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
    DOUBLE_CLICK_INTERVAL = 0.3
    LONG_PRESS_INTERVAL = 0.6
    REPEAT_INTERVAL = 0.05

    def __init__(self, app_ctx, hidraw_path):
        super().__init__(app_ctx=app_ctx, hidraw_path=hidraw_path)
        self.last_click_time_113 = 0
        self._ctx.compatible_modes = [MODE_MOUSE, MODE_SPOTLIGHT, MODE_LASER, MODE_PEN]
        self._last_click_time = {}
        self._last_release_time = {}
        self._button_states = {}
        self._repeat_threads = {}
        self._lock = threading.Lock()

        self._status_byte_map = {
            97: "OK",
            98: "OK++",
            99: "OK+long",
            100: "LASER",
            106: "PREV",
            107: "PREV+long",
            108: "NEXT",
            109: "NEXT+long",
            113: "MOUSE",
            114: "MOUSE+hold",
            115: "MOUSE+release",
            116: "MIC",
            117: "MIC",
            118: "MIC+hold",
            119: "MIC+release",
            122: "LNG",
            123: "LNG",
            124: "LNG+hold",
            125: "LNG+release",
            103: "HGL",
            104: "HGL+hold",
            105: "HGL+release",
            120: "VOL_UP",
            121: "VOL_DOWN",
        }

    def _start_repeat(self, button):
        def repeat():
            while self._button_states.get(button, {}).get("repeat_active", False):
                self.executa_acao(f"{button}+repeat")
                time.sleep(self.REPEAT_INTERVAL)

        t = threading.Thread(target=repeat, daemon=True)
        self._repeat_threads[button] = t
        t.start()

    def monitor(self):
        super().monitor()
        self.start_hidraw_monitoring()

    def start_hidraw_monitoring(self):
        if hasattr(self, "_hidraw_thread_started") and self._hidraw_thread_started:
            return
        self._hidraw_thread_started = True

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

        if not (
            isinstance(data, bytes)
            and len(data) == 16
            and data[0] == 10
            and data[-1] == 182
        ):
            return

        status_byte = data[5]

        if status_byte == 0:
            for btn in list(self._button_states):
                self._button_states[btn]["repeat_active"] = False
            return

        button = self._status_byte_map.get(status_byte)

        if not button:
            return

        if any(
            suffix in button
            for suffix in ["++", "+long", "+hold", "+release", "+repeat"]
        ):
            self.executa_acao(button)
            if "+repeat" in button:
                with self._lock:
                    self._button_states[button] = {"repeat_active": True}
            self._ctx.log(f"executa_acao({button})")
            return

        now = time.time()
        last_click = self._last_click_time.get(button, 0)
        last_release = self._last_release_time.get(button, 0)
        is_double = 0 < (now - last_click) < self.DOUBLE_CLICK_INTERVAL

        self._last_click_time[button] = now

        state = {
            "start_time": now,
            "long_pressed": False,
            "repeat_active": False,
        }

        def do_long_press():
            state["long_pressed"] = True
            state["repeat_active"] = True
            self.executa_acao(f"{button}+long")
            self._start_repeat(button)

        # long_timer = threading.Timer(self.LONG_PRESS_INTERVAL, do_long_press)
        # long_timer.start()
        # state["long_timer"] = long_timer

        self._button_states[button] = state

        def single_click():
            if not state.get("long_pressed"):
                if is_double:
                    self.executa_acao(f"{button}++")
                else:
                    self.executa_acao(button)
            self._button_states.pop(button, None)

        click_timer = threading.Timer(self.LONG_PRESS_INTERVAL + 0.05, single_click)
        click_timer.start()

        self._last_release_time[button] = now

        # self._ctx.log(f"executa_acao_byte({status_byte})")
        # self.executa_acao_byte(status_byte)

    def executa_acao_byte(self, status_byte):
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
                if now - self.last_click_time_113 < self.DOUBLE_CLICK_INTERVAL:
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

    def executa_acao(self, button):
        ow = self._ctx.overlay_window
        current_mode = self._ctx.overlay_window.current_mode()

        match button:
            case "OK":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.BTN_LEFT)
            case "OK+long":
                ow.switch_mode(direct_mode=MODE_MOUSE)
            case "LASER":
                ow.set_laser_mode()
            case "PREV":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEUP)
                elif current_mode == MODE_PEN:
                    ow.change_line_width(-1)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(-1)
            case "NEXT":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEDOWN)
                elif current_mode == MODE_PEN:
                    ow.change_line_width(+1)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(+1)
            case "MOUSE":
                ow.switch_mode(
                    direct_mode=(
                        MODE_SPOTLIGHT if current_mode == MODE_MOUSE else MODE_MOUSE
                    )
                )
            case "MIC":
                if current_mode in [MODE_PEN, MODE_LASER]:
                    ow.next_color()
            case "LNG":
                if current_mode in [MODE_PEN, MODE_LASER]:
                    ow.next_color(-1)
            case "HGL":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_B)
                else:
                    ow.clear_drawing()
            case "VOL_UP":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_VOLUMEUP)
                elif current_mode == MODE_SPOTLIGHT:
                    ow.zoom(+1)
            case "VOL_DOWN":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_VOLUMEDOWN)
                else:
                    ow.zoom(-1)
            case _:
                self._ctx.log(f"BOTAO: {button}")

    def handle_event(self, event):
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
