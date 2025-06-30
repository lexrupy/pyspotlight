import time
import uinput
import evdev.ecodes as ec
import threading

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
    LONG_PRESS_INTERVAL = 0.6  # tempo mínimo para considerar pressionamento longo
    DOUBLE_CLICK_INTERVAL = 0.4  # segundos
    COMBO_WINDOW = 0.3
    REPEAT_INTERVAL = 0.05

    def __init__(self, app_ctx, hidraw_path):
        super().__init__(app_ctx=app_ctx, hidraw_path=hidraw_path)
        # botao: {start_time, long_timer, repeat_timer, long_pressed}

        self._button_states = {}
        self._last_click_time = {}
        self._last_release_time = {}
        self._pending_click_timers = {}  # botao: threading.Timer
        self._lock = threading.Lock()
        self._ctx.compatible_modes = [MODE_MOUSE, MODE_SPOTLIGHT, MODE_LASER]

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
            "combo_disparado": False,
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
                self.executa_acao(button_name, state=1)

        long_timer = threading.Timer(self.LONG_PRESS_INTERVAL, set_long_pressed)
        long_timer.start()
        state["long_timer"] = long_timer

        self._button_states[botao] = state

        # Cancelar clique simples pendente se houver
        if botao in self._pending_click_timers:
            self._pending_click_timers[botao].cancel()
            del self._pending_click_timers[botao]

        # Agenda clique simples só se não for second click e sem combo detectado ainda
        if not is_second_click:

            def emitir_clique_simples():
                current_state = self._button_states.get(botao)
                if current_state is None or (
                    not current_state["long_pressed"]
                    and not current_state["repeat_active"]
                    and not current_state.get("combo_disparado", False)
                ):
                    self.executa_acao(botao, state=1)
                self._pending_click_timers.pop(botao, None)

            click_timer = threading.Timer(
                self.LONG_PRESS_INTERVAL, emitir_clique_simples
            )
            click_timer.start()
            self._pending_click_timers[botao] = click_timer

    def _repeat_timer(self, botao):
        with self._lock:
            state = self._button_states.get(botao)
            if not state or not state.get("repeat_active"):
                return
            button = self._build_button_name(botao, repeat=True)
        self.executa_acao(button, state=1)
        # Reagenda fora do lock para evitar deadlock
        t = threading.Timer(self.REPEAT_INTERVAL, self._repeat_timer, args=(botao,))
        with self._lock:
            # Verifica novamente antes de armazenar/agendar
            state = self._button_states.get(botao)
            if not state or not state.get("repeat_active"):
                return
            state["repeat_timer"] = t
            t.start()

    def _on_button_release(self, botao):
        state = self._button_states.pop(botao, None)
        if not state:
            return

        if state.get("combo_disparado"):
            # não fazer nada no release
            return

        if "long_timer" in state:
            state["long_timer"].cancel()

        with self._lock:
            if "repeat_timer" in state:
                state["repeat_timer"].cancel()

        # Libera combo
        for k in list(self._button_states):
            if self._button_states[k].get("combo_disparado"):
                self._ctx.log(f"[Combo] {k} liberado (parte de combo)")
                self._button_states[k]["combo_disparado"] = False

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
            self.executa_acao(f"{botao}++", state=1)
            return

        # Caso 2: já emitiu long ou repeat, então não faz mais nada
        if state["long_pressed"] or state["repeat_active"]:
            return

    def monitor(self):
        self.start_event_blocking()

    def executa_acao(self, botao, state):
        ow = self._ctx.overlay_window
        current_mode = self._ctx.overlay_window.current_mode()
        match botao:
            case "G1+G2":
                pass
            case "G1":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEDOWN)
                elif current_mode in [MODE_LASER]:
                    ow.next_color()
            case "G1++":
                if current_mode in [MODE_LASER]:
                    ow.next_color()
            case "G1+long":
                self.emit_key_chord(self._ctx.ui, [uinput.KEY_LEFTSHIFT, uinput.KEY_F5])
            case "G1+repeat":
                if current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(+1)
                elif current_mode == MODE_LASER:
                    ow.change_laser_size(+1)
            case "G2":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_PAGEUP)

                elif current_mode in [MODE_LASER]:
                    ow.next_color(-1)
            case "G2++":
                if current_mode in [MODE_LASER]:
                    ow.next_color()
            case "G2+long":
                if current_mode != MODE_MOUSE:
                    ow.set_mouse_mode()
                else:
                    ow.set_last_pointer_mode()
            case "G2+repeat":
                if current_mode == MODE_SPOTLIGHT:
                    ow.change_spot_radius(-1)
                elif current_mode == MODE_LASER:
                    ow.change_laser_size(-1)
            case "A":
                pass
            case "A++":
                pass
            case "A+long":
                pass
            case "B":
                if current_mode == MODE_MOUSE:
                    self.emit_key_press(self._ctx.ui, uinput.KEY_B)
            case "B++":
                pass
            case "B+long":
                ow.set_laser_mode()
            case "B+repeat":
                pass
            case "C":
                ow.switch_mode()
            case "C++":
                ow.switch_mode(step=-1)
            case "C+long":
                ow.set_spotlight_mode()
            case "C+repeat":
                pass
            case "D":
                pass
            case "D++":
                pass
            case "D+long":
                pass
            case "D+repeat":
                pass

    def handle_event(self, event):
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
