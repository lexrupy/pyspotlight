import time
import uinput

from pyspotlight.utils import LASER_MODE, MOUSE_MODE, PEN_MODE, SPOTLIGHT_MODE
from .pointerdevice import BasePointerDevice


class BaseusOrangeDotAI(BasePointerDevice):
    VENDOR_ID = 0xABC8
    PRODUCT_ID = 0xCA08

    def __init__(self, app_ctx, hidraw_path):
        super().__init__(app_ctx=app_ctx, hidraw_path=hidraw_path)
        self.last_click_time_113 = 0
        self.double_click_interval = 0.3  # segundos para considerar duplo clique

    def monitor(self):
        try:
            with open(self.path, "rb") as f:
                for pacote in self.read_pacotes_completos(f):
                    self.processa_pacote_hid(pacote)
        except PermissionError:
            print(
                f"🚫 Sem permissão para acessar {self.path} (tente ajustar udev ou rodar com sudo)"
            )
        except KeyboardInterrupt:
            print(f"\nFinalizando monitoramento de {self.path}")
        except OSError as e:
            if e.errno == 5:  # Input/output error
                print("Dispositivo desconectado ou erro de I/O")
            else:
                print(f"⚠️ Erro em {self.path}: {e}")

        except Exception as e:
            print(f"⚠️ Erro em {self.path}: {e}")

    def read_pacotes_completos(self, f):
        buffer = bytearray()
        while True:
            b = f.read(1)
            if not b:
                break
            buffer += b
            if b[0] == 182:
                yield bytes(buffer)
                buffer.clear()

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

        ow = self.ctx.overlay_window
        current_mode = self.ctx.overlay_window.current_mode()

        match status_byte:
            case 97:
                if current_mode == MOUSE_MODE:
                    self.emit_key_press(self.ctx.ui, uinput.BTN_LEFT)
                else:
                    ow.set_mouse_mode()
            case 99:
                if current_mode == MOUSE_MODE:
                    ow.switch_mode()
            case 103:
                if current_mode == MOUSE_MODE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_B)
                else:
                    ow.clear_drawing()
            case 104 | 114:
                ow.handle_draw_command("start_move")
            case 105 | 115:
                ow.handle_draw_command("stop_move")
            case 106:
                if current_mode == MOUSE_MODE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_PAGEUP)
                elif current_mode == PEN_MODE:
                    ow.change_line_width(+1)
                elif current_mode == SPOTLIGHT_MODE:
                    ow.change_spot_radius(+1)
            case 107:
                if current_mode == MOUSE_MODE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_ESC)
                else:
                    ow.set_mouse_mode()
            case 108:
                if current_mode == MOUSE_MODE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_PAGEDOWN)
                elif current_mode == PEN_MODE:
                    ow.change_line_width(-1)
                elif current_mode == SPOTLIGHT_MODE:
                    ow.change_spot_radius(-1)
            case 109:
                if current_mode == MOUSE_MODE:
                    self.emit_key_chord(
                        self.ctx.ui, [uinput.KEY_LEFTSHIFT, uinput.KEY_F5]
                    )
            case 113:
                now = time.time()
                if now - self.last_click_time_113 < self.double_click_interval:
                    ow.switch_mode()
                self.last_click_time_113 = now
            case 116 | 117:
                if current_mode in [PEN_MODE, LASER_MODE]:
                    ow.next_color()
            case 118:
                if current_mode == SPOTLIGHT_MODE:
                    ow.adjust_overlay_color(0, 10)
            case 120:
                if current_mode == MOUSE_MODE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_VOLUMEUP)
                elif current_mode == SPOTLIGHT_MODE:
                    ow.zoom(+1)
            case 121:
                if current_mode == MOUSE_MODE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_VOLUMEDOWN)
                else:
                    ow.zoom(-1)
            case 122 | 123:
                if current_mode in [PEN_MODE, LASER_MODE]:
                    ow.next_color(-1)
            case 124:
                if current_mode == SPOTLIGHT_MODE:
                    ow.adjust_overlay_color(0, -10)
