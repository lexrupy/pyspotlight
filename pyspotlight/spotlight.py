import os
import time
import configparser
from distutils.util import strtobool
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtGui import (
    QPainter,
    QColor,
    QPixmap,
    QCursor,
    QPainterPath,
    QPen,
    QBrush,
)
from PyQt5.QtCore import Qt, QRect, QTimer, QPointF, QRectF, QPoint

from .utils import (
    MODE_MAP,
    capture_monitor_screenshot,
    MODE_SPOTLIGHT,
    MODE_PEN,
    MODE_LASER,
    MODE_MAG_GLASS,
    MODE_MOUSE,
)


DEBUG = True


CONFIG_PATH = os.path.expanduser("~/.config/pyspotlight/config.ini")


class SpotlightOverlayWindow(QWidget):
    def __init__(self, context, screenshot, screen_geometry, monitor_index):
        super().__init__()

        self._ctx = context

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setCursor(Qt.BlankCursor)

        self.mode = MODE_MOUSE
        self.last_pointer_mode = MODE_SPOTLIGHT

        self._auto_mode_enabled = True
        self._always_take_screenshot = False
        self.mag_is_square = False
        self.mag_aspect_ratio = 0.65

        self.last_key_time = 0
        self.last_key_pressed = 0

        self.default_spot_radius = 150
        self.spot_radius = 150
        self.zoom_factor = 2.0
        self.zoom_max = 10.0
        self.zoom_min = 2.0
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
            QColor(0, 0, 0),  # Preto
            # SE INCLUIR MAIS CORES MANTER ESTA A ÚLTIMA
            QColor(0, 0, 0, 0),  # Preto Transparente
        ]

        self.pen_colors = self.laser_colors[:-1]
        self.laser_index = 0
        self.pen_index = 0
        self.laser_size = 10

        self.pen_paths = []  # Lista de listas de pontos (QPoint)
        self.current_path = []  # Caminho atual
        self.drawing = False  # Se está atualmente desenhando
        self.current_line_width = 3

        self.setGeometry(screen_geometry)

        # self.pixmap = QPixmap.fromImage(screenshot)
        self.clear_pixmap()

        self.pen_color = self.pen_colors[self.pen_index]

        self.cursor_pos = None  # Usado para exibir a caneta

        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

        self.center_screen = self.geometry().center()
        QCursor.setPos(self.center_screen)

    def clear_pixmap(self):
        if self._always_take_screenshot:
            return
        self.pixmap = QPixmap(self.size())
        self.pixmap.fill(Qt.transparent)

    def current_mode(self):
        return self.mode

    def save_config(self):
        config = configparser.ConfigParser()
        config["General"] = {
            "last_mode": str(self.mode),
            "always_take_screenshot": str(self._always_take_screenshot),
        }
        config["Overlay"] = {
            "spot_radius": str(self.spot_radius),
            "zoom_factor": str(self.zoom_factor),
            "mag_aspect_ratio": str(self.mag_aspect_ratio),
            "mag_is_square": str(self.mag_is_square),
            "overlay_alpha": str(self.overlay_alpha),
            "overlay_r": str(self.overlay_color.red()),
            "overlay_g": str(self.overlay_color.green()),
            "overlay_b": str(self.overlay_color.blue()),
        }

        config["Laser"] = {
            "laser_index": str(self.laser_index),
            "pen_index": str(self.pen_index),
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

        if "General" in config:
            self.mode = int(config["General"].get("last_mode", self.mode))
            self._always_take_screenshot = bool(
                strtobool(
                    config["General"].get(
                        "always_take_screenshot", str(self._always_take_screenshot)
                    )
                )
            )

        if "Overlay" in config:
            self.spot_radius = int(
                config["Overlay"].get("spot_radius", self.spot_radius)
            )
            self.mag_is_square = bool(
                strtobool(
                    config["Overlay"].get("mag_is_square", str(self.mag_is_square))
                )
            )
            self.zoom_factor = float(
                config["Overlay"].get("zoom_factor", self.zoom_factor)
            )
            self.overlay_alpha = int(
                config["Overlay"].get("overlay_alpha", self.overlay_alpha)
            )
            self.mag_aspect_ratio = float(
                config["Overlay"].get("mag_aspect_ratio", self.mag_aspect_ratio)
            )

            r = int(config["Overlay"].get("overlay_r", 10))
            g = int(config["Overlay"].get("overlay_g", 10))
            b = int(config["Overlay"].get("overlay_b", 10))
            self.overlay_color = QColor(r, g, b, self.overlay_alpha)

        if "Laser" in config:
            self.laser_index = int(config["Laser"].get("laser_index", self.laser_index))
            self.pen_index = int(config["Laser"].get("pen_index", self.pen_index))
            self.laser_size = int(config["Laser"].get("laser_size", self.laser_size))
            self.pen_color = self.pen_colors[self.pen_index]

    def set_overlay_color_black(self):
        self.adjust_overlay_color(step_color=0, direct=True)

    def set_overlay_color_white(self):
        self.adjust_overlay_color(step_color=255, direct=True)

    def adjust_overlay_color(self, step_color=-256, step_alpha=-256, direct=False):
        r = self.overlay_color.red()
        g = self.overlay_color.green()
        b = self.overlay_color.blue()
        a = self.overlay_color.alpha()

        if direct:
            nr = step_color
            ng = step_color
            nb = step_color
            na = step_alpha
        else:
            nr = r + step_color
            ng = g + step_color
            nb = b + step_color
            na = a + step_alpha

        if step_color >= -255:
            r = min(max(nr, 0), 255)
            g = min(max(ng, 0), 255)
            b = min(max(nb, 0), 255)
        if step_alpha >= -255:
            a = min(max(na, 0), 255)
            self.overlay_alpha = a  # mantém coerência com o atributo

        self.overlay_color = QColor(r, g, b, a)
        self.update()

    def laser_inverted(self):
        return self.laser_index == len(self.laser_colors) - 1

    def auto_mode_enabled(self):
        return self._auto_mode_enabled and self._ctx.support_auto_mode

    def set_spotlight_mode(self):
        self.switch_mode(direct_mode=MODE_SPOTLIGHT)

    def set_mouse_mode(self):
        self.switch_mode(direct_mode=MODE_MOUSE)

    def set_laser_mode(self):
        self.switch_mode(direct_mode=MODE_LASER)

    def set_pen_mode(self):
        self.switch_mode(direct_mode=MODE_PEN)

    def hide_overlay(self):
        self.clear_pixmap()
        self.hide()

    def show_overlay(self):
        if self.mode == MODE_MAG_GLASS:
            if self.zoom_factor <= self.zoom_min:
                self.zoom_factor = self.zoom_min
            self.capture_screenshot()
        elif self.mode == MODE_LASER and self.laser_inverted():
            self.capture_screenshot()
        elif self.mode != MODE_MOUSE:
            if self._always_take_screenshot:
                self.capture_screenshot()
            else:
                self.showFullScreen()

    def set_last_pointer_mode(self):
        if self.last_pointer_mode in self._ctx.compatible_modes:
            self.switch_mode(direct_mode=self.last_pointer_mode)

    def set_auto_mode(self, enable=True):
        if not self._ctx.support_auto_mode:
            return
        self._auto_mode_enabled = enable
        if enable:
            self._ctx.show_info(f"Auto Mode")
            self.hide_overlay()
        else:
            self.show_overlay()
            self._ctx.show_info(f"{MODE_MAP[self.mode]}")

    def switch_mode(self, step=1, direct_mode=-1):
        compatible = self._ctx.compatible_modes
        all_modes = list(MODE_MAP.keys())  # usa ordem de definição dos modos

        if not compatible:
            return

        if direct_mode >= 0:
            if direct_mode in compatible and not (
                direct_mode == MODE_PEN and self.auto_mode_enabled()
            ):
                self.apply_mode_change(direct_mode)
            return

        # Busca o próximo modo compatível
        current_index = all_modes.index(self.mode) if self.mode in all_modes else 0
        total_modes = len(all_modes)

        for i in range(1, total_modes + 1):  # evita loop infinito
            next_index = (current_index + step * i) % total_modes
            next_mode = all_modes[next_index]
            if next_mode == MODE_PEN and self.auto_mode_enabled():
                continue  # pula MODE_PEN
            if next_mode in compatible:
                self.apply_mode_change(next_mode)
                return

    def apply_mode_change(self, new_mode):
        last_mode = self.mode
        if last_mode != new_mode and last_mode == MODE_MAG_GLASS:
            self.clear_pixmap()

        self.mode = new_mode

        if (
            self.mode in [MODE_SPOTLIGHT, MODE_LASER, MODE_MAG_GLASS]
            and last_mode != self.mode
        ):
            self.last_pointer_mode = self.mode

        self._ctx.show_info(f"Modo {MODE_MAP[self.mode]}")

        if self.auto_mode_enabled():
            return

        if self.mode == MODE_MOUSE:
            self.hide()
        elif self.mode == MODE_MAG_GLASS:
            if self.zoom_factor <= self.zoom_min:
                self.zoom_factor = self.zoom_min
            self.capture_screenshot()
        else:

            if self.mode == MODE_LASER and self.laser_inverted():
                self.capture_screenshot()
            else:
                if self._always_take_screenshot:
                    self.capture_screenshot()
                else:
                    self.showFullScreen()

        self.update()

    def change_laser_size(self, delta: int):
        min_size = 5
        max_size = 100

        new_size = self.laser_size + delta
        if new_size < min_size:
            new_size = min_size
        elif new_size > max_size:
            new_size = max_size

        if new_size != self.laser_size:
            self.laser_size = new_size
            self.update()

    def change_spot_radius(self, increase=1):
        if increase == 0:
            self.spot_radius = self.default_spot_radius
        else:
            self.spot_radius = max(50, self.spot_radius + (increase * 10))

        self.update()

    def zoom(self, direction):
        if self.mode == MODE_MAG_GLASS:
            if direction > 0:
                self.zoom_factor = min(self.zoom_max, self.zoom_factor + 1.0)
            else:
                self.zoom_factor = max(self.zoom_min, self.zoom_factor - 1.0)
            self.update()

    def next_laser_color(self, step=1):
        self.laser_index = (self.laser_index + step) % len(self.laser_colors)
        if self.laser_inverted():
            self.capture_screenshot()
        else:
            self.clear_pixmap()
        self.update()

    def next_pen_color(self, step=1):
        self.pen_index = (self.pen_index + step) % len(self.pen_colors)
        self.pen_color = self.pen_colors[self.pen_index]
        self.update()

    def clear_drawing(self, all=False):
        if all:
            self.pen_paths.clear()
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
            self.update()  # atualiza a tela para refletir a mudança, se necessário

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
        self.showFullScreen()

    def drawMagnifyingGlass(self, painter, cursor_pos):
        radius = self.spot_radius
        PADDING = 100  # pixels extras de borda

        if self.mag_is_square:
            width = radius * 2
            height = int(width * self.mag_aspect_ratio)
            is_ellipse = False
        else:
            width = height = radius * 2
            is_ellipse = True

        # Cálculo da área de origem (reduzida pela ampliação)
        src_width = int(width / self.zoom_factor)
        src_height = int(height / self.zoom_factor)

        # Cria imagem com borda transparente
        padded_pixmap = QPixmap(
            self.pixmap.width() + PADDING * 2, self.pixmap.height() + PADDING * 2
        )
        padded_pixmap.fill(Qt.transparent)

        painter_pad = QPainter(padded_pixmap)
        painter_pad.drawPixmap(PADDING, PADDING, self.pixmap)
        painter_pad.end()

        # Corrige a posição do cursor no espaço com padding
        cursor_pos_padded = QPoint(cursor_pos.x() + PADDING, cursor_pos.y() + PADDING)

        # Calcula retângulo de origem (recorte ampliado)
        x = cursor_pos_padded.x() - src_width // 2
        y = cursor_pos_padded.y() - src_height // 2
        src_rect = QRect(x, y, src_width, src_height)

        # Retângulo de destino (onde será desenhado o zoom)
        dest_rect = QRect(
            cursor_pos.x() - width // 2,
            cursor_pos.y() - height // 2,
            width,
            height,
        )

        # Clipping para formato oval ou quadrado
        if is_ellipse:
            clip_path = QPainterPath()
            clip_path.addEllipse(QRectF(dest_rect))
            painter.setClipPath(clip_path)

        # Desenha a imagem ampliada
        painter.drawPixmap(dest_rect, padded_pixmap, src_rect)

        if is_ellipse:
            painter.setClipping(False)

        # Borda branca
        border_color = QColor(255, 255, 255, 180)
        pen = QPen(border_color, 2 if not is_ellipse else 4)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.setRenderHint(QPainter.Antialiasing)

        if is_ellipse:
            painter.drawEllipse(dest_rect)
        else:
            painter.drawRect(dest_rect)

    # def drawMagnifyingGlass(self, painter, cursor_pos):
    #     radius = self.spot_radius
    #
    #     if self.mag_is_square:
    #         width = radius * 2
    #         height = int(width * self.mag_aspect_ratio)
    #         is_ellipse = False
    #     else:
    #         width = height = radius * 2
    #         is_ellipse = True
    #
    #     # Cálculo da área de origem (reduzida pela ampliação)
    #     src_width = int(width / self.zoom_factor)
    #     src_height = int(height / self.zoom_factor)
    #
    #     src_rect = QRect(
    #         cursor_pos.x() - src_width // 2,
    #         cursor_pos.y() - src_height // 2,
    #         src_width,
    #         src_height,
    #     ).intersected(self.pixmap.rect())
    #
    #     dest_rect = QRect(
    #         cursor_pos.x() - width // 2,
    #         cursor_pos.y() - height // 2,
    #         width,
    #         height,
    #     )
    #
    #     if is_ellipse:
    #         clip_path = QPainterPath()
    #         clip_path.addEllipse(QRectF(dest_rect))
    #         painter.setClipPath(clip_path)
    #
    #     painter.drawPixmap(dest_rect, self.pixmap, src_rect)
    #
    #     if is_ellipse:
    #         painter.setClipping(False)
    #
    #     # Borda branca
    #     border_color = QColor(255, 255, 255, 180)
    #     pen = QPen(border_color, 2 if not is_ellipse else 4)
    #     painter.setPen(pen)
    #     painter.setBrush(Qt.NoBrush)
    #     painter.setRenderHint(QPainter.Antialiasing)
    #
    #     if is_ellipse:
    #         painter.drawEllipse(dest_rect)
    #     else:
    #         painter.drawRect(dest_rect)
    #
    def drawSpotlight(self, painter, cursor_pos):
        # Spotlight tradicional com overlay escuro
        painter.setBrush(self.overlay_color)
        painter.setPen(Qt.NoPen)

        spotlight_path = QPainterPath()
        spotlight_path.addRect(QRectF(self.rect()))
        spotlight_path.addEllipse(cursor_pos, self.spot_radius, self.spot_radius)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPath(spotlight_path)

    def drawLaser(self, painter, cursor_pos):
        size = self.laser_size
        half_size = size // 2
        # Laser pointer com sombras e círculo central
        color = self.laser_colors[self.laser_index]

        if color == self.laser_colors[-1]:
            laser_rect = QRect(
                cursor_pos.x() - half_size, cursor_pos.y() - half_size, size, size
            )
            region = self.pixmap.copy(laser_rect)
            image = region.toImage()
            image.invertPixels()
            inverted_pixmap = QPixmap.fromImage(image)

            # Clipa o círculo para desenhar só o laser invertido dentro dele
            clip_path = QPainterPath()
            clip_path.addEllipse(cursor_pos, half_size, half_size)
            painter.setClipPath(clip_path)
            painter.drawPixmap(laser_rect, inverted_pixmap)
            painter.setClipping(False)

            # Agora desenha as sombras ao redor, mas **fora** do círculo
            for margin, alpha in [(12, 50), (8, 80), (4, 110)]:
                outer_radius = half_size + margin
                outer_path = QPainterPath()
                outer_path.addEllipse(cursor_pos, outer_radius, outer_radius)

                # subtrai o círculo central
                outer_path -= clip_path

                shadow_color = QColor(255, 255, 255, alpha)
                painter.setBrush(shadow_color)
                painter.setPen(Qt.NoPen)
                painter.drawPath(outer_path)

            # borda branca (opcional)
            pen = QPen(QColor(255, 255, 255, 200))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.drawEllipse(cursor_pos, half_size, half_size)

        else:

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

    def drawLines(self, painter, cursor_pos):
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

    def paintEvent(self, event):
        painter = QPainter(self)
        cursor_pos = self.mapFromGlobal(QCursor.pos())
        # Fundo: sempre desenha o screenshot completo
        painter.drawPixmap(0, 0, self.pixmap)
        if self.mode == MODE_SPOTLIGHT:
            self.drawSpotlight(painter, cursor_pos)
        elif self.mode == MODE_LASER:
            self.drawLaser(painter, cursor_pos)
        elif self.mode == MODE_PEN:
            self.drawLines(painter, cursor_pos)
        elif self.mode == MODE_MAG_GLASS:
            self.drawMagnifyingGlass(painter, cursor_pos)

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
                if self.mode == MODE_PEN:
                    self.start_pen_path()

            case "stop_move":
                if self.mode == MODE_PEN and self.drawing:
                    self.finish_pen_path()

            case "line_width_increase":
                self.current_line_width = min(self.current_line_width + 1, 20)

            case "line_width_decrease":
                self.current_line_width = max(self.current_line_width - 1, 1)

    def mousePressEvent(self, event):
        if self.mode == MODE_PEN:
            self.start_pen_path()
            self.current_path.append(event.pos())

    def mouseMoveEvent(self, event):
        if self.mode == MODE_PEN and self.drawing:
            self.current_path.append(event.pos())
        self.update()

    def mouseReleaseEvent(self, event):
        if self.mode == MODE_PEN and self.drawing:
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
        if key == Qt.Key_M:
            self.switch_mode(step=1)
            self.update()

        self.last_key_time = now
        self.last_key_pressed = key

    def closeEvent(self, event):
        # self.save_config()
        event.accept()

    def quit(self):
        # self.save_config()
        self.set_mouse_mode()
