import evdev
import pyudev
import threading
import time
import select
import uinput

from pyspotlight.utils import MODE_LASER, MODE_MOUSE, MODE_PEN, MODE_SPOTLIGHT
from .pointerdevice import BasePointerDevice


class VRBoxPointerDevice(BasePointerDevice):
    VENDOR_ID = "248a"
    PRODUCT_ID = "8266"

    def __init__(self, hidraw_path=None, app_ctx=None):
        super().__init__(app_ctx, hidraw_path)
        self.devices = []
        self.running = False
        self.ctx.ui = self.create_virtual_device(name="VR-BOX Virtual Presenter")

    @staticmethod
    def match_device(device):
        vidpid = f"{VRBoxPointerDevice.VENDOR_ID.upper()}:{VRBoxPointerDevice.PRODUCT_ID.upper()}"
        # Checa se o sys_path tem o vidpid
        return device.sys_path and vidpid in device.sys_path

    def monitor(self):
        self.running = True
        self.devices = self.find_all_vrbox_event_devices()
        if not self.devices:
            self.ctx.log("⚠️ Nenhum dispositivo VR BOX encontrado via evdev.")
            return

        threading.Thread(target=self.listen_all, daemon=True).start()

    def find_all_vrbox_event_devices(self):
        context = pyudev.Context()
        devs = []
        vidpid = f"{self.VENDOR_ID.upper()}:{self.PRODUCT_ID.upper()}"
        for device in context.list_devices(subsystem="input"):
            if device.device_node and "event" in device.device_node:
                if vidpid in device.sys_path:
                    try:
                        evdev_dev = evdev.InputDevice(device.device_node)
                        self.ctx.log(
                            f"🎮 VR BOX detectado: {evdev_dev.path} ({evdev_dev.name})"
                        )
                        devs.append(evdev_dev)
                    except Exception as e:
                        self.ctx.log(f"⚠️ Erro ao acessar {device.device_node}: {e}")
        return devs

    def listen_all(self):
        self.ctx.log("📥 Monitorando eventos VR BOX com select")
        fd_to_device = {dev.fd: dev for dev in self.devices}

        while self.running and fd_to_device:
            rlist, _, _ = select.select(fd_to_device.keys(), [], [], 1.0)
            for fd in rlist:
                dev = fd_to_device.get(fd)
                if dev is None:
                    continue
                try:
                    for event in dev.read():
                        if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                            self.handle_key(event.code)
                        elif event.type == evdev.ecodes.EV_REL:
                            self.ctx.overlay_window.notify_activity()
                            self.ctx.ui.emit((event.type, event.code), event.value)
                        self.ctx.log(str(evdev.categorize(event)))
                except OSError as e:
                    if e.errno == 19:  # No such device
                        self.ctx.log(f"⚠️ Dispositivo desconectado: {dev.path}")
                        try:
                            dev.close()
                        except Exception:
                            pass
                        fd_to_device.pop(fd, None)

    def handle_key(self, code):
        ow = self.ctx.overlay_window
        mode = ow.current_mode()

        match code:
            case evdev.ecodes.KEY_P:
                ow.switch_mode(direct_mode=MODE_PEN)
            case evdev.ecodes.KEY_L:
                ow.switch_mode(direct_mode=MODE_LASER)
            case evdev.ecodes.KEY_S:
                ow.switch_mode(direct_mode=MODE_SPOTLIGHT)
            case evdev.ecodes.KEY_C:
                ow.clear_drawing()
            case evdev.ecodes.KEY_PAGEUP:
                ow.zoom(+1)
            case evdev.ecodes.KEY_PAGEDOWN:
                ow.zoom(-1)
            case evdev.ecodes.KEY_B:
                self.emit_key_press(self.ctx.ui, uinput.KEY_B)
            case evdev.ecodes.KEY_ESC:
                self.emit_key_press(self.ctx.ui, uinput.KEY_ESC)
            case _:
                self.ctx.log(f"🔘 Tecla VR BOX não mapeada: {code}")
