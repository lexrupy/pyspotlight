import time
import uinput
import threading
import os
import evdev.ecodes as ec

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

    # def start_event_blocking(self):
    #     if not self._event_thread or not self._event_thread.is_alive():
    #         devs = self.find_all_event_devices_for_known()
    #         if devs:
    #             self._event_thread = threading.Thread(
    #                 target=self.read_input_events,
    #                 args=(devs,),
    #                 daemon=True,
    #             )
    #             self._event_thread.start()
    #         else:
    #             self._ctx.log(
    #                 "* Nenhum dispositivo de entrada conhecido encontrado para bloquear."
    #             )

    # @classmethod
    # def is_known_device(cls, device_info):
    #     try:
    #         output = subprocess.check_output(
    #             ["udevadm", "info", "-a", "-n", device_info], text=True
    #         ).lower()
    #         vid = f"{cls.VENDOR_ID:04x}"
    #         pid = f"{cls.PRODUCT_ID:04x}"
    #         if vid in output and pid in output:
    #             return True
    #         return False
    #     except subprocess.CalledProcessError:
    #         return False

    def monitor(self):
        super().monitor()
        self.start_hidraw_monitoring()

    def start_hidraw_monitoring(self):
        def run():
            try:
                if os.path.exists(self.path):
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

        threading.Thread(target=run, daemon=True).start()

    def read_pacotes_completos(self, f):
        buffer = bytearray()
        try:
            while not self._stop_event.is_set():
                b = f.read(1)
                if not b:
                    time.sleep(0.01)
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

        self._ctx.log(f"{list(data)}")
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

    def handle_event(self, event):

        # if event.type == ec.EV_REL:  # Movimento de Mouse
        #     # Repassa evento virtual
        #     self._ctx.ui.emit((event.type, event.code), event.value)
        #
        # elif event.type == ec.EV_KEY:
        #     botao = None
        #     all_keys = ec.KEY | ec.BTN
        #     self._ctx.log(f"{all_keys[event.code]} - {event.value}")
        #     match event.code:
        #         case ec.BTN_LEFT | ec.BTN_TL:
        #             botao = "G1"
        #         case ec.BTN_RIGHT | ec.BTN_TR:
        #             botao = "G2"
        #         case ec.BTN_A | ec.KEY_PLAYPAUSE | ec.BTN_TR2:
        #             botao = "A"
        #         case ec.BTN_B | ec.BTN_X:
        #             botao = "B"
        #         case ec.KEY_VOLUMEUP | ec.BTN_TL2:
        #             botao = "C"
        #         case ec.KEY_VOLUMEDOWN | ec.BTN_Y:
        #             botao = "D"
        #         case ec.KEY_NEXTSONG:
        #             botao = "SL"
        #         case ec.KEY_PREVIOUSSONG:
        #             botao = "SR"
        #
        #     if event.value == 1:
        #         pass
        #         # self._on_button_press(botao)
        #     elif event.value == 0:
        #         pass
        # self._on_button_release(botao)
        if event.type == ec.EV_REL or (
            event.type == ec.EV_KEY
            and event.code
            in (
                ec.BTN_LEFT,
                ec.BTN_RIGHT,
            )
        ):
            # Repassa evento virtual com cuidado
            self._ctx.ui.emit((event.type, event.code), event.value)
