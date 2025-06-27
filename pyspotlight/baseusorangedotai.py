import time
import uinput
import subprocess
import glob
import evdev
import threading
import select

from pyspotlight.utils import MODE_LASER, MODE_MOUSE, MODE_PEN, MODE_SPOTLIGHT
from .pointerdevice import BasePointerDevice


class BaseusOrangeDotAI(BasePointerDevice):
    VENDOR_ID = 0xABC8
    PRODUCT_ID = 0xCA08
    PRODUCT_DESCRIPTION = "Baseus Orange Dot AI Wireless Presenter"

    def __init__(self, app_ctx, hidraw_path):
        super().__init__(app_ctx=app_ctx, hidraw_path=hidraw_path)
        self.last_click_time_113 = 0
        self.double_click_interval = 0.3  # segundos para considerar duplo clique
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

    @classmethod
    def is_known_device(cls, device_info):
        try:
            output = subprocess.check_output(
                ["udevadm", "info", "-a", "-n", device_info], text=True
            ).lower()
            vid = f"{cls.VENDOR_ID:04x}"
            pid = f"{cls.PRODUCT_ID:04x}"
            if vid in output and pid in output:
                return True
            return False
        except subprocess.CalledProcessError:
            return False

    def monitor(self):
        try:
            with open(self.path, "rb") as f:
                for pacote in self.read_pacotes_completos(f):
                    self.processa_pacote_hid(pacote)
        except PermissionError:
            self._ctx.log(
                f"* Sem permissão para acessar {self.path} (tente ajustar udev ou rodar com sudo)"
            )
        except KeyboardInterrupt:
            self._ctx.log(f"\nFinalizando monitoramento de {self.path}")
        except OSError as e:
            if e.errno == 5:  # Input/output error
                self._ctx.log("- Dispositivo desconectado ou erro de I/O")
            else:
                self._ctx.log(f"* Erro em {self.path}: {e}")

        except Exception as e:
            self._ctx.log(f"*  Erro em {self.path}: {e}")

    def read_pacotes_completos(self, f):
        try:
            buffer = bytearray()
            while True:
                b = f.read(1)
                if not b:
                    break
                buffer += b
                if b[0] == 182:
                    yield bytes(buffer)
                    buffer.clear()
        except OSError as e:
            print(f"[ERRO] Falha ao ler do device: {e}")
            self._ctx.log(f"[ERRO] Falha ao ler do device: {e}")
        except Exception as e:
            print(f"[ERRO] Exceção inesperada: {e}")
            self._ctx.log(f"[ERRO] Exceção inesperada: {e}")

    def processa_pacote_hid(self, data):
        if not (
            isinstance(data, bytes)
            and len(data) == 16
            and data[0] == 10
            and data[-1] == 182
        ):
            return

        status_byte = data[5]
        if status_byte == 0:
            return

        ow = self._ctx.overlay_window
        current_mode = self._ctx.overlay_window.current_mode()

        match status_byte:
            case 97:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.BTN_LEFT)
                else:
                    ow.switch_mode(direct_mode=MODE_MOUSE)
            case 99:
                if current_mode == MODE_MOUSE:
                    ow.switch_mode()
            case 103:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_B)
                else:
                    ow.clear_drawing()
            case 104 | 114:
                ow.handle_draw_command("start_move")
            case 105 | 115:
                ow.handle_draw_command("stop_move")
            case 106:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEUP)
                elif current_mode == MODE_PEN:
                    ow.change_line_width(-1)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(-1)
            case 107:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_ESC)
                else:
                    ow.set_mouse_mode()
            case 108:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEDOWN)
                elif current_mode == MODE_PEN:
                    ow.change_line_width(+1)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(+1)
            case 109:
                if current_mode == MODE_MOUSE:
                    self.emit_key_chord(
                        self._ctx.ui, [uinput.KEY_LEFTSHIFT, uinput.KEY_F5]
                    )
            case 113:
                now = time.time()
                if now - self.last_click_time_113 < self.double_click_interval:
                    if current_mode == MODE_MOUSE:
                        ow.switch_mode(direct_mode=MODE_SPOTLIGHT)
                    else:
                        ow.switch_mode()
                self.last_click_time_113 = now
            case 116 | 117:
                if current_mode in [MODE_PEN, MODE_LASER]:
                    ow.next_color()
            case 118:
                if current_mode == MODE_SPOTLIGHT:
                    ow.adjust_overlay_color(0, 10)
            case 120:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_VOLUMEUP)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.zoom(+1)
            case 121:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_VOLUMEDOWN)
                else:
                    ow.zoom(-1)
            case 122 | 123:
                if current_mode in [MODE_PEN, MODE_LASER]:
                    ow.next_color(-1)
            case 124:
                if current_mode == MODE_SPOTLIGHT:
                    ow.adjust_overlay_color(0, -10)

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

        if not fd_para_dev:
            self._ctx.log("* Nenhum dispositivo monitorado para bloquear eventos.")
            return

        self._ctx.log("* Monitorando dispositivos...")

        try:
            while True:
                r, _, _ = select.select(fd_para_dev.keys(), [], [])
                for fd in r:
                    dev = fd_para_dev.get(fd)
                    if dev is None:
                        continue
                    try:
                        for event in dev.read():
                            if event.type == evdev.ecodes.EV_REL or (
                                event.type == evdev.ecodes.EV_KEY
                                and event.code
                                in (
                                    evdev.ecodes.BTN_LEFT,
                                    evdev.ecodes.BTN_RIGHT,
                                )
                            ):
                                # Repassa evento virtual com cuidado
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
                            if not fd_para_dev:
                                self._ctx.log(
                                    "* Nenhum dispositivo restante para monitorar. Encerrando thread."
                                )
                                return
                        else:
                            self._ctx.log(f"* Erro de OSError na leitura: {e}")
                            # Opcional: continue ou re-raise, cuidado com segfaults
                    except Exception as e:
                        self._ctx.log(f"* Exceção inesperada: {e}")
                        # Não re-raise para evitar segfaults inesperados
        except KeyboardInterrupt:
            self._ctx.log("\n* Encerrando monitoramento.")
        finally:
            for dev in devices:
                try:
                    dev.ungrab()
                except Exception:
                    pass
