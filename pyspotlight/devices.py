import evdev
import pyudev
import os
import time
import glob
import uinput
import subprocess
import select
import threading

from .baseusorangedotai import BaseusOrangeDotAI

# # Lista de dispositivos conhecidos
# DEVICE_IDS = [
#     {"VENDOR_ID": 0xABC8, "PRODUCT_ID": 0xCA08, "CLASS": BaseusOrangeDotAI},
#     # Adicione outros pares vendor/product aqui
# ]

DEVICE_CLASSES = {
    BaseusOrangeDotAI,
}


class DeviceMonitor:
    def __init__(self, context):
        self._ctx = context
        self._monitored_devices = set()

    def _iniciar_bloqueio_eventos(self):
        if not self._event_thread or not self._event_thread.is_alive():
            devs = self.find_all_event_devices_for_known()
            if devs:
                self._event_thread = threading.Thread(
                    target=self.prevent_key_and_mouse_events,
                    args=(devs,),
                    daemon=True,
                )
                self._event_thread.start()
            else:
                self._ctx.log(
                    "⚠️ Nenhum dispositivo de entrada conhecido encontrado para bloquear."
                )

    def start(self):
        self.monitor_usb_hotplug()
        # Inicia monitoramento hotplug (funcionará mesmo sem dispositivos)
        # Encontra e inicia monitoramento de dispositivos já conectados
        hidraws = self.find_known_hidraws()
        if hidraws:
            for path, cls in hidraws:
                dev = cls(app_ctx=self._ctx, hidraw_path=path)
                threading.Thread(target=dev.monitor, daemon=True).start()
        else:
            self._ctx.log(
                "⚠️ Nenhum dispositivo compatível encontrado. Aguardando conexão..."
            )

        dispositivos_para_bloquear = self.find_all_event_devices_for_known()
        if dispositivos_para_bloquear:
            self._iniciar_bloqueio_eventos()

        try:
            while True:
                time.sleep(1)
        except Exception as e:
            self._ctx.log(
                f"❌ Erro inesperado no loop principal: {e}"
            )  # self._ctx.log("Encerrando monitoramento de dispositivos HID.")

    def start_monitoring(self):
        self.monitor_usb_hotplug()
        # Lança monitoramento dos dispositivos já conectados
        hidraws = self.find_known_hidraws()
        if hidraws:
            for path, cls in hidraws:
                dev = cls(app_ctx=self._ctx, hidraw_path=path)
                threading.Thread(target=dev.monitor, daemon=True).start()
            self._ctx.log("🟢 Dispositivos compatíveis encontrados e monitorados.")
        else:
            self._ctx.log("⚠️ Nenhum dispositivo compatível encontrado.")

        dispositivos = self.find_all_event_devices_for_known()
        if dispositivos:
            t = threading.Thread(
                target=self.prevent_key_and_mouse_events,
                args=(dispositivos,),
                daemon=True,
            )
            t.start()

    def find_known_hidraws(self):
        devices = []
        for path in glob.glob("/dev/hidraw*"):
            for cls in DEVICE_CLASSES:
                if cls.is_known_device(path):
                    devices.append((path, cls))
        return devices

    def find_evdev_path_from_hidraw(self, hidraw_path):
        # Mapeia /dev/hidrawX para /dev/input/eventX
        try:
            base_name = os.path.basename(hidraw_path)
            sys_path = f"/sys/class/hidraw/{base_name}/device"
            input_base = os.path.join(sys_path, "input")
            inputs = os.listdir(input_base)
            if not inputs:
                return None
            input_path = os.path.join(input_base, inputs[0])
            event_devices = [f for f in os.listdir(input_path) if f.startswith("event")]
            if not event_devices:
                return None
            event_path = os.path.join("/dev/input", event_devices[0])
            return event_path
        except Exception:
            return None

    def find_all_event_devices_for_known(self):
        devices = []
        for path in glob.glob("/dev/input/event*"):
            for cls in DEVICE_CLASSES:
                if cls.is_known_device(path):
                    try:
                        devices.append(evdev.InputDevice(path))
                        self._ctx.log(f"🟢 Encontrado device de entrada: {path}")
                    except Exception as e:
                        self._ctx.log(f"⚠️ Erro ao acessar {path}: {e}")
        return devices

    def hotplug_callback(self, action, device):

        path = device.device_node
        if not path:
            return

        if action == "add":
            if path.startswith("/dev/hidraw"):
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

            elif path.startswith("/dev/input/event"):
                for cls in DEVICE_CLASSES:
                    if cls.is_known_device(path):
                        self._ctx.log(
                            f"🆕 Dispositivo de entrada compatível conectado: {path}"
                        )
                        # Reinicia o bloqueio de eventos se necessário
                        self._iniciar_bloqueio_eventos()
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

    def prevent_key_and_mouse_events(self, devices):
        fd_para_dev = {}
        for dev in devices:
            try:
                dev.grab()
                fd_para_dev[dev.fd] = dev
                self._ctx.log(f"🟢 Monitorado: {dev.path}")
            except Exception as e:
                self._ctx.log(
                    f"❌ Erro ao monitorar dispositivo {dev.path}: {e}. Tente executar como root ou ajuste as regras udev."
                )
        self._ctx.log("🟢 Monitorando dispositivos...")

        if hasattr(self._ctx, "ui") and self._ctx.ui:
            try:
                self._ctx.log("ℹ️ Interface uinput anterior substituída.")
                self._ctx.ui.close()  # Fecha explicitamente, mesmo não sendo obrigatório
            except Exception as e:
                self._ctx.log(f"⚠️ Erro ao fechar uinput anterior: {e}")

        self._ctx.ui = uinput.Device(
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

        try:
            while True:
                r, _, _ = select.select(fd_para_dev, [], [])
                for fd in r:
                    dev = fd_para_dev.get(fd)
                    if dev is None:
                        continue
                    try:
                        for event in dev.read():
                            if event.type == evdev.ecodes.EV_REL or (
                                event.type == evdev.ecodes.EV_KEY
                                and event.code
                                in (
                                    evdev.ecodes.BTN_LEFT,
                                    evdev.ecodes.BTN_RIGHT,
                                )
                            ):
                                # Repassa evento virtual
                                self._ctx.ui.emit((event.type, event.code), event.value)

                    except OSError as e:
                        if e.errno == 19:  # No such device
                            self._ctx.log(f"⚠️ Dispositivo desconectado: {dev.path}")
                            # Remove dispositivo da lista para não monitorar mais
                            fd_para_dev.pop(fd, None)
                            try:
                                dev.ungrab()
                            except Exception:
                                pass
                            # Opcional: se não há mais dispositivos, pode encerrar ou esperar
                            if not fd_para_dev:
                                self._ctx.log(
                                    "Nenhum dispositivo restante para monitorar. Encerrando thread."
                                )
                                return
                        else:
                            raise

        except KeyboardInterrupt:
            self._ctx.log("\n⏹️ Encerrando monitoramento.")
        finally:
            for dev in devices:
                try:
                    dev.ungrab()
                except Exception:
                    pass
