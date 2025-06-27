import os


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        instance = cls._instances.get(cls)
        if instance is None:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return instance


class BasePointerDevice(metaclass=SingletonMeta):
    def __init__(self, app_ctx, hidraw_path):
        self.path = hidraw_path
        self._ctx = app_ctx
        self._device_name = None
        self._known_paths = []

    def monitor(self):
        raise NotImplementedError

    def ensure_monitoring(self):
        if (
            not hasattr(self, "_event_thread")
            or not self._event_thread
            or not self._event_thread.is_alive()
        ):
            self._ctx.log(f"* Reiniciando monitoramento para {self.display_name()}")
            self.monitor()

    def known_path(self, path):
        return path is not None and path in self._known_paths

    def cleanup_known_paths(self):
        self._known_paths = [p for p in self._known_paths if os.path.exists(p)]

    def add_known_path(self, path):
        self.cleanup_known_paths()
        if path and path not in self._known_paths and os.path.exists(path):
            self._known_paths.append(path)
            self.ensure_monitoring()
            return True
        return False

    def remove_known_path(self, path):
        if path in self._known_paths:
            self._ctx.log(f"- Removendo path {path} de {self.__class__.__name__}")
            self._known_paths.remove(path)
        return len(self._known_paths) == 0  # retorna True se ficou vazio

    # def display_name(self):
    #     name = getattr(self.__class__, "PRODUCT_DESCRIPTION", self._device_name)
    #     if name is None:
    #         name = self.__class__.__name__
    #     return name
    #

    def __str__(self):
        return self.display_name()

    def display_name(self):
        desc = getattr(self.__class__, "PRODUCT_DESCRIPTION", None)
        if desc:
            return desc

        try:
            devname = os.path.basename(self.path or "")
            if devname.startswith("event"):
                path = f"/sys/class/input/{devname}/device/name"
                if os.path.exists(path):
                    return open(path).read().strip()

            elif devname.startswith("hidraw"):
                path = f"/sys/class/hidraw/{devname}/device/uevent"
                if os.path.exists(path):
                    with open(path) as f:
                        for line in f:
                            if line.startswith("HID_NAME="):
                                return line.strip().split("=", 1)[1]
        except Exception as e:
            self._ctx.log(f"[display_name] Erro ao obter nome: {e}")

        return self.__class__.__name__  # Fallback genérico

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
