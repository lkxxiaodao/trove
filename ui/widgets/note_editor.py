"""笔记编辑对话框 - NoteEditor。

编辑标题、内容（支持图片）、颜色（含字体色）、标签。
"""

import os
import uuid
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit,
    QPushButton, QLabel, QMessageBox, QFileDialog, QColorDialog,
    QWidget,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor

from core.note_manager import NoteStore
from config import AppConfig


# 辅助：判断内容是否为 HTML
def _is_html(content: str) -> bool:
    return bool(content) and (
        content.strip().startswith("<!DOCTYPE")
        or content.strip().startswith("<html")
        or "<img" in content
        or "<p" in content
        or "<div" in content
    )


class NoteEditor(QDialog):
    """笔记编辑对话框。

    信号:
        saved(note_id): 保存成功后发出
    """

    saved = Signal(int)

    def __init__(self, note_store: NoteStore, note_data: dict = None, parent=None):
        super().__init__(parent)
        self._store = note_store
        self._note_data = note_data
        self._is_new = note_data is None
        self._selected_color = note_data.get("color", "#FFFFFF") if note_data else "#FFFFFF"
        self._selected_font_color = note_data.get("font_color", "#000000") if note_data else "#000000"
        tags = note_data.get("tags", []) if note_data else []
        self._tag_id = tags[0]["id"] if tags else None

        self.setWindowTitle("新建笔记" if self._is_new else "编辑笔记")
        self.resize(520, 560)
        self.setMinimumSize(420, 400)
        self._init_ui()
        self._load_data()

    @property
    def _preset_colors(self):
        return AppConfig.instance().NOTE_PRESET_COLORS

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ---- 标题 ----
        layout.addWidget(QLabel("标题"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("输入笔记标题...")
        layout.addWidget(self._title_edit)

        # ---- 内容工具栏 ----
        content_toolbar = QHBoxLayout()
        content_toolbar.setSpacing(4)
        content_toolbar.addWidget(QLabel("内容"))
        content_toolbar.addStretch()

        insert_img_btn = QPushButton("🖼 插入图片")
        insert_img_btn.setFixedHeight(26)
        insert_img_btn.setToolTip("从文件选择图片插入到笔记中")
        insert_img_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 0 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #e3f2fd;
                border-color: #1a73e8;
            }
        """)
        insert_img_btn.clicked.connect(self._insert_image)
        content_toolbar.addWidget(insert_img_btn)
        layout.addLayout(content_toolbar)
        self._content_edit = QTextEdit()
        self._content_edit.setPlaceholderText("输入笔记内容...（支持粘贴或插入图片）")
        self._content_edit.setMinimumHeight(140)
        self._content_edit.setAcceptRichText(True)
        layout.addWidget(self._content_edit, 1)

        # ---- 颜色选择 ----
        layout.addWidget(QLabel("背景颜色（点击选择，再点击框内选中的即为当前）"))
        color_layout = QHBoxLayout()
        color_layout.setSpacing(4)
        self._color_buttons = {}
        self._font_color_buttons = {}

        for entry in self._preset_colors:
            name = entry["name"]
            bg = entry["bg"]
            font = entry["font"]

            # 每个颜色项的容器
            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(2)

            # 背景色按钮
            bg_btn = QPushButton()
            bg_btn.setFixedSize(32, 32)
            bg_btn.setToolTip(f"{name} — 背景: {bg}  字体: {font}")
            bg_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg};
                    border: 2px solid #ccc;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border-color: #888;
                }}
            """)
            bg_btn.clicked.connect(lambda checked, b=bg, f=font, n=name: self._on_color_pick(b, f, n))
            item_layout.addWidget(bg_btn, alignment=Qt.AlignmentFlag.AlignCenter)

            # 字体颜色小圆点
            font_dot = QLabel()
            font_dot.setFixedSize(12, 12)
            font_dot.setStyleSheet(
                f"background: {font}; border: 1px solid #aaa; border-radius: 6px;"
            )
            font_dot.setToolTip(f"字体颜色: {font}（点击可改）")
            font_dot.setCursor(Qt.CursorShape.PointingHandCursor)
            font_dot.mousePressEvent = lambda e, n=name: self._on_font_color_pick(n)
            item_layout.addWidget(font_dot, alignment=Qt.AlignmentFlag.AlignCenter)

            color_layout.addWidget(item_widget)
            self._color_buttons[name] = bg_btn
            self._font_color_buttons[name] = font_dot

        # 自定义颜色按钮
        custom_widget = QWidget()
        custom_layout = QVBoxLayout(custom_widget)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(2)

        self._custom_bg_btn = QPushButton()
        self._custom_bg_btn.setFixedSize(32, 32)
        self._custom_bg_btn.setToolTip("自定义背景颜色（点击取色）")
        self._custom_bg_btn.setStyleSheet("""
            QPushButton {
                border: 2px dashed #ccc;
                border-radius: 4px;
                font-size: 14px;
                background: #fafafa;
            }
            QPushButton:hover {
                border-color: #888;
                background: #f0f0f0;
            }
        """)
        self._custom_bg_btn.clicked.connect(self._on_custom_bg_color)
        custom_layout.addWidget(self._custom_bg_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        custom_label = QLabel("自定义")
        custom_label.setStyleSheet("color: #999; font-size: 10px;")
        custom_layout.addWidget(custom_label, alignment=Qt.AlignmentFlag.AlignCenter)
        color_layout.addWidget(custom_widget)

        # 当前字体颜色显示
        self._font_color_preview = QLabel()
        self._font_color_preview.setFixedSize(24, 24)
        self._font_color_preview.setToolTip("当前字体颜色（点击可更改）")
        self._font_color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self._font_color_preview.setStyleSheet(
            f"background: {self._selected_font_color};"
            "border: 2px solid #999; border-radius: 4px;"
        )
        self._font_color_preview.mousePressEvent = lambda e: self._on_pick_font_color()
        color_layout.addWidget(self._font_color_preview)

        color_layout.addStretch()
        layout.addLayout(color_layout)

        # ---- 标签（最多 1 个，最多 5 字） ----
        layout.addWidget(QLabel("标签（最多 5 字）"))
        tag_layout = QHBoxLayout()
        tag_layout.setSpacing(6)
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("输入标签名后回车添加...")
        self._tag_input.setMaxLength(5)
        self._tag_input.returnPressed.connect(self._add_tag)
        tag_layout.addWidget(self._tag_input, 1)
        layout.addLayout(tag_layout)

        self._current_tag_chip = QPushButton()
        self._current_tag_chip.setFixedHeight(24)
        self._current_tag_chip.setStyleSheet("""
            QPushButton {
                background: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 0 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #ccc;
            }
        """)
        self._current_tag_chip.hide()
        self._current_tag_chip.clicked.connect(self._remove_tag)
        layout.addWidget(self._current_tag_chip)

        # ---- 按钮 ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        # 初始刷新选中样式
        self._refresh_color_selection()

    def _load_data(self):
        if self._note_data:
            self._title_edit.setText(self._note_data.get("title", ""))
            content = self._note_data.get("content", "")
            if content and _is_html(content):
                self._content_edit.setHtml(content)
            else:
                self._content_edit.setPlainText(content)
            self._selected_color = self._note_data.get("color", "#FFFFFF")
            self._selected_font_color = self._note_data.get("font_color", "#000000")
            tags = self._note_data.get("tags", [])
            self._tag_id = tags[0]["id"] if tags else None
        self._refresh_tag_chip()
        self._refresh_color_selection()

    # ---- 颜色选择 ----

    def _on_color_pick(self, bg: str, font: str, name: str):
        """选中预设颜色。"""
        self._selected_color = bg
        self._selected_font_color = font
        self._refresh_color_selection()

    def _on_font_color_pick(self, name: str):
        """修改预设颜色的字体颜色。"""
        current = QColor(self._selected_font_color)
        color = QColorDialog.getColor(current, self, f"选择「{name}」的字体颜色")
        if not color.isValid():
            return

        # 更新配置中的预设颜色
        config = AppConfig.instance()
        for entry in config.NOTE_PRESET_COLORS:
            if entry["name"] == name:
                entry["font"] = color.name()
                break
        config.save()

        self._selected_font_color = color.name()
        self._refresh_color_selection()
        self._rebuild_color_ui()

        QMessageBox.information(self, "提示", f"「{name}」的字体颜色已更新为 {color.name()}，下次打开新建笔记时生效。")

    def _on_custom_bg_color(self):
        """自定义背景颜色。"""
        current = QColor(self._selected_color)
        color = QColorDialog.getColor(current, self, "选择自定义背景颜色")
        if color.isValid():
            self._selected_color = color.name()
            self._refresh_color_selection()

    def _on_pick_font_color(self):
        """单独选择字体颜色。"""
        current = QColor(self._selected_font_color)
        color = QColorDialog.getColor(current, self, "选择字体颜色")
        if color.isValid():
            self._selected_font_color = color.name()
            self._font_color_preview.setStyleSheet(
                f"background: {self._selected_font_color};"
                "border: 2px solid #999; border-radius: 4px;"
            )

    def _refresh_color_selection(self):
        """刷新颜色按钮的选中高亮效果。"""
        selected_name = None
        for entry in self._preset_colors:
            if entry["bg"] == self._selected_color:
                selected_name = entry["name"]
                break

        for name, btn in self._color_buttons.items():
            if name == selected_name:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {self._selected_color};
                        border: 3px solid #1a73e8;
                        border-radius: 4px;
                    }}
                """)
            else:
                entry = next((e for e in self._preset_colors if e["name"] == name), None)
                bg = entry["bg"] if entry else "#FFFFFF"
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {bg};
                        border: 2px solid #ccc;
                        border-radius: 4px;
                    }}
                    QPushButton:hover {{
                        border-color: #888;
                    }}
                """)

        # 自定义颜色按钮：如果当前选中色不是预设色，显示为实心预览
        if selected_name is None:
            self._custom_bg_btn.setText("")
            self._custom_bg_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._selected_color};
                    border: 3px solid #1a73e8;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border-color: #888;
                }}
            """)
            self._custom_bg_btn.setToolTip(f"自定义背景颜色: {self._selected_color}（点击更换）")
        else:
            self._custom_bg_btn.setText("🎨")
            self._custom_bg_btn.setStyleSheet("""
                QPushButton {
                    border: 2px dashed #ccc;
                    border-radius: 4px;
                    font-size: 14px;
                    background: #fafafa;
                }
                QPushButton:hover {
                    border-color: #888;
                    background: #f0f0f0;
                }
            """)
            self._custom_bg_btn.setToolTip("自定义背景颜色（点击取色）")

        # 更新字体颜色预览
        self._font_color_preview.setStyleSheet(
            f"background: {self._selected_font_color};"
            "border: 2px solid #999; border-radius: 4px;"
        )

    def _rebuild_color_ui(self):
        """重建颜色按钮区域（字体颜色更改后需要刷新 tooltip 等）。"""
        for name, btn in self._color_buttons.items():
            entry = next((e for e in self._preset_colors if e["name"] == name), None)
            if entry:
                btn.setToolTip(f"{name} — 背景: {entry['bg']}  字体: {entry['font']}")

        for name, dot in self._font_color_buttons.items():
            entry = next((e for e in self._preset_colors if e["name"] == name), None)
            if entry:
                dot.setStyleSheet(
                    f"background: {entry['font']}; border: 1px solid #aaa; border-radius: 6px;"
                )
                dot.setToolTip(f"字体颜色: {entry['font']}（点击可改）")

    # ---- 图片插入 ----

    def _insert_image(self):
        """打开文件对话框，将选中的图片插入编辑器。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "插入图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;所有文件 (*.*)"
        )
        if not file_path:
            return

        # 复制图片到数据目录
        config = AppConfig.instance()
        images_dir = os.path.join(config.DATA_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)

        ext = os.path.splitext(file_path)[1] or ".png"
        unique_name = f"note_img_{uuid.uuid4().hex[:8]}{ext}"
        dest_path = os.path.join(images_dir, unique_name)

        try:
            import shutil
            shutil.copy2(file_path, dest_path)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"复制图片失败: {e}")
            return

        # 在光标位置插入图片
        cursor = self._content_edit.textCursor()
        # 使用 file:/// URL
        img_path = dest_path.replace("\\", "/")
        cursor.insertHtml(f'<img src="file:///{img_path}" style="max-width:100%;">')
        # 插入换行使后续输入方便
        cursor.insertHtml("<br>")

    # ---- 标签 ----

    def _add_tag(self):
        name = self._tag_input.text().strip()[:5]
        if not name:
            return
        tag_id = self._store.add_tag(name)
        if tag_id > 0:
            self._tag_id = tag_id
        self._tag_input.clear()
        self._refresh_tag_chip()

    def _refresh_tag_chip(self):
        if self._tag_id:
            all_tags = self._store.get_all_tags()
            tag_name = next((t["name"] for t in all_tags if t["id"] == self._tag_id), str(self._tag_id))
            self._current_tag_chip.setText(f"× {tag_name}")
            self._current_tag_chip.show()
        else:
            self._current_tag_chip.hide()

    def _remove_tag(self):
        self._tag_id = None
        self._refresh_tag_chip()

    def _on_save(self):
        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "标题不能为空")
            return

        self._flush_tag_input()

        # 获取内容（HTML 格式）
        content = self._content_edit.toHtml()

        if self._is_new:
            note_id = self._store.create(title, content)
        else:
            note_id = self._note_data["id"]
            self._store.update(note_id, title=title, content=content)

        self._store.update(note_id, color=self._selected_color, font_color=self._selected_font_color)
        self._store.set_note_tags(note_id, [self._tag_id] if self._tag_id else [])
        self.saved.emit(note_id)
        self.accept()

    def _flush_tag_input(self):
        """将输入框中的未回车文本转为标签（供保存时调用）。"""
        name = self._tag_input.text().strip()[:5]
        if name:
            tag_id = self._store.add_tag(name)
            if tag_id > 0:
                self._tag_id = tag_id
            self._tag_input.clear()
            self._refresh_tag_chip()
