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
    QSystemTrayIcon,
    QWidget,
    QComboBox,
    QMenu,
    QAction,
)
from PyQt5.QtGui import QGuiApplication, QPixmap, QPainter, QColor, QIcon, QTextCursor
from PyQt5.QtCore import Qt
from screeninfo import get_monitors
from pyspotlight.appcontext import AppContext
from pyspotlight.devices import DeviceMonitor
from pyspotlight.spotlight import SpotlightOverlayWindow
from pyspotlight.utils import capture_monitor_screenshot
from pyspotlight.settingswindow import SpotlightSettingsWindow
from pyspotlight.infoverlay import InfOverlayWindow
from pyspotlight.utils import MODE_AUTO


class PySpotlightApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Py-Spotlight")

        self.setGeometry(100, 100, 800, 500)

        self.tray_icon = None
        self.create_tray_icon()

        # Quando fechar a janela, ao invés de fechar, esconder
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        self.setMinimumSize(400, 300)

        self.ctx = AppContext(
            selected_screen=0,
            log_function=self.append_log,
            show_info_function=self.mostrar_info_em_monitor_secundario,
        )
        self.create_overlay()

        self.info_overlay = None
        if len(QGuiApplication.screens()) >= 1:
            self.setup_info_overlay()

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

        settings_button = QPushButton("Configurações")
        settings_button.clicked.connect(self.open_settings)

        monitor_layout.addWidget(refresh_monitors_button)
        monitor_layout.addWidget(settings_button)
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

    def create_tray_icon(self):
        # Criar um ícone simples na memória (círculo verde)
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor("lime"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, size, size)
        painter.end()

        icon = QIcon(pixmap)

        self.tray_icon = QSystemTrayIcon(icon, self)
        menu = QMenu()

        restore_action = QAction("Restaurar", self)
        restore_action.triggered.connect(self.show_normal)
        menu.addAction(restore_action)

        exit_action = QAction("Sair", self)
        exit_action.triggered.connect(self.exit_app)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)

        self.tray_icon.activated.connect(self.on_tray_icon_activated)

        self.tray_icon.show()

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

    def setup_info_overlay(self):
        # Pega o monitor que não está sendo usado pelo spotlight
        all_screens = QGuiApplication.screens()
        target_index = 0
        if len(all_screens) > 1:
            target_index = 1 if self.ctx.selected_screen == 0 else 0
        geometry = all_screens[target_index].geometry()
        self.info_overlay = InfOverlayWindow(geometry)

    def mostrar_info_em_monitor_secundario(self, mensagem):
        if self.info_overlay:
            self.info_overlay.show_message(mensagem)

    def clear_log(self):
        self.log_text.clear()

    def append_log(self, message):
        self.log_text.append(message)
        self.log_text.moveCursor(QTextCursor.End)

    def open_settings(self):
        self.settings_window = SpotlightSettingsWindow(self.ctx)
        self.settings_window.show()

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
                dev = cls(app_ctx=self.ctx, hidraw_path=path)
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

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            # Clique simples na bandeja
            if self.isVisible():
                self.hide()
            else:
                self.show_normal()
                self.activateWindow()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self):
        self.hide()
        self.append_log("Janela oculta. Clique no ícone da bandeja para restaurar.")

    def exit_app(self):
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        # Ao clicar no "X", não encerra, só esconde e mantém na bandeja
        event.ignore()
        self.hide_to_tray()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_M:
            self.ctx.overlay_window.switch_mode()
            self.update()
        if key == Qt.Key_A:
            self.ctx.overlay_window.set_auto_mode()
            self.update()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setApplicationName("PySpotlight")
    window = PySpotlightApp()
    window.show()
    sys.exit(app.exec_())
