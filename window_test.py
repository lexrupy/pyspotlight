from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QMainWindow,
    QLabel,
    QCheckBox,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QSpinBox,
    QComboBox,
    QFrame,
    QTextEdit,
    QTabWidget,
    QColorDialog,
)
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
import sys


class PreferencesTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Grupos principais
        spotlight_group = self.create_spotlight_group()
        laser_group = self.create_laser_group()
        marker_group = self.create_marker_group()
        lupa_group = self.create_lupa_group()
        monitors_group = self.create_monitors_group()
        geral_group = self.create_geral_group()

        line1 = QHBoxLayout()
        line1.addWidget(spotlight_group)
        line1.addWidget(marker_group)

        line2 = QHBoxLayout()
        line2.addWidget(laser_group)
        line2.addWidget(lupa_group)

        layout.addLayout(line1)
        layout.addLayout(line2)
        layout.addWidget(monitors_group)
        layout.addWidget(geral_group)

        # Botões
        button_layout = QHBoxLayout()
        self.exit_btn = QPushButton("Encerrar")
        self.hide_btn = QPushButton("Fechar")
        button_layout.addWidget(self.exit_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.hide_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def create_spotlight_group(self):
        group = QGroupBox("Spotlight")
        layout = QVBoxLayout()

        layout.addLayout(self.hline("Spot Size(px):", self.create_spinbox(25)))
        layout.addLayout(
            self.hline("Overlay Color:", self.color_button(QColor("navy")))
        )
        layout.addLayout(self.hline("Opacity (%):", self.create_spinbox(25)))
        layout.addWidget(QCheckBox("Exibir Borda"))
        layout.addLayout(self.hline("Cor da Borda:", self.color_button(QColor("red"))))

        group.setLayout(layout)
        return group

    def create_laser_group(self):
        group = QGroupBox("Laser")
        layout = QVBoxLayout()

        layout.addLayout(self.hline("Point Size(px):", self.create_spinbox(25)))
        layout.addLayout(self.hline("Point Color:", self.color_button(QColor("red"))))
        layout.addLayout(self.hline("Opacity (%):", self.create_spinbox(25)))
        layout.addWidget(QCheckBox("Exibir Sombra"))

        group.setLayout(layout)
        return group

    def create_marker_group(self):
        group = QGroupBox("Marcador")
        layout = QVBoxLayout()

        layout.addLayout(self.hline("Line width(px)", self.create_spinbox(25)))
        layout.addLayout(self.hline("Line Color:", self.color_button(QColor("lime"))))
        layout.addLayout(self.hline("Opacity (%):", self.create_spinbox(25)))

        group.setLayout(layout)
        return group

    def create_lupa_group(self):
        group = QGroupBox("Lupa")
        layout = QVBoxLayout()

        shape_combo = QComboBox()
        shape_combo.addItems(["Círculo", "Quadrado"])
        layout.addLayout(self.hline("Forma:", shape_combo))
        layout.addLayout(self.hline("Cor da Borda:", self.color_button(QColor("red"))))
        layout.addLayout(self.hline("Opacity (%):", self.create_spinbox(25)))
        layout.addWidget(QCheckBox("Exibir Borda"))

        group.setLayout(layout)
        return group

    def create_monitors_group(self):
        group = QGroupBox("Monitores")
        layout = QVBoxLayout()

        monitor_combo = QComboBox()
        monitor_combo.addItem("0: 1800x600")
        refresh_btn = QPushButton("Atualizar Monitores")
        layout.addWidget(monitor_combo)
        layout.addWidget(refresh_btn)

        group.setLayout(layout)
        return group

    def create_geral_group(self):
        group = QGroupBox("Geral")
        layout = QVBoxLayout()
        layout.addWidget(QCheckBox("Sempre capturar screenshot"))
        layout.addWidget(QCheckBox("Modo Automático de Disponível"))
        group.setLayout(layout)
        return group

    def hline(self, label: str, widget: QWidget):
        line = QHBoxLayout()
        line.addWidget(QLabel(label))
        line.addWidget(widget)
        return line

    def create_spinbox(self, val=0):
        sb = QSpinBox()
        sb.setRange(0, 100)
        sb.setValue(val)
        return sb

    def color_button(self, color: QColor):
        btn = QPushButton()
        btn.setFixedSize(40, 20)
        btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #000;")
        btn.clicked.connect(lambda: self.choose_color(btn))
        return btn

    def choose_color(self, button: QPushButton):
        current_color = button.palette().button().color()
        new_color = QColorDialog.getColor(current_color, self)
        if new_color.isValid():
            button.setStyleSheet(
                f"background-color: {new_color.name()}; border: 1px solid #000;"
            )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySpotlight")
        self.setMinimumSize(800, 300)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        self.preferences_tab = PreferencesTab()
        self.log_tab = QTextEdit()
        self.log_tab.setReadOnly(True)
        self.log_tab.setStyleSheet("background-color: black; color: lime;")
        self.devices_tab = QWidget()

        tabs.addTab(self.preferences_tab, "Preferences")
        tabs.addTab(self.devices_tab, "Devices")
        tabs.addTab(self.log_tab, "Log")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
