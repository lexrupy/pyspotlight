# infooverlay.py

from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtGui import QFont, QColor, QPainter, QFontMetrics
from PyQt5.QtCore import Qt, QRect, QPoint


class InfOverlayWindow(QWidget):
    def __init__(self, screen_geometry):
        super().__init__()
        self.screen_geometry = screen_geometry

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: white;")
        self.font = QFont("Arial", 64, QFont.Bold)
        self.label.setFont(self.font)

    def show_message(self, text):
        self.label.setText(text)

        # Calcula o tamanho da janela com base no texto
        metrics = QFontMetrics(self.font)
        text_width = metrics.horizontalAdvance(text)
        text_height = metrics.height()

        padding_x = 100
        padding_y = 60

        window_width = text_width + padding_x
        window_height = text_height + padding_y

        # Centraliza no monitor de destino
        screen_center = self.screen_geometry.center()
        top_left = QPoint(
            screen_center.x() - window_width // 2,
            screen_center.y() - window_height // 2,
        )

        self.setGeometry(QRect(top_left, self.size()))
        self.resize(window_width, window_height)
        self.label.resize(window_width, window_height)
        self.show()

    def paintEvent(self, event):
        # Desenha fundo preto translúcido
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 0, 0, 180))  # preto translúcido
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 20, 20)


# class InfOverlayController(QObject):
#     show_requested = pyqtSignal(str, int)
#
#     def __init__(self, overlay: InfOverlayWindow):
#         super().__init__()
#         self.overlay = overlay
#         self.show_requested.connect(self.overlay.show_message)
#
#     def show_message(self, text, duration=2000):
#         self.show_requested.emit(text, duration)
