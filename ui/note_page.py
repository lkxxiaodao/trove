"""微笔记管理页面 - NotePage。

显示所有笔记卡片，管理悬浮窗口，支持创建/编辑/删除/搜索/标签与颜色筛选。
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QMessageBox, QDialog, QLabel, QComboBox,
)
from PySide6.QtCore import Qt, Signal

from core.note_manager import NoteStore
from ui.widgets.card_flow import CardFlowWidget
from ui.widgets.note_card import NoteCard
from ui.widgets.note_editor import NoteEditor
from ui.widgets.note_float import NoteFloatWindow
from config import AppConfig

log = logging.getLogger("trove.note")

# 从配置中获取颜色（向后兼容：提供 bg 色映射）
def _get_filter_colors():
    config = AppConfig.instance()
    return {c["name"]: c["bg"] for c in config.NOTE_PRESET_COLORS}


def _get_font_colors():
    config = AppConfig.instance()
    return {c["name"]: c["font"] for c in config.NOTE_PRESET_COLORS}


class NotePage(QWidget):
    """微笔记管理主页面。"""

    def __init__(self, note_store: NoteStore, font_size: int = 14):
        super().__init__()
        self._store = note_store
        self._font_size = font_size
        self._cards: list[NoteCard] = []
        self._float_windows: dict[int, NoteFloatWindow] = {}
        self._selected_tag_id: int | None = None  # 单选标签
        self._selected_color: str | None = None
        self._sort_by = "modified"
        self._batch_mode = False
        self._init_ui()
        self._refresh()
        self._restore_floating()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # ---- 顶部工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        new_btn = QPushButton("+ 新建笔记")
        new_btn.setFixedHeight(30)
        new_btn.setMinimumWidth(105)
        new_btn.clicked.connect(self._on_new)
        toolbar.addWidget(new_btn)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索笔记...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search_input, 1)

        sort_btn = QPushButton("排序: 时间")
        sort_btn.setFixedHeight(30)
        sort_btn.setMinimumWidth(100)
        sort_btn.clicked.connect(self._toggle_sort)
        self._sort_btn = sort_btn
        toolbar.addWidget(sort_btn)

        # 批量操作按钮（默认隐藏）
        self._batch_bar = QHBoxLayout()
        self._batch_bar.setSpacing(6)
        self._batch_select_btn = QPushButton("批量选择")
        self._batch_select_btn.setFixedHeight(30)
        self._batch_select_btn.setMinimumWidth(70)
        self._batch_select_btn.clicked.connect(self._on_toggle_batch_mode)
        self._batch_bar.addWidget(self._batch_select_btn)

        self._batch_color_btn = QPushButton("设置颜色")
        self._batch_color_btn.setFixedHeight(30)
        self._batch_color_btn.setMinimumWidth(70)
        self._batch_color_btn.hide()
        self._batch_color_btn.clicked.connect(self._on_batch_color)
        self._batch_bar.addWidget(self._batch_color_btn)

        self._batch_tag_btn = QPushButton("设置标签")
        self._batch_tag_btn.setFixedHeight(30)
        self._batch_tag_btn.setMinimumWidth(70)
        self._batch_tag_btn.hide()
        self._batch_tag_btn.clicked.connect(self._on_batch_tag)
        self._batch_bar.addWidget(self._batch_tag_btn)

        self._batch_delete_btn = QPushButton("删除选中")
        self._batch_delete_btn.setFixedHeight(30)
        self._batch_delete_btn.setMinimumWidth(70)
        self._batch_delete_btn.setStyleSheet("color: #d32f2f;")
        self._batch_delete_btn.hide()
        self._batch_delete_btn.clicked.connect(self._on_batch_delete)
        self._batch_bar.addWidget(self._batch_delete_btn)

        self._batch_cancel_btn = QPushButton("取消")
        self._batch_cancel_btn.setFixedHeight(30)
        self._batch_cancel_btn.setMinimumWidth(50)
        self._batch_cancel_btn.hide()
        self._batch_cancel_btn.clicked.connect(self._on_toggle_batch_mode)
        self._batch_bar.addWidget(self._batch_cancel_btn)

        toolbar.addLayout(self._batch_bar)

        main_layout.addLayout(toolbar)

        # ---- 标签栏 ----
        self._tag_bar = QHBoxLayout()
        self._tag_bar.setAlignment(Qt.AlignmentFlag.AlignLeft)
        main_layout.addLayout(self._tag_bar)

        # ---- 卡片墙（ScrollArea + CardFlowWidget） ----
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._card_flow = CardFlowWidget(spacing=10)
        self._card_flow.order_changed.connect(self._on_order_changed)
        self._scroll_area.setWidget(self._card_flow)
        main_layout.addWidget(self._scroll_area, 1)

    # ---- 数据刷新 ----
    def _refresh(self):
        try:
            self._do_refresh()
        except Exception as e:
            log.error(f"刷新笔记页面失败: {e}", exc_info=True)

    def _do_refresh(self):
        self._card_flow.clear()
        self._cards.clear()

        tag_list = [self._selected_tag_id] if self._selected_tag_id else None
        notes = self._store.get_all(
            tag_ids=tag_list,
            sort_by=self._sort_by,
            color=self._selected_color,
        )
        log.info(f"刷新笔记: 查询到 {len(notes)} 条")
        for note in notes:
            log.debug(f"  笔记 id={note.get('id')}, title={note.get('title')!r}, content长度={len(note.get('content', ''))}")
            card = NoteCard(note)
            card.double_clicked.connect(self._on_edit)
            card.float_toggled.connect(self._on_float_toggle)
            card.delete_requested.connect(self._on_delete_single)
            if self._batch_mode:
                card.set_select_mode(True)
            self._cards.append(card)
            self._card_flow.add_card(card)

        self._card_flow.layout_cards()
        self._refresh_tag_bar()

    def _refresh_tag_bar(self):
        while self._tag_bar.count():
            child = self._tag_bar.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 全部按钮（清除标签和颜色筛选）
        all_btn = QPushButton("全部")
        all_btn.setCheckable(True)
        all_btn.setChecked(not self._selected_tag_id and not self._selected_color)
        all_btn.setStyleSheet(
            "QPushButton { padding: 4px 8px; border-radius: 4px; }"
            "QPushButton:checked { background: #1a73e8; color: #fff; }"
        )
        all_btn.clicked.connect(self._on_clear_filters)
        self._tag_bar.addWidget(all_btn)

        # 分隔符
        sep = QLabel("|")
        sep.setStyleSheet("color: #ccc; padding: 0 4px;")
        self._tag_bar.addWidget(sep)

        # 标签筛选下拉框
        self._tag_combo = QComboBox()
        self._tag_combo.setMinimumWidth(80)
        self._tag_combo.setMaximumWidth(100)
        self._tag_combo.setToolTip("按标签筛选")
        self._tag_combo.setStyleSheet(
            "QComboBox { text-align: left; }"
            "QComboBox QAbstractItemView { text-align: left; }"
        )
        self._tag_combo.addItem("全部标签", None)  # 默认项
        all_tags = self._store.get_all_tags()
        for tag in all_tags:
            self._tag_combo.addItem(tag["name"], tag["id"])
        # 当前选中
        if self._selected_tag_id:
            for i in range(self._tag_combo.count()):
                if self._tag_combo.itemData(i) == self._selected_tag_id:
                    self._tag_combo.setCurrentIndex(i)
                    break
        self._tag_combo.currentIndexChanged.connect(self._on_tag_combo_changed)
        self._tag_bar.addWidget(self._tag_combo)

        # 颜色筛选分隔
        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #ccc; padding: 0 4px;")
        self._tag_bar.addWidget(sep2)

        # 颜色筛选按钮
        filter_colors = _get_filter_colors()
        for name, color in filter_colors.items():
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setToolTip(f"颜色筛选: {name} ({color})")
            btn.setCheckable(True)
            btn.setChecked(color == self._selected_color)
            border = "3px solid #1a73e8" if color == self._selected_color else "1px solid #aaa"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    border: {border};
                    border-radius: 3px;
                    padding: 0;
                }}
                QPushButton:hover {{
                    border-color: #555;
                }}
            """)
            btn.clicked.connect(lambda checked, c=color: self._on_color_click(c))
            self._tag_bar.addWidget(btn)

        self._tag_bar.addStretch()

    def _on_tag_combo_changed(self, index: int):
        if index < 0:
            return
        tag_id = self._tag_combo.itemData(index)
        if tag_id != self._selected_tag_id:
            self._selected_tag_id = tag_id
            self._refresh()

    def _on_clear_filters(self):
        """清除所有标签和颜色筛选。"""
        self._selected_tag_id = None
        self._selected_color = None
        self._refresh()

    def _on_color_click(self, color: str):
        """点击颜色筛选按钮，切换选中状态。"""
        if self._selected_color == color:
            self._selected_color = None
        else:
            self._selected_color = color
        self._refresh()

    def _toggle_sort(self):
        if self._sort_by == "modified":
            self._sort_by = "sort_order"
            self._sort_btn.setText("排序: 自定义")
            self._card_flow.set_drag_enabled(True)
        else:
            self._sort_by = "modified"
            self._sort_btn.setText("排序: 时间")
            self._card_flow.set_drag_enabled(False)
        self._refresh()

    def _on_order_changed(self, note_ids: list[int]):
        """拖拽排序后更新数据库中的 sort_order。"""
        self._store.reorder(note_ids)
        # 更新内存中的卡片列表顺序以匹配 UI
        id_to_card = {c._note_id: c for c in self._cards}
        self._cards = [id_to_card[nid] for nid in note_ids if nid in id_to_card]

    def _on_search(self, text: str):
        if not text.strip():
            self._refresh()
            return
        self._card_flow.clear()
        self._cards.clear()
        notes = self._store.search(text.strip())
        for note in notes:
            card = NoteCard(note)
            card.double_clicked.connect(self._on_edit)
            card.float_toggled.connect(self._on_float_toggle)
            card.delete_requested.connect(self._on_delete_single)
            if self._batch_mode:
                card.set_select_mode(True)
            self._cards.append(card)
            self._card_flow.add_card(card)
        self._card_flow.layout_cards()

    # ---- 操作 ----
    def _on_new(self):
        if self._batch_mode:
            return
        dlg = NoteEditor(self._store, parent=self)
        dlg.saved.connect(self._on_note_saved)
        dlg.exec()

    def _on_edit(self, note_id: int):
        if self._batch_mode:
            return
        note = self._store.get(note_id)
        if not note:
            return
        dlg = NoteEditor(self._store, note, self)
        dlg.saved.connect(self._on_note_saved)
        dlg.exec()

    def _on_note_saved(self, note_id: int):
        """编辑保存后，刷新卡片和对应悬浮窗口。"""
        self._refresh()
        self._update_float_window(note_id)

    def _on_delete_single(self, note_id: int):
        """删除单条笔记。"""
        reply = QMessageBox.question(
            self, "确认删除",
            "确定删除这条笔记吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._hide_float_window(note_id)
        self._store.delete(note_id)
        self._refresh()

    def _on_float_toggle(self, note_id: int, floating: bool):
        self._store.set_floating(note_id, floating)
        if floating:
            self._show_float_window(note_id)
        else:
            self._hide_float_window(note_id)

    # ---- 悬浮窗口管理 ----
    def _show_float_window(self, note_id: int):
        if note_id in self._float_windows:
            self._float_windows[note_id].show()
            return
        note = self._store.get(note_id)
        if not note:
            return
        win = NoteFloatWindow(note, self._font_size)
        win.unfloated.connect(self._on_float_window_closed)
        win.edit_requested.connect(self._on_edit)
        self._float_windows[note_id] = win

    def _hide_float_window(self, note_id: int):
        if note_id in self._float_windows:
            self._float_windows[note_id].close()
            del self._float_windows[note_id]

    def _on_float_window_closed(self, note_id: int):
        self._store.set_floating(note_id, False)
        if note_id in self._float_windows:
            self._float_windows[note_id].close()
            del self._float_windows[note_id]
        # 更新卡片状态
        for card in self._cards:
            if card._note_id == note_id:
                card.set_floating_state(False)
                break

    def _update_float_window(self, note_id: int):
        if note_id in self._float_windows:
            note = self._store.get(note_id)
            if note:
                self._float_windows[note_id].update_content(note, self._font_size)

    def _restore_floating(self):
        """启动时恢复所有悬浮笔记。"""
        floating_notes = self._store.get_floating()
        for note in floating_notes:
            self._show_float_window(note["id"])

    def set_font_size(self, size: int):
        """更新所有悬浮窗口的字体大小。"""
        self._font_size = size
        for win in self._float_windows.values():
            win._set_font()

    def close_all_floats(self):
        """关闭所有悬浮窗口（退出时调用）。"""
        for win in list(self._float_windows.values()):
            win.close()
        self._float_windows.clear()

    # ---- 批量操作 ----
    def _on_toggle_batch_mode(self):
        """切换批量选择模式。"""
        self._batch_mode = not self._batch_mode
        self._batch_select_btn.setVisible(not self._batch_mode)
        self._batch_color_btn.setVisible(self._batch_mode)
        self._batch_tag_btn.setVisible(self._batch_mode)
        self._batch_delete_btn.setVisible(self._batch_mode)
        self._batch_cancel_btn.setVisible(self._batch_mode)
        for card in self._cards:
            card.set_select_mode(self._batch_mode)

    def _get_selected_ids(self) -> list[int]:
        """获取当前选中的笔记 ID 列表。"""
        return [card._note_id for card in self._cards if card.is_checked()]

    def _on_batch_color(self):
        """批量设置选中笔记的颜色。"""
        selected = self._get_selected_ids()
        if not selected:
            QMessageBox.information(self, "提示", "未选中任何笔记。")
            return

        # 弹出颜色选择对话框
        dlg = QDialog(self)
        dlg.setWindowTitle("批量设置颜色")
        dlg.setFixedSize(320, 80)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.addWidget(QLabel("选择颜色："))
        btn_layout = QHBoxLayout()
        chosen_color = [None]  # 用列表在闭包中可变
        chosen_font = ["#000000"]

        filter_colors = _get_filter_colors()
        font_colors = _get_font_colors()
        for name, color in filter_colors.items():
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            font_c = font_colors.get(name, "#000000")
            btn.setToolTip(f"{name} (字体: {font_c})")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    border: 2px solid #ccc;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border-color: #888;
                }}
            """)
            btn.clicked.connect(lambda checked, c=color, fc=font_c: [chosen_color.__setitem__(0, c), chosen_font.__setitem__(0, fc), dlg.accept()])
            btn_layout.addWidget(btn)
        btn_layout.addStretch()
        dlg_layout.addLayout(btn_layout)

        if dlg.exec() != QDialog.DialogCode.Accepted or not chosen_color[0]:
            return

        for nid in selected:
            self._store.update(nid, color=chosen_color[0], font_color=chosen_font[0])
        # 同步更新悬浮窗
        for nid in selected:
            self._update_float_window(nid)
        self._refresh()
        QMessageBox.information(self, "成功", f"已为 {len(selected)} 条笔记设置颜色。")

    def _on_batch_tag(self):
        """批量设置选中笔记的标签（最多 1 个，最多 5 字）。"""
        selected = self._get_selected_ids()
        if not selected:
            QMessageBox.information(self, "提示", "未选中任何笔记。")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("批量设置标签")
        dlg.setFixedSize(300, 130)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.addWidget(QLabel("选择一个标签（替换原有标签）："))

        # 标签下拉框
        tag_combo = QComboBox()
        tag_combo.addItem("不设置（清除标签）", None)
        all_tags = self._store.get_all_tags()
        for tag in all_tags:
            tag_combo.addItem(tag["name"], tag["id"])
        tag_combo.setCurrentIndex(0)
        dlg_layout.addWidget(tag_combo)

        # 新增标签输入
        new_layout = QHBoxLayout()
        new_tag_input = QLineEdit()
        new_tag_input.setPlaceholderText("或输入新标签名（最多 5 字）...")
        new_tag_input.setMaxLength(5)
        add_btn = QPushButton("添加并应用")
        new_layout.addWidget(new_tag_input)
        new_layout.addWidget(add_btn)
        dlg_layout.addLayout(new_layout)

        chosen_id = [None]  # mutable

        tag_combo.currentIndexChanged.connect(
            lambda idx: chosen_id.__setitem__(0, tag_combo.itemData(idx))
        )

        add_btn.clicked.connect(
            lambda: self._batch_add_and_apply(new_tag_input, tag_combo, chosen_id)
        )
        new_tag_input.returnPressed.connect(
            lambda: self._batch_add_and_apply(new_tag_input, tag_combo, chosen_id)
        )

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        apply_btn = QPushButton("应用")
        apply_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(apply_btn)
        dlg_layout.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        tag_id = chosen_id[0]
        tag_ids = [tag_id] if tag_id else []
        for nid in selected:
            self._store.set_note_tags(nid, tag_ids)
        for nid in selected:
            self._update_float_window(nid)
        self._refresh()
        QMessageBox.information(self, "成功", f"已为 {len(selected)} 条笔记设置标签。")

    def _batch_add_and_apply(self, input_widget, combo, chosen_id):
        """批量标签对话框：创建新标签并切换到它。"""
        name = input_widget.text().strip()[:5]
        if not name:
            return
        tag_id = self._store.add_tag(name)
        if tag_id > 0:
            # 添加到下拉框
            combo.addItem(name, tag_id)
            combo.setCurrentIndex(combo.count() - 1)
            chosen_id[0] = tag_id
            input_widget.clear()

    def _on_batch_delete(self):
        """批量删除选中笔记。"""
        selected = self._get_selected_ids()
        if not selected:
            QMessageBox.information(self, "提示", "未选中任何笔记。")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除选中的 {len(selected)} 条笔记吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 关闭对应悬浮窗
        for nid in selected:
            self._hide_float_window(nid)

        self._store.delete_many(selected)
        self._on_toggle_batch_mode()  # 退出批量模式
        self._refresh()

    def add_note_from_clip(self, content: str):
        """从剪贴板创建笔记。"""
        try:
            title = content[:50].replace("\n", " ") if content else "未命名"
            note_id = self._store.create(title, content)
            log.info(f"从剪贴板创建笔记: id={note_id}, title={title!r}")
            self._refresh()
        except Exception as e:
            log.error(f"从剪贴板创建笔记失败: {e}", exc_info=True)


def create_page(note_store: NoteStore, font_size: int = 14) -> QWidget:
    """创建 NotePage（工厂函数）。"""
    return NotePage(note_store, font_size)