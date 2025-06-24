import pyudev
import time
import glob
import threading


from .baseusorangedotai import BaseusOrangeDotAI


DEVICE_CLASSES = {
    BaseusOrangeDotAI,
}


class DeviceMonitor:
    def __init__(self, context):
        self._ctx = context
        self._monitored_devices = set()

    def start_monitoring(self):
        self.monitor_usb_hotplug()
        # Lança monitoramento dos dispositivos já conectados
        hidraws = self.find_known_hidraws()
        if hidraws:
            for path, cls in hidraws:
                dev = cls(app_ctx=self._ctx, hidraw_path=path)
                threading.Thread(target=dev.monitor, daemon=True).start()
                self._monitored_devices.add(path)
            self._ctx.log("🟢 Dispositivos compatíveis encontrados e monitorados.")
        else:
            self._ctx.log("⚠️ Nenhum dispositivo compatível encontrado.")

        self._ctx.log(str(self._monitored_devices))

    def find_known_hidraws(self):
        devices = []
        for path in glob.glob("/dev/hidraw*"):
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
                if path in self._monitored_devices:
                    return  # já monitorado
                for cls in DEVICE_CLASSES:
                    if cls.is_known_device(path):
                        self._ctx.log(
                            f"➕ Novo dispositivo HID compatível conectado: {path}"
                        )
                        dev = cls(app_ctx=self._ctx, hidraw_path=path)
                        t = threading.Thread(target=dev.monitor, daemon=True)
                        t.start()
                        self._monitored_devices.add(path)

        elif action == "remove":
            if path in self._monitored_devices:
                self._ctx.log(f"➖ Dispositivo HID removido: {path}")
                self._monitored_devices.remove(path)

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
