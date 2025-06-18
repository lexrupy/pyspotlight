import os
import sys
import time
import threading
import select
import mss
import configparser
from PIL import Image
from PyQt5.QtWidgets import QApplication, QWidget, QMessageBox
from PyQt5.QtGui import (
    QPainter,
    QColor,
    QPixmap,
    QCursor,
    QPainterPath,
    QGuiApplication,
    QImage,
    QPen,
    QBrush,
)
from PyQt5.QtCore import Qt, QRect, QTimer, QPointF, QRectF

DEBUG = True


CONFIG_PATH = os.path.expanduser("~/.config/pyspotlight/config.ini")


SPOTLIGHT_MODE = 0
LASER_MODE = 1
PEN_MODE = 2


def log(message):
    if DEBUG:
        print(message)


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


def ipc_listener(window: QWidget):
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 0.1)
        if ready:
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip()
            log(f"IPC: {cmd}")
            window.handle_command(cmd)


class OverlayWindow(QWidget):
    def __init__(self, screenshot, screen_geometry, monitor_index):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.BlankCursor)

        self.mode = SPOTLIGHT_MODE
        self.last_mode = SPOTLIGHT_MODE

        self.last_key_time = 0
        self.last_key_pressed = 0

        self.default_spot_radius = 150
        self.spot_radius = 150
        self.zoom_factor = 1.0
        self.zoom_max = 10.0
        self.zoom_min = 1.0
        self.overlay_alpha = 200
        self.overlay_color = QColor(10, 10, 10, self.overlay_alpha)
        self.monitor_index = monitor_index

        self.laser_colors = [
            QColor(255, 0, 0),  # Vermelho
            QColor(0, 255, 0),  # Verde
            QColor(0, 0, 255),  # Azul
            QColor(255, 0, 255),  # Magenta / Pink
            QColor(255, 255, 0),  # Amarelo
            QColor(0, 255, 255),  # Ciano
            QColor(255, 165, 0),  # Laranja forte
            QColor(255, 255, 255),  # Branco
        ]
        self.laser_index = 0
        self.laser_size = 10

        self.pen_paths = []  # Lista de listas de pontos (QPoint)
        self.current_path = []  # Caminho atual
        self.drawing = False  # Se está atualmente desenhando
        self.current_line_width = 3

        self.setGeometry(screen_geometry)
        self.pixmap = QPixmap.fromImage(screenshot)

        self.pen_color = self.laser_colors[self.laser_index]

        self.cursor_pos = None  # Usado para exibir a caneta

        self.load_config()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

        self.showFullScreen()
        self.center_screen = self.geometry().center()
        QCursor.setPos(self.center_screen)

    def save_config(self):
        config = configparser.ConfigParser()

        config["Overlay"] = {
            "spot_radius": str(self.spot_radius),
            "zoom_factor": str(self.zoom_factor),
            "overlay_alpha": str(self.overlay_alpha),
            "overlay_r": str(self.overlay_color.red()),
            "overlay_g": str(self.overlay_color.green()),
            "overlay_b": str(self.overlay_color.blue()),
        }

        config["Laser"] = {
            "laser_index": str(self.laser_index),
            "laser_size": str(self.laser_size),
        }

        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            config.write(f)

    def load_config(self):
        config = configparser.ConfigParser()
        if not os.path.exists(CONFIG_PATH):
            return  # Nenhum arquivo ainda

        config.read(CONFIG_PATH)

        if "Overlay" in config:
            self.spot_radius = int(
                config["Overlay"].get("spot_radius", self.spot_radius)
            )
            self.zoom_factor = float(
                config["Overlay"].get("zoom_factor", self.zoom_factor)
            )
            self.overlay_alpha = int(
                config["Overlay"].get("overlay_alpha", self.overlay_alpha)
            )

            r = int(config["Overlay"].get("overlay_r", 10))
            g = int(config["Overlay"].get("overlay_g", 10))
            b = int(config["Overlay"].get("overlay_b", 10))
            self.overlay_color = QColor(r, g, b, self.overlay_alpha)

        if "Laser" in config:
            self.laser_index = int(config["Laser"].get("laser_index", self.laser_index))
            self.laser_size = int(config["Laser"].get("laser_size", self.laser_size))
            self.pen_color = self.laser_colors[self.laser_index]

    def adjust_overlay_color(self, step_color=0, step_alpha=0):
        r = self.overlay_color.red()
        g = self.overlay_color.green()
        b = self.overlay_color.blue()
        a = self.overlay_color.alpha()

        if step_color != 0:
            r = min(max(r + step_color, 0), 255)
            g = min(max(g + step_color, 0), 255)
            b = min(max(b + step_color, 0), 255)

        a = min(max(a + step_alpha, 0), 255)

        self.overlay_alpha = a  # mantém coerência com o atributo
        self.overlay_color = QColor(r, g, b, a)
        self.update()

    def switch_mode(self, step=1):
        next_mode = self.mode + step
        if next_mode >= 3:
            QApplication.quit()
            return

        self.mode = next_mode % 3
        self.capture_screenshot()
        self.update()

    def change_spot_radius(self, increase=1):
        if increase == 0:
            self.spot_radius = self.default_spot_radius
        else:
            self.spot_radius = max(50, self.spot_radius + (increase * 10))

        self.update()

    def zoom(self, direction):
        if self.mode == SPOTLIGHT_MODE:
            if direction > 0:
                self.zoom_factor = min(self.zoom_max, self.zoom_factor + 1.0)
            else:
                self.zoom_factor = max(self.zoom_min, self.zoom_factor - 1.0)
            self.update()

    def next_color(self, step=1):
        self.laser_index = (self.laser_index + step) % len(self.laser_colors)
        self.pen_color = self.laser_colors[self.laser_index]
        self.update()

    def clear_drawing(self):
        if self.pen_paths:
            self.pen_paths.pop()  # Remove o último caminho desenhado
        self.current_path = []
        self.update()

    def change_line_width(self, delta: int):
        min_width = 1
        max_width = 20

        new_width = self.current_line_width + delta
        if new_width < min_width:
            new_width = min_width
        elif new_width > max_width:
            new_width = max_width

        if new_width != self.current_line_width:
            self.current_line_width = new_width
            print(f"Largura da linha ajustada para: {self.current_line_width}")
            self.update()  # atualiza a tela para refletir a mudança, se necessário

    def set_mode_by_name(self, name):
        mode_map = {
            "laser": LASER_MODE,
            "spotlight": SPOTLIGHT_MODE,
            "pen": PEN_MODE,
        }
        if name in mode_map:
            self.switch_mode(mode=mode_map[name])

    def capture_screenshot(self):

        # Esconde a janela overlay
        self.hide()
        QApplication.processEvents()
        time.sleep(0.5)  # aguardar atualização da tela

        # Captura a tela limpa usando seu método externo
        qimage, rect = capture_monitor_screenshot(self.monitor_index)

        # Atualiza o pixmap do overlay (converter QImage para QPixmap)
        self.pixmap = QPixmap.fromImage(qimage)

        # Mostra a janela overlay novamente
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        cursor_pos = self.mapFromGlobal(QCursor.pos())

        # Fundo: sempre desenha o screenshot completo
        painter.drawPixmap(0, 0, self.pixmap)

        if self.mode == SPOTLIGHT_MODE:
            if self.zoom_factor > 1.0:
                # --- Lente com zoom sem overlay ---
                src_size = int((self.spot_radius * 2) / self.zoom_factor)
                half = src_size // 2
                src_rect = QRect(
                    cursor_pos.x() - half, cursor_pos.y() - half, src_size, src_size
                )
                src_rect = src_rect.intersected(self.pixmap.rect())

                dest_size = self.spot_radius * 2
                dest_rect = QRect(
                    cursor_pos.x() - self.spot_radius,
                    cursor_pos.y() - self.spot_radius,
                    dest_size,
                    dest_size,
                )

                clip_path = QPainterPath()
                clip_path.addEllipse(cursor_pos, self.spot_radius, self.spot_radius)
                painter.setClipPath(clip_path)
                painter.drawPixmap(dest_rect, self.pixmap, src_rect)
                painter.setClipping(False)

                # Borda translúcida ao redor da lente
                border_color = QColor(self.laser_colors[self.laser_index])
                border_color.setAlphaF(0.3)
                pen = QPen(border_color, 6)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.drawEllipse(cursor_pos, self.spot_radius, self.spot_radius)

            else:
                # Spotlight tradicional com overlay escuro
                painter.setBrush(self.overlay_color)
                painter.setPen(Qt.NoPen)

                spotlight_path = QPainterPath()
                spotlight_path.addRect(QRectF(self.rect()))
                spotlight_path.addEllipse(
                    cursor_pos, self.spot_radius, self.spot_radius
                )

                painter.setRenderHint(QPainter.Antialiasing)
                painter.drawPath(spotlight_path)

        elif self.mode == LASER_MODE:
            # Laser pointer com sombras e círculo central
            color = self.laser_colors[self.laser_index]
            size = self.laser_size
            center_x = cursor_pos.x() - size // 2
            center_y = cursor_pos.y() - size // 2

            shadow_levels = [(12, 30), (8, 60), (4, 90)]
            for margin, alpha in shadow_levels:
                shadow_color = QColor(color)
                shadow_color.setAlpha(alpha)
                painter.setBrush(shadow_color)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(
                    center_x - margin,
                    center_y - margin,
                    size + 2 * margin,
                    size + 2 * margin,
                )

            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(center_x, center_y, size, size)

        elif self.mode == PEN_MODE:
            painter.setRenderHint(QPainter.Antialiasing)

            # Desenha paths antigos
            for path in self.pen_paths:
                pen = QPen(
                    path["color"],
                    path["width"],
                    Qt.SolidLine,
                    Qt.RoundCap,
                    Qt.RoundJoin,
                )
                painter.setPen(pen)
                if len(path["points"]) > 1:
                    for i in range(len(path["points"]) - 1):
                        painter.drawLine(path["points"][i], path["points"][i + 1])

            # Desenha o path atual (se estiver desenhando)
            if self.drawing and len(self.current_path) > 1:
                pen = QPen(
                    self.pen_color,
                    self.current_line_width,
                    Qt.SolidLine,
                    Qt.RoundCap,
                    Qt.RoundJoin,
                )
                painter.setPen(pen)
                for i in range(len(self.current_path) - 1):
                    painter.drawLine(self.current_path[i], self.current_path[i + 1])

            cursor_pos = self.mapFromGlobal(QCursor.pos())
            brush = QBrush(self.pen_color)
            painter.setBrush(brush)
            painter.setPen(Qt.NoPen)
            self.draw_pen_tip(painter, cursor_pos, size=self.current_line_width * 4)

    def draw_pen_tip(self, painter, pos, size=20):
        # Pontos do SVG com a ponta em (0, 0)
        original_points = [
            (0.0, 0.0),  # ponta inferior
            (43.989, -75.561),  # canto superior esquerdo
            (57.999, -66.870),  # canto superior direito
            (11.352, 6.918),  # lado inferior direito
            (-1.241, 14.013),  # lado inferior esquerdo
        ]

        # Escala total proporcional ao "size" do traço
        # Consideramos que o SVG foi feito com largura base ~10 → ajustamos para isso
        base_line_width = 20  # ajuste este valor se quiser outra espessura padrão
        scale = size / base_line_width

        points = [
            QPointF(pos.x() + x * scale, pos.y() + y * scale)
            for (x, y) in original_points
        ]

        path = QPainterPath()
        path.moveTo(points[0])
        for p in points[1:]:
            path.lineTo(p)
        path.closeSubpath()

        painter.setBrush(QBrush(self.pen_color))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

    def start_pen_path(self):
        self.drawing = True
        self.current_path = []

    def finish_pen_path(self):
        if len(self.current_path) > 1:
            self.pen_paths.append(
                {
                    "points": self.current_path[:],
                    "color": self.pen_color,
                    "width": self.current_line_width,
                }
            )
        self.current_path = []
        self.drawing = False
        self.update()

    def handle_draw_command(self, command):
        match command:
            case "start_move":
                if self.mode == PEN_MODE:
                    self.start_pen_path()

            case "stop_move":
                if self.mode == PEN_MODE and self.drawing:
                    self.finish_pen_path()

            case "line_width_increase":
                self.current_line_width = min(self.current_line_width + 1, 20)

            case "line_width_decrease":
                self.current_line_width = max(self.current_line_width - 1, 1)

    def handle_command(self, cmd: str):
        # Aqui você centraliza toda a lógica de comandos IPC
        if cmd == "next_mode":
            self.switch_mode(+1)
        elif cmd == "previous_mode":
            self.switch_mode(-1)
        elif cmd == "zoom_in":
            if self.mode == 2:  # PEN mode não tem zoom, por exemplo
                # Pode ignorar ou fazer algo específico
                pass
            else:
                self.zoom(+1)
        elif cmd == "zoom_out":
            if self.mode != 2:
                self.zoom(-1)
        elif cmd == "increase_size":
            if self.mode == 2:
                self.change_line_width(+1)
            else:
                self.change_spot_radius(+1)
        elif cmd == "decrease_size":
            if self.mode == 2:
                self.change_line_width(-1)
            else:
                self.change_spot_radius(-1)
        elif cmd == "color_next":
            if self.mode == SPOTLIGHT_MODE:
                self.adjust_overlay_color(20)
            else:
                self.next_color(+1)
        elif cmd == "color_prior":
            if self.mode == SPOTLIGHT_MODE:
                self.adjust_overlay_color(-20)
            else:
                self.next_color(-1)
        elif cmd == "alpha_next":
            if self.mode == SPOTLIGHT_MODE:
                self.adjust_overlay_color(0, 10)
        elif cmd == "alpha_prior":
            if self.mode == SPOTLIGHT_MODE:
                self.adjust_overlay_color(0, -10)
        elif cmd == "clear_drawing":
            self.clear_drawing()
        elif cmd == "quit_spx":
            self.quit()
        elif cmd in ("start_move", "stop_move"):
            self.handle_draw_command(cmd)
        elif cmd.startswith("set_mode"):
            _, mode_str = cmd.split(maxsplit=1)
            self.set_mode_by_name(mode_str.strip().lower())
        else:
            print(f"Comando IPC desconhecido: {cmd}")

    def mousePressEvent(self, event):
        if self.mode == PEN_MODE:
            self.start_pen_path()
            self.current_path.append(event.pos())

    def mouseMoveEvent(self, event):
        if self.mode == PEN_MODE and self.drawing:
            self.current_path.append(event.pos())
        self.update()

    def mouseReleaseEvent(self, event):
        if self.mode == PEN_MODE and self.drawing:
            self.finish_pen_path()

    # Other ShortCuts
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if self.mode == 1:
            if delta > 0:
                self.zoom_factor = min(self.zoom_max, self.zoom_factor + 1.0)
            else:
                self.zoom_factor = max(self.zoom_min, self.zoom_factor - 1.0)
        elif self.mode == 0:
            if delta > 0:
                self.laser_size = min(100, self.laser_size + 2)
            else:
                self.laser_size = max(5, self.laser_size - 2)
        self.update()

    def keyPressEvent(self, event):
        key = event.key()
        now = time.time()
        # modifiers = QApplication.keyboardModifiers()
        if key == Qt.Key_Escape:
            if (
                now - self.last_key_time < 1.0
                and self.last_key_pressed == Qt.Key_Escape
            ):
                self.quit()

        if key == Qt.Key_P:
            self.capture_screenshot()
            self.update()

        self.last_key_time = now
        self.last_key_pressed = key

    def closeEvent(self, event):
        self.save_config()
        event.accept()

    def quit(self):
        self.save_config()
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    screen_index = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    screens = QGuiApplication.screens()

    geometry = screens[screen_index].geometry()

    img, geometry = capture_monitor_screenshot(screen_index)
    w = OverlayWindow(img, geometry, screen_index)

    threading.Thread(target=ipc_listener, args=(w,), daemon=True).start()

    sys.exit(app.exec_())
    # END
