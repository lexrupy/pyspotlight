import os
import threading
import subprocess
import select
import glob
import evdev


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        instance = cls._instances.get(cls)
        if instance is None:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return instance


class BasePointerDevice(metaclass=SingletonMeta):
    VENDOR_ID = None
    PRODUCT_ID = None

    def __init__(self, app_ctx, hidraw_path):
        self.path = hidraw_path
        self._stop_event = threading.Event()
        self._stop_hidraw_event = threading.Event()
        self._event_thread = None
        self._hidraw_thread = None
        self._ctx = app_ctx
        self._device_name = None
        self._known_paths = []

        self.add_known_path(hidraw_path)
        for device in self.find_all_event_devices_for_known():
            self.add_known_path(device.path)

    def start_event_blocking(self):
        if not self._event_thread or not self._event_thread.is_alive():
            self._stop_event.clear()
            devs = self.find_all_event_devices_for_known()
            if devs:
                self._event_thread = threading.Thread(
                    target=self.read_input_events,
                    args=(devs,),
                    daemon=True,
                )
                self._event_thread.start()
            else:
                self._ctx.log(
                    "* Nenhum dispositivo de entrada conhecido encontrado para bloquear."
                )

    def find_all_event_devices_for_known(self):
        devices = []
        for path in glob.glob("/dev/input/event*"):
            if self.__class__.is_known_device(path):
                try:
                    devices.append(evdev.InputDevice(path))
                    self._ctx.log(f"* Encontrado device de entrada: {path}")
                except Exception as e:
                    self._ctx.log(f"* Erro ao acessar {path}: {e}")
        return devices

    def monitor(self):
        self.start_event_blocking()
        self.start_hidraw_monitoring()

    def start_hidraw_monitoring(self):
        pass

    def stop_hidraw_monitoring(self):
        self._stop_hidraw_event.set()

    def stop_event_blocking(self):
        self._stop_event.set()
        if self._event_thread and self._event_thread.is_alive():
            self._event_thread.join(
                timeout=1
            )  # espera a thread encerrar (timeout opcional)

    def stop(self):
        self.stop_event_blocking()
        self.stop_hidraw_monitoring()

    def ensure_monitoring(self):
        if (
            not hasattr(self, "_event_thread")
            or not self._event_thread
            or not self._event_thread.is_alive()
        ):
            self._ctx.log(f"* Monitorando {self.display_name()}")
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
    def device_filter(cls, device_info, udevadm_output) -> bool:
        return True

    @classmethod
    def is_known_device(cls, device_info):
        try:
            output = subprocess.check_output(
                ["udevadm", "info", "-a", "-n", device_info], text=True
            ).lower()
            vid = f"{cls.VENDOR_ID:04x}"
            pid = f"{cls.PRODUCT_ID:04x}"
            known_device = vid in output and pid in output
            return known_device and cls.device_filter(device_info, output)
        except subprocess.CalledProcessError:
            return False

    def emit_key_press(self, key):
        ui = self._ctx.ui
        ui.emit(key, 1)  # Pressiona
        ui.emit(key, 0)  # Solta

    def emit_key_chord(self, keys):
        ui = self._ctx.ui
        ui.emit(keys[0], 1)  # Pressiona primeira tecla, ex: SHIFT
        ui.emit(keys[1], 1)  # Pressiona segunda tecla ex: F5
        ui.emit(keys[1], 0)  # Solta segunda tecla
        ui.emit(keys[0], 0)  # Solta primeira tecla

    def handle_event(self, event):
        pass

    def read_input_events(self, devices):
        while not self._stop_event.is_set():
            fd_para_dev = {}
            for dev in devices:
                try:
                    dev.grab()
                    fd_para_dev[dev.fd] = dev
                    self._ctx.log(f"* Monitorado: {dev.path}")
                except Exception as e:
                    self._ctx.log(
                        f"* Erro ao monitorar dispositivo {dev.path}: {e}. Tente executar como root ou ajuste as regras udev."
                    )
            self._ctx.log("* Monitorando dispositivos...")

            try:
                while True:
                    r, _, _ = select.select(fd_para_dev, [], [], 0.1)
                    for fd in r:
                        dev = fd_para_dev.get(fd)
                        if dev is None:
                            continue
                        try:
                            for event in dev.read():
                                self.handle_event(event)

                        except OSError as e:
                            if e.errno == 19:  # No such device
                                self._ctx.log(f"- Dispositivo desconectado: {dev.path}")
                                # Remove dispositivo da lista para não monitorar mais
                                fd_para_dev.pop(fd, None)
                                try:
                                    dev.ungrab()
                                except Exception:
                                    pass
                                # Opcional: se não há mais dispositivos, pode encerrar ou esperar
                                if not fd_para_dev:
                                    self._ctx.log(
                                        "* Nenhum dispositivo restante para monitorar. Encerrando thread."
                                    )
                                    return
                            else:
                                raise

            except KeyboardInterrupt:
                self._ctx.log("\n* Encerrando monitoramento.")
            finally:
                for dev in devices:
                    try:
                        dev.ungrab()
                    except Exception:
                        pass
