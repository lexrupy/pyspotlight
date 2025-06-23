import uinput


class BasePointerDevice:
    def __init__(self, app_ctx, hidraw_path=None):
        self.path = hidraw_path
        self.ctx = app_ctx
        self.last_click_time_113 = 0
        self.double_click_interval = 0.3  # segundos para considerar duplo clique

    @staticmethod
    def match_device(device_info):
        """
        Recebe info do dispositivo (path, sysfs, etc) e retorna True se o dispositivo é deste tipo.
        """
        raise NotImplementedError

    @classmethod
    def from_device_info(cls, app_ctx, device_info):
        """
        Cria a instância da classe com as informações do dispositivo.
        """
        return cls(app_ctx, device_info.get("path"))

    def emit_key_press(self, ui, key):
        ui.emit(key, 1)  # Pressiona
        ui.emit(key, 0)  # Solta

    def emit_key_chord(self, ui, keys):
        ui.emit(keys[0], 1)  # Pressiona primeira tecla, ex: SHIFT
        ui.emit(keys[1], 1)  # Pressiona segunda tecla ex: F5
        ui.emit(keys[1], 0)  # Solta segunda tecla
        ui.emit(keys[0], 0)  # Solta primeira tecla

    def create_virtual_device(self, keys=None, name="Virtual Spotlight Mouse"):
        if keys is None:
            keys = [
                uinput.REL_X,
                uinput.REL_Y,
                uinput.BTN_LEFT,
                uinput.BTN_RIGHT,
                uinput.KEY_B,
                uinput.KEY_PAGEUP,
                uinput.KEY_PAGEDOWN,
                uinput.KEY_ESC,
                uinput.KEY_F5,
                uinput.KEY_SPACE,
                uinput.KEY_LEFTSHIFT,
                uinput.KEY_VOLUMEUP,
                uinput.KEY_VOLUMEDOWN,
            ]

        return uinput.Device(keys, name=name)
