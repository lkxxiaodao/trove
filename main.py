

import sys
import os
import ctypes
import ctypes.wintypes
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer, QTranslator, QLibraryInfo
from config import AppConfig, ensure_directories

# 单实例互斥体句柄（必须存活于整个进程生命周期，否则 Windows 自动释放）
_single_instance_mutex: ctypes.wintypes.HANDLE | None = None


def _suppress_shiboken_noise():
    """将 C 级 stderr 重定向到日志文件，抑制 Shiboken NoneType 刷屏警告。
    日志文件会捕获所有 stderr 输出，便于排查问题。
    """
    # 使用环境变量或默认路径来确定日志目录
    appdata = os.environ.get("TROVE_DATA_DIR", "")
    if not appdata:
        if sys.platform == "win32":
            appdata = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "trove")
        else:
            appdata = os.path.join(os.path.expanduser("~"), ".trove")
    log_dir = os.path.join(appdata, "logs")
    os.makedirs(log_dir, exist_ok=True)
    stderr_path = os.path.join(log_dir, "stderr.log")
    fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    os.dup2(fd, 2)  # 将 fd 2 (stderr) 重定向到日志文件
    os.close(fd)


def setup_logging(log_dir: str) -> logging.Logger:
    """配置日志系统，输出到文件和控制台。"""
    import os

    logger = logging.getLogger("trove")
    logger.setLevel(logging.DEBUG)

    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(
        os.path.join(log_dir, "app.log"), encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(console_handler)

    return logger


def _try_activate_existing_window() -> bool:
    """尝试找到已有 trove 窗口并激活。返回 True 表示找到了。"""
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, "trove")
    if hwnd:
        SW_RESTORE = 9
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    return False


def _check_single_instance() -> bool:
    """检查是否已有实例在运行。返回 True 表示这是唯一实例。

    使用 Windows 命名互斥体（Named Mutex），内核保证跨进程唯一性。
    互斥体句柄存于模块变量中，进程退出时自动释放。
    """
    global _single_instance_mutex

    kernel32 = ctypes.windll.kernel32
    mutex_name = "Global\\trove_SingleInstance_Mutex_v1"
    _single_instance_mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if not _single_instance_mutex:
        return True  # 创建失败，放行（不应发生）

    last_error = kernel32.GetLastError()
    if last_error != 183:  # ERROR_ALREADY_EXISTS = 183，没有同名互斥体 → 是首个实例
        return True

    # 已有实例在运行
    _try_activate_existing_window()
    return False


def main() -> int:
    # ---- 单实例检查（必须在创建 QApplication 之前） ----
    if not _check_single_instance():
        return 0

    _suppress_shiboken_noise()
    app = QApplication(sys.argv)
    app.setApplicationName("trove")
    app.setOrganizationName("trove")

    # 加载 Qt 中文翻译（修复 QColorDialog 等系统对话框的英文问题）
    translator = QTranslator()
    translations_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load("qt_zh_CN", translations_dir):
        app.installTranslator(translator)
    else:
        # 备选：从 PySide6 包目录查找
        import PySide6
        alt_dir = os.path.join(os.path.dirname(PySide6.__file__), "translations")
        if translator.load("qt_zh_CN", alt_dir):
            app.installTranslator(translator)

    # 应用图标
    icon_path = os.path.join(os.path.dirname(__file__), "icon.ico")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

    # ---- M00: 配置与目录 ----
    config = AppConfig.instance()
    ensure_directories(config)
    log = setup_logging(config.LOG_DIR)
    log.info("trove 启动")
    log.info(f"数据目录: {config.DATA_DIR}")

    # ---- M01: 数据库初始化 ----
    from data.db import Database, ClipboardMigrations, NotesMigrations
    clipboard_db = Database(config.clipboard_db_path)
    clipboard_db.migrate(ClipboardMigrations)
    notes_db = Database(config.notes_db_path)
    notes_db.migrate(NotesMigrations)
    log.info("数据库初始化完成")

    # ---- 主题 ----
    try:
        import qt_material
        qt_material.apply_stylesheet(app, theme=config.THEME)
        log.info(f"已应用主题: {config.THEME}")
    except ImportError:
        log.warning("qt-material 未安装，使用默认样式")

    # ---- M03: ClipCache ----
    from core.clipboard_monitor import ClipStore, ClipboardMonitor
    clip_store = ClipStore(clipboard_db)
    clip_monitor = ClipboardMonitor(clip_store)
    clip_monitor.start()
    log.info("剪贴板监听已启动")

    # ---- M04: NoteNest ----
    from core.note_manager import NoteStore
    note_store = NoteStore(notes_db)

    # ---- M05: TaskFlow ----
    from data.db import TaskMigrations
    tasks_db = Database(config.tasks_db_path)
    tasks_db.migrate(TaskMigrations)
    from core.task_manager import TaskStore
    from core.task_scheduler import TaskScheduler
    task_store = TaskStore(tasks_db)
    task_scheduler = TaskScheduler(task_store)
    log.info("TaskFlow 初始化完成")

    # ---- M02: 主窗口 ----
    from ui.main_window import MainWindow
    from ui.clip_page import create_page as create_clip_page
    from ui.note_page import create_page as create_note_page
    from ui.task_page import create_page as create_task_page
    from ui.settings_page import create_page as create_settings_page

    window = MainWindow(close_to_tray=config.CLOSE_TO_TRAY)
    clip_page = create_clip_page(clip_store, clip_monitor)
    note_page = create_note_page(note_store, config.NOTE_FONT_SIZE)
    task_page = create_task_page(task_store, task_scheduler)
    # 连接转笔记信号
    clip_page.convert_to_note.connect(note_page.add_note_from_clip)

    window.register_page("clip", clip_page)
    window.register_page("note", note_page)
    window.register_page("task", task_page)
    window.switch_to_page("clip")

    # ---- M09: 设置页面（后注册，需拿到其它模块引用） ----
    settings_page = create_settings_page(config)
    settings_page.close_to_tray_changed.connect(window.set_close_to_tray)
    window.register_page("settings", settings_page)

    # ---- M06: 全局搜索 ----
    from core.search_engine import SearchEngine
    from ui.search_window import SearchWindow
    search_engine = SearchEngine(clip_store, note_store, task_store)
    search_window = SearchWindow(search_engine)

    def on_search_result_jump(module_name, entry_data):
        """搜索结果双击 → 跳转到对应页面。"""
        if module_name == "clip":
            window.switch_to_page("clip")
        elif module_name == "note":
            window.switch_to_page("note")
        elif module_name == "task":
            window.switch_to_page("task")
        search_window.hide()
        window.show()
        window.raise_()
        window.activateWindow()

    search_window.jump_to.connect(on_search_result_jump)

    # ---- 粘贴选择弹窗 ----
    from ui.paste_popup import create_paste_popup
    paste_popup = create_paste_popup(clip_store)

    # ---- M07: 托盘 + 热键 ----
    from core.tray_manager import TrayManager
    tray_mgr = TrayManager()

    def show_search():
        """热键回调：显示搜索窗口。"""
        if search_window.isVisible():
            search_window.hide()
        else:
            # 居中定位
            screen = app.primaryScreen()
            if screen:
                center = screen.availableGeometry().center()
                search_window.move(
                    center.x() - search_window.width() // 2,
                    center.y() - search_window.height() // 2,
                )
            search_window.show_and_focus()

    def new_note_hotkey():
        """热键回调：快速新建笔记。"""
        window.show()
        window.raise_()
        window.activateWindow()
        window.switch_to_page("note")
        from ui.widgets.note_editor import NoteEditor
        dlg = NoteEditor(note_store, parent=window)
        dlg.saved.connect(lambda nid: note_page._refresh())
        dlg.exec()

    def show_paste_popup():
        """热键回调：显示粘贴选择弹窗。"""
        paste_popup.show_near_cursor()

    def exit_all_ghost():
        """热键回调：退出所有幽灵模式悬浮窗。"""
        note_page.exit_all_ghost()

    tray_mgr.setup_hotkeys(config, on_search=show_search, on_new_note=new_note_hotkey,
                           on_paste=show_paste_popup, on_exit_ghost=exit_all_ghost)
    tray_mgr.setup_tray(app, window, on_new_note=new_note_hotkey, on_quit=app.quit)

    # ---- 热键与设置的冲突处理 ----
    def on_page_changed(page_key: str):
        """切换到设置页时暂停全局热键，离开时恢复。"""
        if page_key == "settings":
            tray_mgr.unregister_all()
        else:
            tray_mgr.setup_hotkeys(config, on_search=show_search,
                                   on_new_note=new_note_hotkey, on_paste=show_paste_popup,
                                   on_exit_ghost=exit_all_ghost)

    window.page_changed.connect(on_page_changed)

    # ---- M08: 备份系统 ----
    from core.backup import BackupManager
    backup_mgr = BackupManager(config)
    backup_mgr.start_auto_backup()
    log.info("自动备份已启动")

    # ---- 剪贴板自动清理（超过 N 天） ----
    def _auto_delete_old_clips():
        days = config.CLIP_AUTO_DELETE_DAYS
        if days > 0:
            clip_store.delete_old_entries(days)
            clip_store.enforce_cap(config.CLIP_MAX_HISTORY)

    clip_cleanup_timer = QTimer()
    clip_cleanup_timer.timeout.connect(_auto_delete_old_clips)
    clip_cleanup_timer.start(3600000)  # 每小时检查一次

    # ---- 任务笔记调度 ----
    note_page.start_task_scheduler()
    # 延迟自动打开开机任务笔记（等待悬浮窗恢复完成）
    QTimer.singleShot(500, note_page.auto_open_task_notes)

    # 显示主窗口
    window.show()
    log.info("主窗口已显示")
    exit_code = app.exec()

    # ---- 清理 ----
    note_page.stop_task_scheduler()
    note_page.close_all_floats()
    task_scheduler.stop()
    backup_mgr.stop_auto_backup()
    clip_cleanup_timer.stop()
    clip_monitor.stop()
    tray_mgr.shutdown()
    clipboard_db.close()
    notes_db.close()
    tasks_db.close()
    log.info("trove 退出")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())