"""剪贴板列表项委托 - 自定义绘制。

绘制文本（单行省略）+ 时间 + 星标按钮（可点击切换）。
支持文本/文件/图片类型差异化显示。
"""

import json
from PySide6.QtWidgets import QStyledItemDelegate, QStyle
from PySide6.QtCore import Qt, QRect, QSize, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPainterPath, QPolygonF, QPixmap


def _relative_time(ts: int) -> str:
    """将时间戳转为相对时间描述。"""
    import time
    now = int(time.time())
    diff = now - ts
    if diff < 60:
        return "刚刚"
    elif diff < 3600:
        return f"{diff // 60}分钟前"
    elif diff < 86400:
        return f"{diff // 3600}小时前"
    elif diff < 604800:
        return f"{diff // 86400}天前"
    else:
        import datetime
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d")


def _draw_star(painter: QPainter, center: QPointF, outer_r: float, inner_r: float):
    """绘制五角星路径。"""
    import math
    path = QPainterPath()
    points = []
    for i in range(5):
        # 外顶点
        angle = math.radians(-90 + i * 72)
        points.append(QPointF(
            center.x() + outer_r * math.cos(angle),
            center.y() + outer_r * math.sin(angle),
        ))
        # 内顶点
        angle = math.radians(-90 + 36 + i * 72)
        points.append(QPointF(
            center.x() + inner_r * math.cos(angle),
            center.y() + inner_r * math.sin(angle),
        ))

    polygon = QPolygonF(points)
    path.addPolygon(polygon)
    painter.drawPath(path)


class ClipItemDelegate(QStyledItemDelegate):
    """绘制剪贴板历史条目：文本 + 时间 + 可点击星标按钮。"""

    ITEM_HEIGHT = 48
    PADDING = 8
    STAR_SIZE = 18  # 星标按钮区域大小
    STAR_OUTER = 8  # 星标外半径
    STAR_INNER = 3  # 星标内半径

    # 星标颜色
    STAR_ON_COLOR = QColor("#F5A623")   # 黄色填充
    STAR_OFF_COLOR = QColor(200, 200, 200)  # 灰色空心

    def __init__(self):
        super().__init__()
        self._star_callback = None  # callable(clip_id)

    def set_star_callback(self, callback):
        """设置星标点击回调。"""
        self._star_callback = callback

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ITEM_HEIGHT)

    def _star_rect(self, item_rect: QRect) -> QRect:
        """返回星标按钮的矩形区域。"""
        return QRect(
            item_rect.right() - self.STAR_SIZE - self.PADDING - 110,
            item_rect.top() + (self.ITEM_HEIGHT - self.STAR_SIZE) // 2,
            self.STAR_SIZE,
            self.STAR_SIZE,
        )

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 选中背景
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(240, 240, 245))

        data = index.data(Qt.ItemDataRole.UserRole)
        if not data:
            painter.restore()
            return

        rect = option.rect.adjusted(self.PADDING, 4, -self.PADDING, -4)

        # ---- 星标按钮 ----
        star_rect = self._star_rect(option.rect)
        star_center = QPointF(star_rect.center())
        starred = data.get("starred", False)

        painter.setPen(QPen(self.STAR_ON_COLOR if starred else self.STAR_OFF_COLOR, 1.5))
        if starred:
            painter.setBrush(QBrush(self.STAR_ON_COLOR))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        _draw_star(painter, star_center, self.STAR_OUTER, self.STAR_INNER)

        # ---- 时间 ----
        time_font = QFont(option.font)
        time_font.setPointSize(8)
        painter.setFont(time_font)
        painter.setPen(QColor(150, 150, 150))
        time_text = _relative_time(data.get("timestamp", 0))
        time_rect = QRect(rect.right() - 100, rect.top(), 90, 16)
        painter.drawText(time_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, time_text)

        # ---- 内容文本（单行省略） ----
        content_font = QFont(option.font)
        content_font.setPointSize(10)
        painter.setFont(content_font)

        clip_type = data.get("clip_type", "text")
        # 为星标按钮 + 时间让出空间
        text_rect = rect.adjusted(0, 0, -120, 0)

        if clip_type == "image":
            # 图片类型：尝试显示缩略图
            image_data = data.get("image_data")
            if image_data:
                try:
                    pixmap = QPixmap()
                    pixmap.loadFromData(image_data)
                    thumb_rect = QRect(text_rect.left(), text_rect.top(), 24, 24)
                    painter.drawPixmap(thumb_rect, pixmap.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    text_rect.setLeft(thumb_rect.right() + 6)
                except Exception:
                    pass
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             "[图片]")
        elif clip_type == "file":
            # 文件类型：显示 📁 + 文件名
            paths = json.loads(data.get("file_paths", "[]"))
            names = [p.rsplit("\\", 1)[-1] for p in paths]
            display = ", ".join(names[:3])
            if len(names) > 3:
                display += f" 等 {len(names)} 个文件"
            painter.setPen(option.palette.text().color())
            elided = painter.fontMetrics().elidedText(
                display, Qt.TextElideMode.ElideRight, text_rect.width()
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
        else:
            painter.setPen(option.palette.text().color())
            content_text = data.get("content", "").replace("\n", " ")
            elided = painter.fontMetrics().elidedText(
                content_text, Qt.TextElideMode.ElideRight, text_rect.width()
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # ---- 分隔线 ----
        painter.setPen(QPen(QColor(230, 230, 230), 1))
        painter.drawLine(option.rect.left(), option.rect.bottom(), option.rect.right(), option.rect.bottom())

        painter.restore()

    def editorEvent(self, event, model, option, index):
        """处理鼠标点击星标区域。"""
        if event.type() == event.Type.MouseButtonRelease:
            star_rect = self._star_rect(option.rect)
            if star_rect.contains(event.pos()):
                data = index.data(Qt.ItemDataRole.UserRole)
                if data and self._star_callback:
                    self._star_callback(data["id"])
                return True
        return super().editorEvent(event, model, option, index)