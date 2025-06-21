from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QSpinBox,
    QColorDialog,
    QDoubleSpinBox,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QFrame,
)
from PyQt5.QtGui import QColor


class SpotlightSettingsWindow(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("Configurações do PySpotlight")
        self.setMinimumSize(500, 500)
        self.build_ui()
        self.spot_color = QColor(0, 0, 0, 255)
        self.laser_color = QColor(255, 0, 0, 200)
        self.pen_color = QColor(255, 0, 0, 255)

    def build_ui(self):
        layout = QVBoxLayout()

        # ======== SPOTLIGHT ========
        spotlight_group = QGroupBox("Spotlight")
        spot_layout = QVBoxLayout()

        # Raio
        radius_layout = QHBoxLayout()
        radius_layout.addWidget(QLabel("Raio (px):"))
        self.spot_radius_spin = QSpinBox()
        self.spot_radius_spin.setRange(10, 1000)
        self.spot_radius_spin.setValue(200)
        radius_layout.addWidget(self.spot_radius_spin)
        spot_layout.addLayout(radius_layout)

        # Cor + preview
        color_layout = QHBoxLayout()
        self.spot_color_btn = QPushButton("Cor do overlay")
        self.spot_color_btn.clicked.connect(self.select_spotlight_color)
        self.spot_color_display = self.create_color_display(QColor("black"))
        color_layout.addWidget(self.spot_color_btn)
        color_layout.addWidget(self.spot_color_display)
        spot_layout.addLayout(color_layout)

        # Opacidade
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacidade do overlay:"))
        self.spot_opacity_spin = QDoubleSpinBox()
        self.spot_opacity_spin.setRange(0.0, 1.0)
        self.spot_opacity_spin.setSingleStep(0.05)
        self.spot_opacity_spin.setValue(0.3)
        opacity_layout.addWidget(self.spot_opacity_spin)
        spot_layout.addLayout(opacity_layout)

        spotlight_group.setLayout(spot_layout)
        layout.addWidget(spotlight_group)

        # ======== LASER ========
        laser_group = QGroupBox("Laser")
        laser_layout = QVBoxLayout()

        # Tamanho
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Tamanho (px):"))
        self.laser_size_spin = QSpinBox()
        self.laser_size_spin.setRange(1, 100)
        self.laser_size_spin.setValue(8)
        size_layout.addWidget(self.laser_size_spin)
        laser_layout.addLayout(size_layout)

        # Cor + preview
        laser_color_layout = QHBoxLayout()
        self.laser_color_btn = QPushButton("Cor do laser")
        self.laser_color_btn.clicked.connect(self.select_laser_color)
        self.laser_color_display = self.create_color_display(QColor("red"))
        laser_color_layout.addWidget(self.laser_color_btn)
        laser_color_layout.addWidget(self.laser_color_display)
        laser_layout.addLayout(laser_color_layout)

        laser_group.setLayout(laser_layout)
        layout.addWidget(laser_group)

        # ======== CANETA ========
        pen_group = QGroupBox("Modo Caneta")
        pen_layout = QVBoxLayout()

        # Espessura
        pen_size_layout = QHBoxLayout()
        pen_size_layout.addWidget(QLabel("Espessura (px):"))
        self.pen_size_spin = QSpinBox()
        self.pen_size_spin.setRange(1, 50)
        self.pen_size_spin.setValue(4)
        pen_size_layout.addWidget(self.pen_size_spin)
        pen_layout.addLayout(pen_size_layout)

        # Cor + preview
        pen_color_layout = QHBoxLayout()
        self.pen_color_btn = QPushButton("Cor da linha")
        self.pen_color_btn.clicked.connect(self.select_pen_color)
        self.pen_color_display = self.create_color_display(QColor("blue"))
        pen_color_layout.addWidget(self.pen_color_btn)
        pen_color_layout.addWidget(self.pen_color_display)
        pen_layout.addLayout(pen_color_layout)

        # Opacidade
        pen_opacity_layout = QHBoxLayout()
        pen_opacity_layout.addWidget(QLabel("Opacidade da linha:"))
        self.pen_opacity_spin = QDoubleSpinBox()
        self.pen_opacity_spin.setRange(0.0, 1.0)
        self.pen_opacity_spin.setSingleStep(0.05)
        self.pen_opacity_spin.setValue(0.8)
        pen_opacity_layout.addWidget(self.pen_opacity_spin)
        pen_layout.addLayout(pen_opacity_layout)

        pen_group.setLayout(pen_layout)
        layout.addWidget(pen_group)

        # ======== APLICAR ========
        apply_btn = QPushButton("Aplicar Configurações")
        apply_btn.clicked.connect(self.apply_settings)
        layout.addWidget(apply_btn)

        self.setLayout(layout)

    def create_color_display(self, color: QColor):
        frame = QFrame()
        frame.setFixedSize(20, 20)
        frame.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #000;"
        )
        return frame

    def select_spotlight_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.spot_color = color
            self.spot_color_display.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #000;"
            )
            self.spot_color = color

    def select_laser_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.laser_color = color
            self.laser_color_display.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #000;"
            )
            self.laser_color = color

    def select_pen_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.pen_color = color
            self.pen_color_display.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #000;"
            )
            self.pen_color = color

    def apply_settings(self):
        config = {
            "spotlight_radius": self.spot_radius_spin.value(),
            "spotlight_opacity": self.spot_opacity_spin.value(),
            "spotlight_color": self.spot_color,
            "laser_size": self.laser_size_spin.value(),
            "laser_color": self.laser_color,
            "pen_size": self.pen_size_spin.value(),
            "pen_color": self.pen_color,
            "pen_opacity": self.pen_opacity_spin.value(),
        }

        ow = self.ctx.overlay_window  # Janela ativa
        if ow:
            ow.spot_radius = config["spotlight_radius"]
            ow.overlay_alpha = int(config["spotlight_opacity"] * 255)
            ow.overlay_color = QColor(
                config["spotlight_color"].red(),
                config["spotlight_color"].green(),
                config["spotlight_color"].blue(),
                ow.overlay_alpha,
            )
            ow.laser_size = config["laser_size"]
            ow.pen_color = QColor(
                config["pen_color"].red(),
                config["pen_color"].green(),
                config["pen_color"].blue(),
                int(config["pen_opacity"] * 255),
            )
            ow.current_line_width = config["pen_size"]
            ow.update()

        self.close()
