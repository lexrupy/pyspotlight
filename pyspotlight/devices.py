import os
import pyudev
import glob
import threading

from pyspotlight.genericvrbox import GenericVRBoxPointer
from pyspotlight.baseusorangedotai import BaseusOrangeDotAI


DEVICE_CLASSES = {
    BaseusOrangeDotAI,
    GenericVRBoxPointer,
}


class DeviceMonitor:
    def __init__(self, context):
        self._ctx = context
        self._monitored_devices = {}
        self._hotplug_callbacks = []

    def start_monitoring(self):
        self.monitor_usb_hotplug()
        # Lança monitoramento dos dispositivos já conectados
        hidraws = self.find_known_devices()
        if hidraws:
            for path, cls in hidraws:
                self.add_monitored_device(cls, path)
        else:
            self._ctx.log("* Nenhum dispositivo compatível encontrado.")

    def add_monitored_device(self, cls, path=None):
        if cls not in self._monitored_devices:
            dev = cls(app_ctx=self._ctx, hidraw_path=path)
            threading.Thread(target=dev.monitor, daemon=True).start()
            self._monitored_devices[cls] = dev
            self._notify_callbacks()
            self._ctx.log(f"Adicionando dispositivo: {cls.__name__} com path {path}")
        else:
            dev = self._monitored_devices[cls]
            dev.add_known_path(path)
            # dev.ensure_monitoring()
            self._ctx.log(
                f"Dispositivo {cls.__name__} já monitorado, adicionando path: {path}"
            )

    def remove_monitored_device(self, dev):
        # Encontra a classe correspondente à instância
        for cls, inst in list(self._monitored_devices.items()):
            if inst is dev:
                del self._monitored_devices[cls]
                break
        self._notify_callbacks()

    def remove_monitored_device_path(self, path):
        for dev in self.get_monitored_devices():
            if path in dev._known_paths:
                self._ctx.log(f"- Removendo path {path} do dispositivo {dev}")
                dev._known_paths.remove(path)
                if not dev._known_paths:
                    self._ctx.log(
                        f"* Nenhum dispositivo restante para monitorar. Encerrando thread."
                    )
                    self.remove_monitored_device(dev)
                break

    def get_monitored_devices(self):
        return list(self._monitored_devices.values())

    # def get_compatible_devices(self):
    #     return [d for d in self.devices if d.is_compatible()]

    def register_hotplug_callback(self, callback):
        self._hotplug_callbacks.append(callback)

    def _notify_callbacks(self):
        for cb in self._hotplug_callbacks:
            cb()

    def find_known_devices(self):
        devices = []
        for path in glob.glob("/dev/hidraw*"):
            for cls in DEVICE_CLASSES:
                if cls.is_known_device(path):
                    devices.append((path, cls))
        for path in glob.glob("/dev/input/*"):
            if not os.path.isfile(path):
                continue
            for cls in DEVICE_CLASSES:
                if cls.is_known_device(path):
                    devices.append((path, cls))

        return devices

    def hotplug_callback(self, action, device):
        path = device.device_node
        if not path:
            return

        if action == "add":
            if path.startswith("/dev/hidraw") or path.startswith("/dev/input"):
                for dev in self.get_monitored_devices():
                    if dev.known_path(path):
                        return  # já monitorado
                for cls in DEVICE_CLASSES:
                    if cls.is_known_device(path):
                        self._ctx.log(
                            f"+ Novo dispositivo compatível conectado: {path}"
                        )
                        self.add_monitored_device(cls, path)
        elif action == "remove":
            for dev in self.get_monitored_devices():
                self._ctx.log(
                    f"Verificando dispositivo {dev.__class__.__name__} com paths {dev._known_paths}"
                )
                if dev.known_path(path):
                    self.remove_monitored_device_path(path)

    def monitor_usb_hotplug(self):
        def monitor_loop():
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by("input")
            monitor.start()

            for device in iter(monitor.poll, None):
                action = device.action  # 'add' ou 'remove'
                self.hotplug_callback(action, device)

        threading.Thread(target=monitor_loop, daemon=True).start()
