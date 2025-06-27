import time
import uinput
import subprocess
import glob
import evdev
import evdev.ecodes as ec
import threading
import select

from pyspotlight.utils import MODE_LASER, MODE_MOUSE, MODE_PEN, MODE_SPOTLIGHT
from .pointerdevice import BasePointerDevice


class GenericVRBoxPointer(BasePointerDevice):
    VENDOR_ID = 0x248A
    PRODUCT_ID = 0x8266
    PRODUCT_DESCRIPTION = "Generic VR BOX Bluetooth Controller"
    BOTOES_MAP = {
        (1, 1): "G1",
        (1, 2): "G2",
        (2, 1): "C",
        (2, 2): "D",
        (4, 1): "A",
        (4, 2): "B",
    }
    LONG_PRESS_MS = 600  # tempo mínimo para considerar pressionamento longo
    DOUBLE_CLICK_INTERVAL = 0.4  # segundos

    def __init__(self, app_ctx, hidraw_path):
        super().__init__(app_ctx=app_ctx, hidraw_path=hidraw_path)

        self._event_thread = None

        # botao: {start_time, long_timer, repeat_timer, long_pressed}
        self._button_states = {}
        self._last_click_time = {}

        self.add_known_path(hidraw_path)
        for device in self.find_all_event_devices_for_known():
            self.add_known_path(device.path)

    def _build_button_name(self, button, long_press=False, repeat=False):
        parts = [button]
        if repeat:
            parts.append("repeat")
        elif long_press:
            parts.append("long")
        return "+".join(parts)

    def _on_button_press(self, botao):
        now = time.time()
        last_click = self._last_click_time.get(botao, 0)
        time_since_last = now - last_click

        is_second_click = 0 < time_since_last < self.DOUBLE_CLICK_INTERVAL
        self._last_click_time[botao] = now

        state = {
            "start_time": now,
            "long_pressed": False,
            "repeat_active": False,
            "is_second_click": is_second_click,
        }

        def set_long_pressed():
            state["long_pressed"] = True
            button_name = self._build_button_name(botao, long_press=True)
            self.executa_acao(button_name, state=1)
            # Ativar repeat apenas no segundo clique + segurar
            if is_second_click:
                state["repeat_active"] = True
                self._repeat_timer(botao)

        long_timer = threading.Timer(self.LONG_PRESS_MS / 1000, set_long_pressed)
        long_timer.start()
        state["long_timer"] = long_timer
        self._button_states[botao] = state
        # Verificar combinações conhecidas de botões simultâneos
        # Exemplo: G1 + G2
        if (
            "G1" in self._button_states
            and "G2" in self._button_states
            and not self._button_states["G1"].get("combo_disparado")
            and not self._button_states["G2"].get("combo_disparado")
        ):
            combo_nome = "G1+G2"
            self._ctx.log(f"[Combo] {combo_nome} detectado")
            self._button_states["G1"]["combo_disparado"] = True
            self._button_states["G2"]["combo_disparado"] = True
            self.executa_acao(combo_nome, state=1)

    def _repeat_timer(self, botao):
        state = self._button_states.get(botao)
        if state and state["repeat_active"]:
            button = self._build_button_name(botao, repeat=True)
            self.executa_acao(button, state=1)
            t = threading.Timer(0.1, self._repeat_timer, args=(botao,))
            state["repeat_timer"] = t
            t.start()

    def _on_button_release(self, botao):
        state = self._button_states.pop(botao, None)
        if not state:
            return
        if "long_timer" in state:
            state["long_timer"].cancel()
        if "repeat_timer" in state:
            state["repeat_timer"].cancel()
        # Liberando combo se existir
        for k in list(self._button_states):
            if self._button_states[k].get("combo_disparado"):
                self._ctx.log(f"[Combo] {k} liberado (parte de combo)")
                self._button_states[k]["combo_disparado"] = False
        button = self._build_button_name(
            botao, long_press=state.get("long_pressed", False)
        )
        self.executa_acao(button, state=0)

    def start_event_blocking(self):
        if not self._event_thread or not self._event_thread.is_alive():
            devs = self.find_all_event_devices_for_known()
            if devs:
                self._event_thread = threading.Thread(
                    target=self.read_input_events,
                    args=(devs,),
                    daemon=True,
                )
                self._event_thread.start()
            else:
                self._ctx.log(
                    "* Nenhum dispositivo de entrada conhecido encontrado para bloquear."
                )

    def monitor(self):
        self.start_event_blocking()

    def find_all_event_devices_for_known(self):
        devices = []
        for path in glob.glob("/dev/input/event*"):
            if self.__class__.is_known_device(path):
                try:
                    devices.append(evdev.InputDevice(path))
                    self._ctx.log(f"* Encontrado device de entrada: {path}")
                except Exception as e:
                    self._ctx.log(f"* Erro ao acessar {path}: {e}")
        return devices

    def executa_acao(self, botao, state):
        # state = 0 botão solto, 1 botão pressionado
        self._ctx.log(f"[Evento] Botão {botao}")

        ow = self._ctx.overlay_window
        current_mode = self._ctx.overlay_window.current_mode()
        # Exemplo para botão A
        match botao:
            case "G1+G2":
                pass
            case "G1":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEDOWN)
                elif current_mode == MODE_PEN:
                    ow.change_line_width(+1)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(+1)
            case "G1+long":
                self.emit_key_chord(self._ctx.ui, [uinput.KEY_LEFTSHIFT, uinput.KEY_F5])
            case "G2":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEUP)
                elif current_mode == MODE_PEN:
                    ow.change_line_width(-1)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(-1)
            case "G2+long":
                pass
            case "A":
                pass
            case "A+long":
                pass
            case "B":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_B)
                elif current_mode == MODE_PEN:
                    ow.clear_drawing()
            case "B+long":
                ow.set_mouse_mode()
            case "C":
                ow.switch_mode()
            case "C+long":
                ow.switch_mode(step=-1)
            case "D":
                if current_mode in [MODE_PEN, MODE_LASER]:
                    ow.next_color()
            case "D+long":
                ow.set_mouse_mode()

    @classmethod
    def is_known_device(cls, device_info):
        try:
            output = subprocess.check_output(
                ["udevadm", "info", "-a", "-n", device_info], text=True
            ).lower()
            vid = f"{cls.VENDOR_ID:04x}"
            pid = f"{cls.PRODUCT_ID:04x}"
            return vid in output and pid in output
        except subprocess.CalledProcessError:
            return False

    def read_input_events(self, devices):
        fd_para_dev = {}
        for dev in devices:
            try:
                dev.grab()
                fd_para_dev[dev.fd] = dev
                self._ctx.log(f"* Monitorado: {dev.path}")
            except Exception as e:
                self._ctx.log(
                    f"* Erro ao monitorar dispositivo {dev.path}: {e}. Tente executar como root ou ajuste as regras udev."
                )
        self._ctx.log("* Monitorando dispositivos...")

        try:
            while True:
                r, _, _ = select.select(fd_para_dev, [], [])
                for fd in r:
                    dev = fd_para_dev.get(fd)
                    if dev is None:
                        continue
                    try:
                        for event in dev.read():
                            if event.type == ec.EV_REL:  # Movimento de Mouse
                                # Repassa evento virtual
                                self._ctx.ui.emit((event.type, event.code), event.value)

                            elif event.type == ec.EV_KEY:
                                botao = None
                                all_keys = ec.KEY | ec.BTN
                                match event.code:
                                    case ec.BTN_LEFT | ec.BTN_TL:
                                        botao = "G1"
                                    case ec.BTN_RIGHT | ec.BTN_TR:
                                        botao = "G2"
                                    case ec.BTN_A | ec.KEY_PLAYPAUSE | ec.BTN_TR2:
                                        botao = "A"
                                    case ec.BTN_B | ec.BTN_X:
                                        botao = "B"
                                    case ec.KEY_VOLUMEUP | ec.BTN_TL2:
                                        botao = "C"
                                    case ec.KEY_VOLUMEDOWN | ec.BTN_Y:
                                        botao = "D"
                                    case ec.KEY_NEXTSONG:
                                        botao = "SL"
                                    case ec.KEY_PREVIOUSSONG:
                                        botao = "SR"

                                if event.value == 1:
                                    self._on_button_press(botao)
                                elif event.value == 0:
                                    self._on_button_release(botao)

                    except OSError as e:
                        if e.errno == 19:  # No such device
                            self._ctx.log(f"- Dispositivo desconectado: {dev.path}")
                            # Remove dispositivo da lista para não monitorar mais
                            fd_para_dev.pop(fd, None)
                            try:
                                dev.ungrab()
                            except Exception:
                                pass
                            # Opcional: se não há mais dispositivos, pode encerrar ou esperar
                            if not fd_para_dev:
                                self._ctx.log(
                                    "* Nenhum dispositivo restante para monitorar. Encerrando thread."
                                )
                                return
                        else:
                            raise

        except KeyboardInterrupt:
            self._ctx.log("\n* Encerrando monitoramento.")
        finally:
            for dev in devices:
                try:
                    dev.ungrab()
                except Exception:
                    pass
