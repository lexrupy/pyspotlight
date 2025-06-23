import time
import uinput
import evdev
import select
import subprocess


from pyspotlight.utils import MODE_LASER, MODE_MOUSE, MODE_PEN, MODE_SPOTLIGHT
from .pointerdevice import BasePointerDevice


class BaseusOrangeDotAI(BasePointerDevice):
    VENDOR_ID = "abc8"
    PRODUCT_ID = "ca08"

    def __init__(self, app_ctx, hidraw_path):
        super().__init__(app_ctx, hidraw_path)
        self.ctx.ui = self.create_virtual_device(name="Baseus Virtual Presenter")

    @staticmethod
    def match_device(device_info):
        if not device_info.device_node:
            return False
        try:
            output = subprocess.check_output(
                ["udevadm", "info", "-a", "-n", device_info.device_node], text=True
            ).lower()
            vid = BaseusOrangeDotAI.VENDOR_ID
            pid = BaseusOrangeDotAI.PRODUCT_ID
            return vid in output and pid in output
        except Exception:
            return False

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

    def monitor(self):
        if self.path:
            try:
                with open(self.path, "rb") as f:
                    for pacote in self.read_pacotes_completos(f):
                        self.processa_pacote_hid(pacote)
            except PermissionError:
                self.ctx.log(
                    f"🚫 Sem permissão para acessar {self.path} (tente ajustar udev ou rodar com sudo)"
                )
            except KeyboardInterrupt:
                self.ctx.log(f"\nFinalizando monitoramento de {self.path}")
            except OSError as e:
                if e.errno == 5:  # Input/output error
                    self.ctx.log("Dispositivo desconectado ou erro de I/O")
                else:
                    self.ctx.log(f"⚠️ Erro em {self.path}: {e}")

            except Exception as e:
                self.ctx.log(f"⚠️ Erro em {self.path}: {e}")

    @staticmethod
    def should_block_events():
        return True

    @staticmethod
    def block_events_thread(ctx):
        devices = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                if "baseus" in dev.name.lower():
                    dev.grab()
                    devices.append(dev)
                    ctx.log(f"🛑 Bloqueando eventos de: {path}")
            except Exception as e:
                ctx.log(f"⚠️ Erro ao bloquear {path}: {e}")

        if not devices:
            ctx.log("⚠️ Nenhum dispositivo Baseus para bloquear.")
            return

        fd_para_dev = {dev.fd: dev for dev in devices}
        try:
            while True:
                r, _, _ = select.select(fd_para_dev.keys(), [], [])
                for fd in r:
                    try:
                        list(fd_para_dev[fd].read())  # Descarte
                    except Exception:
                        pass
        except Exception as e:
            ctx.log(f"❌ Erro no bloqueio Baseus: {e}")
        finally:
            for dev in devices:
                try:
                    dev.ungrab()
                except:
                    pass
