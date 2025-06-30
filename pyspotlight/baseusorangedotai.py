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
        self._ctx.compatible_modes = [MODE_MOUSE, MODE_SPOTLIGHT, MODE_LASER, MODE_PEN]
        self._last_click_time = {}
        self._last_release_time = {}
        self._pending_click_timers = {}
        self._button_states = {}
        self._lock = threading.Lock()

        self._single_action_buttons = {
            97: "OK",
            98: "OK++",
            99: "OK+long",
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
            100: "LASER",
            103: "HGL",
            106: "PREV",
            108: "NEXT",
            113: "MOUSE",
            116: "MIC",
            120: "VOL_UP",
            121: "VOL_DOWN",
            122: "LNG",
        }

        self._long_press_buttons = {
            100: "LASER",
            120: "VOL_UP",
            121: "VOL_DOWN",
        }

    # def _on_button_press(self, button):
    #     now = time.time()
    #     last_click = self._last_click_time.get(button, 0)
    #     is_double = 0 < (now - last_click) < self.DOUBLE_CLICK_INTERVAL
    #
    #     self._last_click_time[button] = now
    #
    #     state = {
    #         "start_time": now,
    #         "long_pressed": False,
    #     }
    #
    #     self._button_states[button] = state
    #
    #     def single_click():
    #         if not state.get("long_pressed"):
    #             if is_double:
    #                 self.executa_acao(f"{button}++")
    #             else:
    #                 self.executa_acao(button)
    #         self._button_states.pop(button, None)
    #
    #     click_timer = threading.Timer(self.LONG_PRESS_INTERVAL + 0.05, single_click)
    #     click_timer.start()
    #
    #     self._last_release_time[button] = now

    # def _on_button_press(
    #     self,
    #     button,
    # ):
    #     now = time.time()
    #     last_click = self._last_click_time.get(button, 0)
    #     is_double = 0 < (now - last_click) < self.DOUBLE_CLICK_INTERVAL
    #
    #     self._last_click_time[button] = now
    #
    #     state = {
    #         "start_time": now,
    #         "long_pressed": False,
    #     }
    #     self._button_states[button] = state
    #
    #     if is_double:
    #         # Se for duplo clique, cancelar o timer de clique simples do primeiro clique
    #         timer = self._pending_click_timers.pop(button, None)
    #         if timer:
    #             timer.cancel()
    #         self.executa_acao(f"{button}++")
    #         return
    #
    #     # Clique simples (ainda não sabemos se será duplo ou longo)
    #     def single_click():
    #         if not state.get("long_pressed"):
    #             self.executa_acao(button)
    #         self._pending_click_timers.pop(button, None)
    #
    #     click_timer = threading.Timer(self.LONG_PRESS_INTERVAL + 0.05, single_click)
    #     click_timer.start()
    #     self._pending_click_timers[button] = click_timer
    #
    #     self._last_release_time[button] = now

    def _build_button_name(self, button, long_press=False, repeat=False):
        parts = [button]
        if repeat:
            parts.append("repeat")
        elif long_press:
            parts.append("long")
        return "+".join(parts)

    def _on_button_press(self, button):
        now = time.time()
        last_click_time = self._last_click_time.get(button, 0)
        self._last_click_time[button] = now

        is_second_click = 0 < (now - last_click_time) < self.DOUBLE_CLICK_INTERVAL

        # Se for segundo clique, dispara ++ e cancela o anterior
        if is_second_click:
            timer = self._pending_click_timers.pop(button, None)
            if timer:
                timer.cancel()
            self._ctx.log(f"DOUBLE CLICK -> BOTAO: {button}++")
            self.executa_acao(f"{button}++")
            return

        # Caso contrário, agenda clique simples
        def emitir_clique_simples():
            # Garante que nenhum clique duplo ou long foi disparado
            self.executa_acao(button)
            self._pending_click_timers.pop(button, None)

        timer = threading.Timer(self.DOUBLE_CLICK_INTERVAL, emitir_clique_simples)
        self._pending_click_timers[button] = timer
        timer.start()

    def _repeat_timer(self, button):
        with self._lock:
            state = self._button_states.get(button)
            if not state or not state.get("repeat_active"):
                return
            button_name = self._build_button_name(button, repeat=True)
        self.executa_acao(button_name)
        # Reagenda fora do lock para evitar deadlock
        t = threading.Timer(self.REPEAT_INTERVAL, self._repeat_timer, args=(button,))
        with self._lock:
            # Verifica novamente antes de armazenar/agendar
            state = self._button_states.get(button)
            if not state or not state.get("repeat_active"):
                return
            state["repeat_timer"] = t
            t.start()

    def _on_button_release(self, button):
        state = self._button_states.pop(button, None)
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
        last_release = self._last_release_time.get(button, 0)

        self._last_release_time[button] = now

        if (
            last_release > 0
            and (now - last_release) < self.DOUBLE_CLICK_INTERVAL
            and duration < self.LONG_PRESS_INTERVAL
            and not state["long_pressed"]
        ):
            self.executa_acao(f"{button}++")
            return

        # Caso 2: já emitiu long ou repeat, então não faz mais nada
        if state["long_pressed"] or state["repeat_active"]:
            return

        # Cancela qualquer clique simples pendente que ainda não foi cancelado
        timer = self._pending_click_timers.pop(button, None)
        if timer:
            timer.cancel()

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
            # Liberou botão: libera todos os botões que estavam ativos
            for botao in list(self._button_states):
                self._on_button_release(botao)
            return

        button = self.get_button(status_byte)

        if not button:
            return

        self._ctx.log(f"{button}")
        # Estes botoes executam diretamente, sem tratamento
        if button in self._single_action_buttons.values():
            self._ctx.log(f"SINGLE -> BOTAO: {button}")
            self.executa_acao(button)
        else:
            self._on_button_press(button)

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
                if current_mode == MODE_MOUSE:
                    ow.set_last_pointer_mode()
                else:
                    ow.switch_mode()
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
