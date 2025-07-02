import uinput


class AppContext:
    def __init__(
        self,
        selected_screen=0,
        log_function=None,
        overlay_window=None,
        show_info_function=None,
    ):
        self._selected_screen = selected_screen
        self._log_function = log_function
        self._overlay_window = overlay_window
        self._show_info_function = show_info_function
        self._compatible_modes = []
        self._support_auto_mode = False

        self._active_device = None

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
    def support_auto_mode(self):
        return self._support_auto_mode

    @support_auto_mode.setter
    def support_auto_mode(self, sam):
        self._support_auto_mode = sam

    @property
    def selected_screen(self):
        return self._selected_screen

    @selected_screen.setter
    def selected_screen(self, scr):
        self._selected_screen = scr

    @property
    def compatible_modes(self):
        return self._compatible_modes

    @compatible_modes.setter
    def compatible_modes(self, modes):
        self._compatible_modes = modes

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

    @property
    def show_info_function(self):
        return self._show_info_function

    @show_info_function.setter
    def show_info_function(self, func):
        self._show_info_function = func

    def set_active_device(self, device):
        if self._active_device == device:
            return

        # Para dispositivo ativo anterior
        if self._active_device:
            self._active_device.stop()

        self._active_device = device

        if device:
            device.ensure_monitoring()

    def log(self, message):
        if self._log_function:
            self._log_function(message)

    def show_info(self, message):
        if self._show_info_function:
            self._show_info_function(message)
