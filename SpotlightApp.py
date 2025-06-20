import sys
import threading
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QComboBox,
)
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtCore import Qt
from screeninfo import get_monitors
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem
from pyspotlight.appcontext import AppContext
from pyspotlight.devices import DeviceMonitor
from pyspotlight.spotlight import SpotlightOverlayWindow
from pyspotlight.utils import capture_monitor_screenshot


class PySpotlightApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Py-Spotlight")
        self.setGeometry(100, 100, 800, 500)

        self.running = True
        self.icon = None

        self.ctx = AppContext(
            selected_screen=0,
            log_function=self.append_log,
        )
        self.create_overlay()
        # self.spotlight_window = SpotlightOverlayWindow(self.ctx)
        self.device_monitor = DeviceMonitor(self.ctx)

        self.init_ui()
        self.refresh_screens()
        self.start_device_monitor()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        title = QLabel("Py-Spotlight")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        main_layout.addWidget(title)

        self.screen_combo = QComboBox()
        # refresh_button = QPushButton("Reiniciar no monitor selecionado")
        # refresh_button.clicked.connect(self.change_screen)
        self.screen_combo.currentIndexChanged.connect(self.update_selected_screen)

        monitor_layout = QHBoxLayout()
        monitor_layout.addWidget(QLabel("Selecionar monitor:"))
        monitor_layout.addWidget(self.screen_combo)

        refresh_monitors_button = QPushButton("Atualizar Monitores")
        refresh_monitors_button.clicked.connect(self.refresh_screens)
        monitor_layout.addWidget(refresh_monitors_button)
        # monitor_layout.addWidget(refresh_button)
        main_layout.addLayout(monitor_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: black; color: lime;")
        main_layout.addWidget(self.log_text)

        button_layout = QHBoxLayout()
        clear_button = QPushButton("Limpar Log")
        clear_button.clicked.connect(self.clear_log)
        hide_button = QPushButton("Ocultar")
        hide_button.clicked.connect(self.hide_to_tray)
        exit_button = QPushButton("Encerrar")
        exit_button.clicked.connect(self.exit_app)

        button_layout.addWidget(clear_button)
        button_layout.addWidget(hide_button)
        button_layout.addWidget(exit_button)

        main_layout.addLayout(button_layout)

    def create_overlay(self):
        screen_index = self.ctx.selected_screen
        screens = QGuiApplication.screens()
        geometry = screens[screen_index].geometry()
        screenshot, geometry = capture_monitor_screenshot(screen_index)

        if self.ctx.overlay_window:
            self.ctx.overlay_window.close()

        self.ctx.overlay_window = SpotlightOverlayWindow(
            context=self.ctx,
            screenshot=screenshot,
            screen_geometry=geometry,
            monitor_index=screen_index,
        )
        # self.ctx.overlay_window.showFullScreen()

    def clear_log(self):
        self.log_text.clear()

    def append_log(self, message):
        self.log_text.append(message)

    def refresh_screens(self):
        current_index = self.screen_combo.currentIndex()
        self.screens = get_monitors()
        self.screen_combo.clear()
        for i, m in enumerate(self.screens):
            text = f"{i}: {m.width}x{m.height} @ {m.x},{m.y}"
            if m.is_primary:
                text += " [Primário]"
            self.screen_combo.addItem(text)
        if 0 <= current_index < self.screen_combo.count():
            self.screen_combo.setCurrentIndex(current_index)

    def update_selected_screen(self):
        idx = self.screen_combo.currentIndex()
        self.ctx.selected_screen = idx
        self.create_overlay()
        self.append_log(f"🖥️ Tela selecionada: {idx}")

    def start_device_monitor(self):
        self.device_monitor.monitor_usb_hotplug()
        # Lança monitoramento dos dispositivos já conectados
        hidraws = self.device_monitor.find_known_hidraws()
        if hidraws:
            for path, dev_info in hidraws:
                cls = dev_info["CLASS"]
                dev = cls(path, app_ctx=self.ctx)
                threading.Thread(target=dev.monitor, daemon=True).start()
            self.append_log("🟢 Dispositivos compatíveis encontrados e monitorados.")
        else:
            self.append_log("⚠️ Nenhum dispositivo compatível encontrado.")

        dispositivos = self.device_monitor.find_all_event_devices_for_known()
        if dispositivos:
            t = threading.Thread(
                target=self.device_monitor.prevent_key_and_mouse_events,
                args=(dispositivos,),
                daemon=True,
            )
            t.start()

    def hide_to_tray(self):
        self.hide()
        if self.icon is None:
            self.create_tray_icon()

    def create_tray_icon(self):
        def restore():
            self.show()
            if self.icon:
                self.icon.stop()
                self.icon = None

        image = self.create_image()
        self.icon = Icon("Py-Spotlight", image, "Py-Spotlight")
        self.icon.menu = Menu(MenuItem("Restaurar", lambda: restore()))

        threading.Thread(target=self.icon.run, daemon=True).start()

    def create_image(self):
        image = Image.new("RGB", (64, 64), "black")
        draw = ImageDraw.Draw(image)
        draw.ellipse((16, 16, 48, 48), fill="lime")
        return image

    def exit_app(self):
        self.running = False
        if self.icon:
            self.icon.stop()
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PySpotlightApp()
    window.show()
    sys.exit(app.exec_())
