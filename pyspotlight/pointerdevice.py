class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        instance = cls._instances.get(cls)
        if instance is None:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        # else:
        #     # Chamar o método de reinicialização parcial (se existir)
        #     if hasattr(instance, "initialize"):
        #         instance.initialize(*args, **kwargs)
        return instance


class BasePointerDevice(metaclass=SingletonMeta):
    def __init__(self, app_ctx, hidraw_path):
        self.path = hidraw_path
        self.ctx = app_ctx
        self._known_paths = []

    def monitor(self):
        raise NotImplementedError

    def known_path(self, path):
        return path in self._known_paths

    def add_known_path(self, path):
        if path and path not in self._known_paths:
            self._known_paths.append(path)
            return True
        return False

    def display_name(self):
        return getattr(self.__class__, "PRODUCT_DESCRIPTION", self.__class__.__name__)

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
