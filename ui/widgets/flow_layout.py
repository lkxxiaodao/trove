"""自适应换行布局 - FlowLayout。

参考 Qt 官方 FlowLayout 示例，实现卡片式自动换行排列。
"""

from PySide6.QtWidgets import QLayout, QWidgetItem, QWidget, QSizePolicy, QLayoutItem
from PySide6.QtCore import Qt, QRect, QSize, QPoint


class FlowLayout(QLayout):
    """自适应换行布局。

    将子控件从左到右排列，超出容器宽度时自动换行。
    """

    def __init__(self, parent=None, margin: int = 8, spacing: int = 8):
        super().__init__(parent)
        self._items: list[QWidgetItem] = []
        self._margin = margin
        self._spacing = spacing
        if parent:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def __del__(self):
        self._clear()

    def _clear(self):
        while self._items:
            item = self._items.pop()
            if item.widget():
                item.widget().deleteLater()
            del item

    def addItem(self, item: QLayoutItem):
        self._items.append(item)
        self.invalidate()

    def addWidget(self, widget: QWidget):
        item = QWidgetItem(widget)
        self.addItem(item)

    def removeWidget(self, widget: QWidget):
        for item in self._items:
            if item.widget() is widget:
                self._items.remove(item)
                self.invalidate()
                break

    def clear(self):
        """清空所有子控件并重置布局。"""
        while self._items:
            item = self._items.pop()
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.invalidate()

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self._calc_size()

    def minimumSize(self) -> QSize:
        return self._calc_size()

    def _calc_size(self) -> QSize:
        """基于实际布局计算所需尺寸。"""
        if not self._items:
            margins = self.contentsMargins()
            return QSize(
                margins.left() + margins.right(),
                margins.top() + margins.bottom(),
            )
        # 使用父容器宽度计算实际高度
        parent_widget = self.parentWidget()
        if parent_widget:
            width = parent_widget.width()
            # 如果父容器宽度有效，按实际宽度计算
            if width > 0:
                height = self.heightForWidth(width)
                return QSize(width, height)
        # 回退：使用最大子项尺寸
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom(),
        )
        return size

    def _do_layout(self, rect: QRect, test_only: bool = False) -> int:
        margins = self.contentsMargins()
        available = rect.adjusted(
            margins.left(), margins.top(),
            -margins.right(), -margins.bottom(),
        )
        x = available.x()
        y = available.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            if widget and not widget.isVisible():
                continue
            item_size = item.sizeHint()
            # 换行
            if x + item_size.width() > available.right() and x > available.x():
                x = available.x()
                y += line_height + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))
            x += item_size.width() + self._spacing
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + margins.bottom()