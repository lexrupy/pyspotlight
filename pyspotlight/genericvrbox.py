import time
import uinput
import subprocess
import glob
import evdev
import threading
import select

from pyspotlight.utils import LASER_MODE, MOUSE_MODE, PEN_MODE, SPOTLIGHT_MODE
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
        self.start_event_blocking()

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
        try:
            with open(self.path, "rb") as f:
                for pacote in self.read_pacotes_completos(f):
                    self.processa_pacote(pacote)
        except PermissionError:
            self._ctx.log(f"* Sem permissão para acessar {self.path}")
        except OSError as e:
            if e.errno == 5:
                self._ctx.log("- Dispositivo desconectado ou erro de I/O")
            else:
                self._ctx.log(f"* Erro em {self.path}: {e}")
        except Exception as e:
            self._ctx.log(f"* Erro inesperado: {e}")

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

    def read_pacotes_completos(self, f):
        buffer = bytearray()
        while True:
            byte = f.read(1)
            if not byte:
                break  # EOF ou erro
            buffer += byte
            if buffer[0] == 1:  # pacote 5 bytes
                max_len = 5
            else:
                max_len = 3
            if len(buffer) == max_len:
                yield bytes(buffer)
                buffer.clear()

    def processa_pacote(self, pacote: bytes):
        if len(pacote) not in (3, 5):
            self._ctx.log(f"Pacote ignorado (tamanho inesperado): {list(pacote)}")
            return

        grupo = pacote[0]
        codigo = pacote[1]
        chave = (grupo, codigo)

        ow = self._ctx.overlay_window
        current_mode = ow.current_mode()

        if codigo == 0:
            # Botão foi liberado
            if self.botao_ativo:
                tempo_ativo = (
                    time.time() - self.botao_press_start
                    if self.botao_press_start
                    else 0
                )
                long_press = tempo_ativo >= self.LONG_PRESS_MS / 1000

                # Se estava desenhando com G1 ou G2, parar
                if current_mode == PEN_MODE and self.botao_ativo in ("G1", "G2"):
                    ow.handle_draw_command("stop_move")

                self.executa_acao(self.botao_ativo, long_press_state=long_press)

                # Parar repetição se estava ativa
                self._repeat_active = False
                if self._repeat_timer:
                    self._repeat_timer = None

                self.botao_ativo = None
                self.botao_press_start = None
            return

        nome = self.BOTOES_MAP.get(chave)
        if not nome:
            self._ctx.log(f"Botão desconhecido: {list(pacote)}")
            return

        if nome != self.botao_ativo:
            agora = time.time()
            intervalo = agora - self.last_press_time

            self.botao_ativo = nome
            self.botao_press_start = agora
            self.last_press_time = agora  # atualiza para o próximo ciclo

            if current_mode == PEN_MODE and nome in ("G1", "G2"):
                ow.handle_draw_command("start_move")

            # Ativa repetição apenas se for um segundo clique rápido (duplo clique)
            if intervalo < self.__class__.DOUBLE_CLICK_INTERVAL:
                self._repeat_active = True

                def start_repeat():
                    while self._repeat_active and self.botao_ativo == nome:
                        self.executa_acao(nome, long_press_state=True, repeat=True)
                        time.sleep(0.05)

                self._repeat_timer = threading.Thread(target=start_repeat, daemon=True)
                self._repeat_timer.start()

    def executa_acao(self, botao, long_press_state=False, repeat=False):
        self._ctx.log(
            f"[Evento] Botão {botao} - pressão longa: {long_press_state} - repeat: {repeat}"
        )

        ow = self._ctx.overlay_window
        current_mode = self._ctx.overlay_window.current_mode()
        # Exemplo para botão A
        if botao == "C":
            if long_press_state and current_mode == MOUSE_MODE:
                ow.switch_mode(step=-1)
            else:
                ow.switch_mode()

        elif botao == "B":
            if long_press_state and current_mode != MOUSE_MODE:
                ow.set_mouse_mode()
            if current_mode == MOUSE_MODE:
                self.emit_key_press(self._ctx.ui, uinput.KEY_B)
            elif current_mode == PEN_MODE:
                ow.clear_drawing()

        elif botao == "A":
            if long_press_state:
                pass

        elif botao == "D":
            if long_press_state:
                ow.set_mouse_mode()
            else:
                if current_mode in [PEN_MODE, LASER_MODE]:
                    ow.next_color()

        elif botao == "G1":
            if current_mode == MOUSE_MODE and long_press_state:
                self.emit_key_chord(self._ctx.ui, [uinput.KEY_LEFTSHIFT, uinput.KEY_F5])
            if current_mode == MOUSE_MODE:
                self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEDOWN)
            elif current_mode == PEN_MODE:
                ow.change_line_width(+1)
            elif current_mode == SPOTLIGHT_MODE:
                ow.change_spot_radius(+1)

        elif botao == "G2":
            if current_mode == MOUSE_MODE:
                self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEUP)
            elif current_mode == PEN_MODE:
                ow.change_line_width(-1)
            elif current_mode == SPOTLIGHT_MODE:
                ow.change_spot_radius(-1)

        # match status_byte:
        #     case 97:
        #         if current_mode == MOUSE_MODE:
        #             self.emit_key_press(self._ctx.ui, uinput.BTN_LEFT)
        #         else:
        #             ow.set_mouse_mode()
        #     case 99:
        #         if current_mode == MOUSE_MODE:
        #             ow.switch_mode()
        #     case 104 | 114:
        #         ow.handle_draw_command("start_move")
        #     case 105 | 115:
        #         ow.handle_draw_command("stop_move")
        #     case 106:
        #         if current_mode == MOUSE_MODE:
        #             self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEUP)
        #         elif current_mode == PEN_MODE:
        #             ow.change_line_width(+1)
        #         elif current_mode == SPOTLIGHT_MODE:
        #             ow.change_spot_radius(+1)
        #     case 107:
        #         if current_mode == MOUSE_MODE:
        #             self.emit_key_press(self._ctx.ui, uinput.KEY_ESC)
        #         else:
        #             ow.set_mouse_mode()
        #     case 108:
        #         if current_mode == MOUSE_MODE:
        #             self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEDOWN)
        #         elif current_mode == PEN_MODE:
        #             ow.change_line_width(-1)
        #         elif current_mode == SPOTLIGHT_MODE:
        #             ow.change_spot_radius(-1)
        #     case 109:
        #         if current_mode == MOUSE_MODE:
        #             self.emit_key_chord(
        #                 self._ctx.ui, [uinput.KEY_LEFTSHIFT, uinput.KEY_F5]
        #             )
        #     case 113:
        #         now = time.time()
        #         if now - self.last_click_time_113 < self.double_click_interval:
        #             ow.switch_mode()
        #         self.last_click_time_113 = now
        #     case 116 | 117:
        #         if current_mode in [PEN_MODE, LASER_MODE]:
        #             ow.next_color()
        #     case 118:
        #         if current_mode == SPOTLIGHT_MODE:
        #             ow.adjust_overlay_color(0, 10)
        #     case 120:
        #         if current_mode == MOUSE_MODE:
        #             self.emit_key_press(self._ctx.ui, uinput.KEY_VOLUMEUP)
        #         elif current_mode == SPOTLIGHT_MODE:
        #             ow.zoom(+1)
        #     case 121:
        #         if current_mode == MOUSE_MODE:
        #             self.emit_key_press(self._ctx.ui, uinput.KEY_VOLUMEDOWN)
        #         else:
        #             ow.zoom(-1)
        #     case 122 | 123:
        #         if current_mode in [PEN_MODE, LASER_MODE]:
        #             ow.next_color(-1)
        #     case 124:
        #         if current_mode == SPOTLIGHT_MODE:
        #             ow.adjust_overlay_color(0, -10)
        #

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
                            if event.type == evdev.ecodes.EV_REL:
                                # Repassa evento virtual
                                self._ctx.ui.emit((event.type, event.code), event.value)

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
