import time
import uinput

from pyspotlight.utils import MODE_LASER, MODE_MOUSE, MODE_PEN, MODE_SPOTLIGHT
from .pointerdevice import BasePointerDevice


class BaseusOrangeDotAI(BasePointerDevice):
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
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self.ctx.ui, uinput.BTN_LEFT)
                else:
                    ow.switch_mode(direct_mode=MODE_MOUSE)
            case 99:
                if current_mode == MODE_MOUSE:
                    ow.switch_mode()
            case 103:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_B)
                else:
                    ow.clear_drawing()
            case 104 | 114:
                ow.handle_draw_command("start_move")
            case 105 | 115:
                ow.handle_draw_command("stop_move")
            case 106:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_PAGEUP)
                elif current_mode == MODE_PEN:
                    ow.change_line_width(+1)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(+1)
            case 107:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_ESC)
                else:
                    ow.switch_mode(direct_mode=MODE_MOUSE)
            case 108:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_PAGEDOWN)
                elif current_mode == MODE_PEN:
                    ow.change_line_width(-1)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(-1)
            case 109:
                if current_mode == MODE_MOUSE:
                    self.emit_key_chord(
                        self.ctx.ui, [uinput.KEY_LEFTSHIFT, uinput.KEY_F5]
                    )
            case 113:
                now = time.time()
                if now - self.last_click_time_113 < self.double_click_interval:
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
                    self.emit_key_press(self.ctx.ui, uinput.KEY_VOLUMEUP)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.zoom(+1)
            case 121:
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self.ctx.ui, uinput.KEY_VOLUMEDOWN)
                else:
                    ow.zoom(-1)
            case 122 | 123:
                if current_mode in [MODE_PEN, MODE_LASER]:
                    ow.next_color(-1)
            case 124:
                if current_mode == MODE_SPOTLIGHT:
                    ow.adjust_overlay_color(0, -10)
