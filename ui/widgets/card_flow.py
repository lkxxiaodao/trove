"""自适应卡片流式容器 - CardFlowWidget。

手动 positioning，完全避开 Qt 布局系统的更新时序问题。
支持拖拽排序（自定义排序模式下）。
"""

from PySide6.QtWidgets import (
    QWidget, QScrollArea, QLabel, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import QSize, Qt, Signal, QPoint


class CardFlowWidget(QWidget):
    """自适应卡片容器 —— 手动 positioning 实现。

    信号:
        order_changed(list[int]): 拖拽后新的 note_id 顺序
    """

    order_changed = Signal(list)

    def __init__(self, parent=None, card_width: int = 220, spacing: int = 10):
        super().__init__(parent)
        self._card_width = card_width
        self._spacing = spacing
        self._cards: list[QWidget] = []
        self._total_height = 0
        self._drag_enabled = False

        # 拖拽状态
        self._drag_index: int | None = None
        self._drag_start: QPoint | None = None
        self._drag_offset: QPoint | None = None
        self._ghost: QLabel | None = None

    # ---- API ----

    def set_drag_enabled(self, enabled: bool):
        self._drag_enabled = enabled

    def clear(self):
        self._cancel_drag()
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._total_height = 0
        self.setMinimumHeight(0)
        self.updateGeometry()

    def add_card(self, widget: QWidget):
        widget.setParent(self)
        widget.show()
        self._cards.append(widget)

    def layout_cards(self):
        self._do_layout()
        self.updateGeometry()

    def cards(self) -> list:
        return self._cards

    def card_ids(self) -> list[int]:
        """返回当前卡片顺序下的 note_id 列表。"""
        return [int(c._note_id) for c in self._cards if hasattr(c, '_note_id')]

    # ---- 布局逻辑 ----

    def _do_layout(self):
        if not self._cards:
            self._total_height = 0
            self.setMinimumHeight(0)
            return

        w = self.width()
        if w <= 0:
            sp = self._scroll_parent_width()
            w = sp if sp > 0 else 800

        cols = max(1, (w + self._spacing) // (self._card_width + self._spacing))

        for i, card in enumerate(self._cards):
            col = i % cols
            row = i // cols
            x = col * (self._card_width + self._spacing)
            y = row * (card.height() + self._spacing)
            card.setGeometry(x, y, self._card_width, card.height())
            card.show()

        total_rows = (len(self._cards) + cols - 1) // cols
        ch = self._card_height()
        self._total_height = total_rows * (ch + self._spacing) - self._spacing
        self.setMinimumHeight(self._total_height)

    def _card_height(self) -> int:
        if self._cards:
            return self._cards[0].height()
        return 150

    def _scroll_parent_width(self) -> int:
        p = self.parent()
        if p and isinstance(p, QScrollArea):
            return p.viewport().width()
        return 0

    # ---- 拖拽（极简方案：拖过程中不做任何布局，松手一次性计算） ----

    def _card_index_at(self, pos: QPoint) -> int | None:
        """返回 pos 处直接命中的卡片索引，未命中返回 None。"""
        for i, card in enumerate(self._cards):
            if card.geometry().contains(pos):
                return i
        return None

    def _target_index(self, ghost_center: QPoint) -> int:
        """根据幽灵卡片中心位置，计算应插入的索引。"""
        if not self._cards:
            return 0
        w = self.width()
        if w <= 0:
            w = self._scroll_parent_width() or 800
        cols = max(1, (w + self._spacing) // (self._card_width + self._spacing))
        ch = self._card_height()

        # 找到幽灵中心所在的行列
        col = ghost_center.x() // (self._card_width + self._spacing)
        row = ghost_center.y() // (ch + self._spacing)
        col = max(0, col)
        row = max(0, row)
        grid_idx = row * cols + col

        # 判断插在 grid_idx 卡片之前还是之后
        # 先找到 grid_idx 对应卡片的中心 x
        card_center_x = col * (self._card_width + self._spacing) + self._card_width // 2
        if ghost_center.x() < card_center_x:
            target = grid_idx
        else:
            target = grid_idx + 1

        return min(target, len(self._cards))

    def mousePressEvent(self, event):
        if not self._drag_enabled or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        idx = self._card_index_at(event.pos())
        if idx is None:
            super().mousePressEvent(event)
            return
        self._drag_index = idx
        self._drag_start = event.pos()
        self._drag_offset = event.pos() - self._cards[idx].pos()

    def mouseMoveEvent(self, event):
        if self._drag_index is None:
            super().mouseMoveEvent(event)
            return

        if self._ghost is None:
            delta = event.pos() - (self._drag_start or event.pos())
            if abs(delta.x()) < 6 and abs(delta.y()) < 6:
                return
            self._start_drag()

        # 幽灵跟随光标，不做任何布局
        if self._ghost:
            self._ghost.move(event.pos() - (self._drag_offset or QPoint(0, 0)))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_index is None:
            super().mouseReleaseEvent(event)
            return

        # 计算目标位置
        if self._ghost:
            ghost_center = self._ghost.geometry().center()
        else:
            ghost_center = event.pos()
        target = self._target_index(ghost_center)

        # pop 原位置，insert 到目标
        src = self._drag_index
        card = self._cards.pop(src)
        adj = target if target <= src else target - 1
        self._cards.insert(adj, card)

        self._end_drag()

    def _start_drag(self):
        """创建科技风拖拽预览卡片。"""
        card = self._cards[self._drag_index]
        title = "未命名"
        if hasattr(card, '_note_data'):
            title = card._note_data.get("title", "未命名") or "未命名"

        self._ghost = QLabel(self)
        self._ghost.setFixedSize(self._card_width, 48)
        self._ghost.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ghost.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            "  stop:0 #1a73e8, stop:1 #4285f4);"
            "color: #fff;"
            "border-radius: 10px;"
            "font-size: 12px; font-weight: bold;"
            "padding: 4px 12px;"
        )
        self._ghost.setText(title)

        from PySide6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect(self._ghost)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(26, 115, 232, 80))
        self._ghost.setGraphicsEffect(shadow)

        self._ghost.move(card.pos())
        self._ghost.raise_()
        self._ghost.show()

    def _end_drag(self):
        if self._ghost:
            self._ghost.deleteLater()
            self._ghost = None
            self._do_layout()
            self.order_changed.emit(self.card_ids())
        self._drag_index = None
        self._drag_start = None
        self._drag_offset = None

    def _cancel_drag(self):
        if self._ghost:
            self._ghost.deleteLater()
            self._ghost = None
        self._drag_index = None
        self._drag_start = None
        self._drag_offset = None

    # ---- Qt overrides ----

    def sizeHint(self) -> QSize:
        return QSize(self._card_width, max(self._total_height, 0))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._cards and self._drag_index is None:
            self._do_layout()