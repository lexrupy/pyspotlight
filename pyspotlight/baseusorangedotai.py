import time
import uinput
import threading
import os
import evdev.ecodes as ec

from pyspotlight.utils import (
    MODE_LASER,
    MODE_MOUSE,
    MODE_PEN,
    MODE_SPOTLIGHT,
    MODE_MAG_GLASS,
)
from .pointerdevice import BasePointerDevice


class BaseusOrangeDotAI(BasePointerDevice):
    VENDOR_ID = 0xABC8
    PRODUCT_ID = 0xCA08
    PRODUCT_DESCRIPTION = "Baseus Orange Dot AI Wireless Presenter"
    DOUBLE_CLICK_INTERVAL = 0.4
    LONG_PRESS_INTERVAL = 0.6
    REPEAT_INTERVAL = 0.05

    def __init__(self, app_ctx, hidraw_path):
        super().__init__(app_ctx=app_ctx, hidraw_path=hidraw_path)
        self._ctx.compatible_modes = [
            MODE_MOUSE,
            MODE_SPOTLIGHT,
            MODE_LASER,
            MODE_PEN,
            MODE_MAG_GLASS,
        ]
        self._last_click_time = {}
        self._last_release_time = {}
        self._pending_click_timers = {}
        self._button_states = {}
        self._ultimo_botao_ativo = None
        self._lock = threading.Lock()
        self._hold_states = {}
        self._was_last_esc = False

        self._single_action_buttons = {
            97: "OK",
            98: "OK++",
            99: "OK+long",
            100: "LASER",
            104: "HGL+hold",
            105: "HGL+release",
            107: "PREV+long",
            109: "NEXT+long",
            114: "MOUSE+hold",
            115: "MOUSE+release",
            118: "MIC+hold",
            119: "MIC+release",
            124: "LNG+hold",
            125: "LNG+release",
        }
        self._multiple_action_buttons = {
            106: "PREV",
            108: "NEXT",
            113: "MOUSE",
            116: "MIC",
            122: "LNG",
            # botoes tratados em input events pois se comportam de forma estranha em hidraw quanto ao press/release
            # 103: "HGL", # MONITORADO EM INPUT EVENTS
            120: "VOL_UP",  # MONITORADO TAMBÉM EM INPUT EVENTS, LA RETORNA VOL_UP
            121: "VOL_DOWN",  # MONITORADO TAMBÉM EM INPUT EVENTS, LA RETORNA VOL_DOWN
        }
        self._virtual_repeat_buttons = {"MIC", "LNG", "MOUSE", "VOL_UP", "VOL_DOWN"}

    def _build_button_name(self, button, long_press=False, repeat=False):
        parts = [button]
        if repeat:
            parts.append("repeat")
        elif long_press:
            parts.append("hold")
        return "+".join(parts)

    def _on_button_press(self, botao):
        now = time.time()
        last_click = self._last_click_time.get(botao, 0)
        time_since_last = now - last_click

        is_second_click = (
            0 < time_since_last < self.DOUBLE_CLICK_INTERVAL
            and self._last_release_time.get(botao, 0) > 0
        )

        self._last_click_time[botao] = now

        state = {
            "start_time": now,
            "long_pressed": False,
            "repeat_active": False,
            "is_second_click": is_second_click,
        }

        def set_long_pressed():
            state["long_pressed"] = True
            timer = self._pending_click_timers.pop(botao, None)
            if timer:
                timer.cancel()
            button_name = self._build_button_name(botao, long_press=True)
            if is_second_click:
                with self._lock:
                    state["repeat_active"] = True
                self._repeat_timer(botao)
            else:
                self.executa_acao(button_name)

        long_timer = threading.Timer(self.LONG_PRESS_INTERVAL, set_long_pressed)
        long_timer.start()
        state["long_timer"] = long_timer

        self._button_states[botao] = state

        # Cancelar clique simples pendente se houver
        if botao in self._pending_click_timers:
            self._pending_click_timers[botao].cancel()
            del self._pending_click_timers[botao]

        # Agenda clique simples só se não for second click
        if not is_second_click:

            def emitir_clique_simples():
                current_state = self._button_states.get(botao)
                if current_state is None or (
                    not current_state.get("long_pressed", False)
                    and not current_state.get("repeat_active", False)
                ):
                    self.executa_acao(botao)
                self._pending_click_timers.pop(botao, None)

            click_timer = threading.Timer(
                self.LONG_PRESS_INTERVAL, emitir_clique_simples
            )
            click_timer.start()
            self._pending_click_timers[botao] = click_timer

    def _on_button_release(self, botao):
        state = self._button_states.pop(botao, None)
        if not state:
            return

        if "long_timer" in state:
            state["long_timer"].cancel()

        with self._lock:
            if "repeat_timer" in state:
                state["repeat_timer"].cancel()

        now = time.time()
        duration = now - state["start_time"]
        last_release = self._last_release_time.get(botao, 0)

        self._last_release_time[botao] = now

        if (
            last_release > 0
            and (now - last_release) < self.DOUBLE_CLICK_INTERVAL
            and duration < self.LONG_PRESS_INTERVAL
            and not state["long_pressed"]
        ):
            self.executa_acao(f"{botao}++")
            return

        # Caso 2: já emitiu long ou repeat, então não faz mais nada
        if state.get("long_pressed", False) or state.get("repeat_active", False):
            self.executa_acao(f"{botao}+release")
            return

    def _repeat_timer(self, botao):
        with self._lock:
            state = self._button_states.get(botao)
            if not state or not state.get("repeat_active"):
                return
            button = self._build_button_name(botao, repeat=True)
        self.executa_acao(button)
        # Reagenda fora do lock para evitar deadlock
        t = threading.Timer(self.REPEAT_INTERVAL, self._repeat_timer, args=(botao,))
        with self._lock:
            # Verifica novamente antes de armazenar/agendar
            state = self._button_states.get(botao)
            if not state or not state.get("repeat_active"):
                return
            # Cancelar timer anterior, se existir
            old_timer = state.get("repeat_timer")
            if old_timer:
                old_timer.cancel()
            state["repeat_timer"] = t
            t.start()

    def check_hold_repeat(self, button):
        now = time.time()
        hold_start = self.get_hold_start(button)
        hold_time = self.get_hold_time(button)
        timer = now - hold_time
        if hold_start and timer < self.LONG_PRESS_INTERVAL:
            self.set_hold_start(button, False)
            self.start_hold_repeat(button)
            return True
        return False

    def start_hold_repeat(self, button):
        if button not in self._virtual_repeat_buttons:
            return False
        with self._lock:
            estado = self._button_states.get(button)
            if not estado:
                estado = {
                    "repeat_active": True,
                    "hold_active": True,
                    "long_pressed": False,
                    "start_time": time.time(),
                }
                self._button_states[button] = estado
            else:
                estado["repeat_active"] = True
                estado["hold_active"] = True

        # Inicia o timer de repeat
        self._repeat_timer(button)

    def end_hold_repeat(self, button):
        with self._lock:
            estado = self._button_states.get(button)
            if not estado:
                return
            estado["repeat_active"] = False
            estado["hold_active"] = False
            repeat_timer = estado.get("repeat_timer")
            if repeat_timer:
                repeat_timer.cancel()
                del estado["repeat_timer"]
                return True
        return False

        # self.executa_acao(f"{button}+release")

    def set_hold_start(self, button, value=True):
        now = time.time()
        self._hold_states[button] = self._hold_states.get(button, {})
        self._hold_states[button]["hold_start"] = value
        if value:
            self._hold_states[button]["hold_time"] = now
        else:
            self._hold_states[button]["hold_time"] = 0

    def get_hold_start(self, button):
        return self._hold_states.get(button, {}).get("hold_start", False)

    def get_hold_time(self, button):
        return self._hold_states.get(button, {}).get("hold_time", 0)

    def get_button(self, status_byte):
        all_buttons = self._single_action_buttons | self._multiple_action_buttons
        _byte = status_byte
        if status_byte in [116, 117]:
            _byte = 116
        elif status_byte in [122, 123]:
            _byte = 122
        if _byte in all_buttons:
            return all_buttons[_byte]
        return False

    def stop(self):
        super().stop()
        for t in self._pending_click_timers.values():
            t.cancel()
        self._pending_click_timers.clear()

    def start_hidraw_monitoring(self):
        if self._hidraw_thread and self._hidraw_thread.is_alive():
            return
        # time.sleep(0.8)

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

        # self._hidraw_thread = threading.Thread(target=run, daemon=True).start()
        self._hidraw_thread = threading.Thread(target=run, daemon=True)
        self._hidraw_thread.start()

    def stop_hidraw_monitoring(self):
        self._stop_hidraw_event.set()
        if self._hidraw_thread and self._hidraw_thread.is_alive():
            self._stop_hidraw_event.set()
            self._hidraw_thread.join(
                timeout=1
            )  # espera a thread encerrar (timeout opcional)

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
            # Somente libera o botão que estava ativo
            if self._ultimo_botao_ativo:
                self._on_button_release(self._ultimo_botao_ativo)
                self._ultimo_botao_ativo = None
            return

        button = self.get_button(status_byte)

        if not button:
            return

        # Estes botoes executam diretamente, sem tratamento
        if button in self._single_action_buttons.values():
            self.executa_acao(button)
        else:
            # Se for um novo botão e havia outro ativo, libera o anterior
            if self._ultimo_botao_ativo and self._ultimo_botao_ativo != button:
                self._on_button_release(self._ultimo_botao_ativo)

            # Atualiza botão atualmente ativo
            self._ultimo_botao_ativo = button

            # Processa pressão do novo botão
            self._on_button_press(button)

    def executa_acao(self, button):
        ow = self._ctx.overlay_window
        current_mode = self._ctx.overlay_window.current_mode()

        # self._ctx.log(f"{button}")
        match button:
            case "OK":
                if ow.isVisible():
                    ow.switch_mode()
                else:
                    self.emit_key_press(uinput.BTN_LEFT)
            case "OK++":
                if ow.isVisible():
                    ow.switch_mode()
                else:
                    self.emit_key_chord([uinput.KEY_LEFTALT, uinput.KEY_TAB])
            case "OK+long":
                ow.set_auto_mode(not ow.auto_mode_enabled)
            case "LASER":
                pass
            case "PREV":
                if ow.isVisible():
                    # When not visible, already emit KEY_PAGEUP
                    pass
            case "PREV+long":
                if not ow.isVisible():
                    if self._was_last_esc:
                        self.emit_key_chord([uinput.KEY_LEFTSHIFT, uinput.KEY_F5])
                        self._was_last_esc = False
                    else:
                        self.emit_key_press(uinput.KEY_ESC)
                        self._was_last_esc = True
                # else:
                #     ow.switch_mode(direct_mode=MODE_MOUSE)
            case "NEXT":
                if ow.isVisible():
                    # When not visible, already emit KEY_PAGEDOWN
                    pass
            case "NEXT+long":
                pass
            case "MOUSE":
                if not self.check_hold_repeat("MOUSE"):
                    pass
            case "MOUSE+hold":
                self.set_hold_start("MOUSE")
                if ow.auto_mode_enabled:
                    ow.show_overlay()
            case "MOUSE+release":
                if self.end_hold_repeat("MOUSE"):
                    pass
                else:
                    if ow.auto_mode_enabled:
                        ow.hide_overlay()
            case "MOUSE+repeat":
                pass
            case "MOUSE++":
                ow.switch_mode()
            case "MIC":
                if not self.check_hold_repeat("MIC"):
                    if current_mode == MODE_LASER:
                        ow.next_laser_color(+1)
                    elif current_mode == MODE_PEN:
                        ow.next_pen_color(+1)
                    elif current_mode == MODE_SPOTLIGHT:
                        ow.set_overlay_color_white()
            case "MIC++":
                pass
            case "MIC+hold":
                self.set_hold_start("MIC")
            case "MIC+release":
                if self.end_hold_repeat("MIC"):
                    pass
            case "MIC+repeat":
                pass
            case "LNG":
                if not self.check_hold_repeat("LNG"):
                    if current_mode == MODE_LASER:
                        ow.next_laser_color(-1)
                    elif current_mode == MODE_PEN:
                        ow.next_pen_color(-1)
                    elif current_mode == MODE_SPOTLIGHT:
                        ow.set_overlay_color_black()
            case "LNG++":
                pass
            case "LNG+hold":
                self.set_hold_start("LNG")
            case "LNG+release":
                if self.end_hold_repeat("LNG"):
                    pass
            case "LNG+repeat":
                pass
            case "HGL":
                if current_mode == MODE_PEN:
                    ow.clear_drawing()
            case "HGL++":
                if current_mode == MODE_PEN:
                    ow.clear_drawing(all=True)
            case "VOL_UP+hold":
                self.start_hold_repeat("VOL_UP")
            case "VOL_UP+release":
                if self.end_hold_repeat("VOL_UP"):
                    pass
            case "VOL_UP":
                if current_mode == MODE_PEN:
                    ow.change_line_width(+2)
                elif current_mode == MODE_MAG_GLASS:
                    ow.zoom(+1)
                if current_mode == MODE_LASER:
                    ow.change_laser_size(+10)
                if current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(+5)
            case "VOL_UP+repeat":
                if current_mode == MODE_PEN:
                    ow.change_line_width(+1)
                if current_mode == MODE_LASER:
                    ow.change_laser_size(+1)
                if current_mode in [MODE_SPOTLIGHT, MODE_MAG_GLASS]:
                    ow.change_spot_radius(+1)
            case "VOL_DOWN":
                if current_mode == MODE_PEN:
                    ow.change_line_width(-2)
                elif current_mode == MODE_MAG_GLASS:
                    ow.zoom(-1)
                if current_mode == MODE_LASER:
                    ow.change_laser_size(-10)
                if current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(-5)

            case "VOL_DOWN+hold":
                self.start_hold_repeat("VOL_DOWN")
            case "VOL_DOWN+release":
                if self.end_hold_repeat("VOL_DOWN"):
                    pass
            case "VOL_DOWN+repeat":
                if current_mode == MODE_PEN:
                    ow.change_line_width(-1)
                if current_mode == MODE_LASER:
                    ow.change_laser_size(-1)
                if current_mode in [MODE_SPOTLIGHT, MODE_MAG_GLASS]:
                    ow.change_spot_radius(-1)

    @classmethod
    def device_filter(cls, device_info, udevadm_output):
        # Only InterfaceProtocol 02 returns relevant info
        if "hidraw" in device_info:
            return 'attrs{binterfaceprotocol}=="02"' in udevadm_output
        return True

    def log_key(self, ev):
        all_keys = ec.KEY | ec.BTN
        if ev.value == 1:
            direction = "down"
        else:
            direction = "up"
        self._ctx.log(f"{all_keys[ev.code]} - {direction}")

    def handle_event(self, event):
        if event.type == ec.EV_REL:  # Movimento de Mouse
            # Repassa evento virtual
            self._ctx.ui.emit((event.type, event.code), event.value)

        elif event.type == ec.EV_KEY:
            ow = self._ctx.overlay_window
            button = None

            # self.log_key(event)
            match event.code:
                case (
                    ec.KEY_VOLUMEUP
                    | ec.KEY_VOLUMEDOWN
                    | ec.KEY_B
                    | ec.KEY_E
                    | ec.KEY_PAGEDOWN
                    | ec.KEY_PAGEUP
                    # | ec.KEY_LEFTSHIFT
                    # | ec.KEY_F5
                    # | ec.KEY_ESC
                    # | ec.KEY_TAB
                    # | ec.BTN_RIGHT
                    # | ec.BTN_LEFT
                ):
                    if ow and ow.isVisible():
                        pass
                    else:

                        # Emit if overlay is not visible
                        self._ctx.ui.emit((event.type, event.code), event.value)
                case ec.KEY_E:
                    button = "HGL"

            if button:
                if event.value == 1:
                    self._on_button_press(button)
                elif event.value == 0:
                    self._on_button_release(button)
