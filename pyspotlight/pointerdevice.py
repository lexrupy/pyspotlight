from abc import abstractmethod


class BasePointerDevice:
    def __init__(self, app_ctx, hidraw_path):
        self.path = hidraw_path
        self.ctx = app_ctx

    @abstractmethod
    def monitor(self):
        raise NotImplementedError

    @classmethod
    def is_known_device(cls, device_info):
        raise NotImplementedError

    def emit_key_press(self, ui, key):
        ui.emit(key, 1)  # Pressiona
        ui.emit(key, 0)  # Solta

    def emit_key_chord(self, ui, keys):
        ui.emit(keys[0], 1)  # Pressiona primeira tecla, ex: SHIFT
        ui.emit(keys[1], 1)  # Pressiona segunda tecla ex: F5
        ui.emit(keys[1], 0)  # Solta segunda tecla
        ui.emit(keys[0], 0)  # Solta primeira tecla
