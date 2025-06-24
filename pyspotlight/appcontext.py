import uinput


class AppContext:
    def __init__(
        self,
        spx_proc=None,
        selected_screen=0,
        log_function=None,
        overlay_window=None,
    ):
        self._spx_proc = spx_proc
        self._selected_screen = selected_screen
        self._log_function = log_function
        self._overlay_window = overlay_window

        self._ui = uinput.Device(
            [
                uinput.REL_X,
                uinput.REL_Y,
                uinput.BTN_LEFT,
                uinput.BTN_RIGHT,
                uinput.KEY_B,
                uinput.KEY_PAGEUP,
                uinput.KEY_PAGEDOWN,
                uinput.KEY_ESC,
                # uinput.KEY_LEFTCTRL,
                uinput.KEY_F5,
                uinput.KEY_SPACE,
                uinput.KEY_LEFTSHIFT,
                uinput.KEY_VOLUMEUP,
                uinput.KEY_VOLUMEDOWN,
            ],
            name="Virtual Spotlight Mouse",
        )

    @property
    def ui(self):
        return self._ui

    @ui.setter
    def ui(self, uid):
        self._ui = uid

    @property
    def spx_proc(self):
        return self._spx_proc

    @spx_proc.setter
    def spx_proc(self, spxc):
        self._spx_proc = spxc

    @property
    def selected_screen(self):
        return self._selected_screen

    @selected_screen.setter
    def selected_screen(self, scr):
        self._selected_screen = scr

    @property
    def log_function(self):
        return self._log_function

    @log_function.setter
    def log_function(self, func):
        self._log_function = func

    @property
    def overlay_window(self):
        return self._overlay_window

    @overlay_window.setter
    def overlay_window(self, window):
        self._overlay_window = window

    def log(self, message):
        if self._log_function:
            self._log_function(message)
