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

        self.botao_ativo = None
        self.tempo_pressao = 0
        self.pressao_longa_disparada = False

        self._repeat_timer = None
        self._repeat_active = False
        self.last_press_time = 0

        self._event_thread = None

        self.add_known_path(hidraw_path)
        for device in self.find_all_event_devices_for_known():
            self.add_known_path(device.path)

    def start_event_blocking(self):
        if not self._event_thread or not self._event_thread.is_alive():
            devs = self.find_all_event_devices_for_known()
            if devs:
                self._event_thread = threading.Thread(
                    target=self.prevent_key_and_mouse_events,
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

    def executa_acao(self, botao, state=0):

        # TODO: Calcular aqui se é long-press ou se é repeat
        long_press_state = False
        repeat = False
        # self._ctx.log(
        #     f"[Evento] Botão {botao} - pressão longa: {long_press_state} - repeat: {repeat}"
        # )

        ow = self._ctx.overlay_window
        current_mode = self._ctx.overlay_window.current_mode()
        # Exemplo para botão A
        if botao == "C":
            if long_press_state and current_mode == MODE_MOUSE:
                ow.switch_mode(step=-1)
            else:
                ow.switch_mode()

        elif botao == "B":
            if long_press_state and current_mode != MODE_MOUSE:
                ow.set_mouse_mode()
            if current_mode == MODE_MOUSE:
                self.emit_key_press(self._ctx.ui, uinput.KEY_B)
            elif current_mode == MODE_PEN:
                ow.clear_drawing()

        elif botao == "A":
            if long_press_state:
                pass

        elif botao == "D":
            if long_press_state:
                ow.set_mouse_mode()
            else:
                if current_mode in [MODE_PEN, MODE_LASER]:
                    ow.next_color()

        elif botao == "G1":
            if current_mode == MODE_MOUSE and long_press_state:
                self.emit_key_chord(self._ctx.ui, [uinput.KEY_LEFTSHIFT, uinput.KEY_F5])
            if current_mode == MODE_MOUSE:
                self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEDOWN)
            elif current_mode == MODE_PEN:
                ow.change_line_width(+1)
            elif current_mode == MODE_SPOTLIGHT:
                ow.change_spot_radius(+1)

        elif botao == "G2":
            if current_mode == MODE_MOUSE:
                self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEUP)
            elif current_mode == MODE_PEN:
                ow.change_line_width(-1)
            elif current_mode == MODE_SPOTLIGHT:
                ow.change_spot_radius(-1)

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

    def prevent_key_and_mouse_events(self, devices):
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
                                self.executa_acao(botao, state=event.value)
                                if botao:
                                    self._ctx.log(
                                        f"BOTAO: {botao} STATE: {event.value}"
                                    )
                                else:
                                    self._ctx.log(
                                        f"KEY: {all_keys[event.code]} - {event.code} STATE: {event.value}"
                                    )

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
