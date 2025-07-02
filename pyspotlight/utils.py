import mss
from PIL import Image
from PyQt5.QtGui import (
    QImage,
)
from PyQt5.QtCore import QRect


MODE_MOUSE = 0
MODE_SPOTLIGHT = 1
MODE_LASER = 2
MODE_PEN = 3
MODE_MAG_GLASS = 4


MODE_MAP = {
    MODE_MOUSE: "Mouse",
    MODE_SPOTLIGHT: "Spotlight",
    MODE_LASER: "Laser",
    MODE_PEN: "Marcador",
    MODE_MAG_GLASS: "Lente",
}


def pil_to_qimage(pil_img):
    pil_img = pil_img.convert("RGBA")
    data = pil_img.tobytes("raw", "RGBA")
    return QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)


def capture_monitor_screenshot(monitor_index):
    with mss.mss() as sct:
        monitors = sct.monitors
        # monitor_index da GUI (0-based) → monitor_index para mss (1-based)
        mss_index = monitor_index + 1

        if mss_index < 1 or mss_index >= len(monitors):
            mss_index = 1  # fallback para primeiro monitor real

        mon = monitors[mss_index]
        sct_img = sct.grab(mon)
        img = pil_to_qimage(
            Image.frombytes("RGB", sct_img.size, sct_img.rgb).convert("RGBA")
        )
    return img, QRect(mon["left"], mon["top"], mon["width"], mon["height"])
