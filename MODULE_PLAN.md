# trove 模块化开发计划

> **目标读者：AI 开发工具**
> 本文档以结构化方式定义所有模块的接口、依赖、优先级，便于 AI 按序逐步实现。

---

## 一、模块总览

```
trove
│
├─ M00  项目骨架（入口 + 配置 + 目录初始化）
├─ M01  数据库层（SQLite 管理 + 迁移）
├─ M02  主窗口框架（侧边栏 + 页面路由）
│
├─ M03  ClipCache - 剪贴板历史
│   ├─ M03.1  数据模型与 CRUD
│   ├─ M03.2  后台监听线程
│   └─ M03.3  UI 页面
│
├─ M04  NoteNest - 微笔记
│   ├─ M04.1  数据模型与 CRUD（含 FTS5 + 标签）
│   ├─ M04.2  CardFlowWidget 卡片墙
│   └─ M04.3  UI 页面 + 编辑器
│
├─ M05  TaskFlow - 本地定时小助手
│   ├─ M05.1  数据模型与 CRUD（任务 + 日志）
│   ├─ M05.2  调度引擎（时间规则匹配 + 动作触发）
│   └─ M05.3  UI 页面（任务列表 + 创建/编辑 + 提醒弹窗）
│
├─ M06  全局搜索
├─ M07  系统托盘 + 全局热键
├─ M08  备份系统
├─ M09  设置页面
└─ M10  打包部署
```

---

## 二、依赖关系图

```
M00 项目骨架
 │
 ├──► M01 数据库层 ──► M03.1, M04.1, M05.1
 │
 └──► M02 主窗口框架
       │
       ├──► M03.3 ClipCache UI ──► M03.2 后台监听 ──► M03.1
       │
       ├──► M04.3 NoteNest UI ──► M04.2 卡片墙 ──► M04.1
       │
       ├──► M05.3 TaskFlow UI ──► M05.2 调度引擎 ──► M05.1
       │
       ├──► M06 全局搜索 ──► M03.1, M04.1, M05.1
       │
       ├──► M07 托盘+热键 ──► M03.2, M04.3, M05.2, M06
       │
       ├──► M08 备份系统 ──► M01
       │
       └──► M09 设置页面 ──► M00
```

**依赖规则：箭头方向 = "依赖于"，先实现被依赖的模块。**

---

## 三、模块详细规格

---

### M00 - 项目骨架

**文件：** `main.py`, `config.py`

**职责：**
- 初始化 `QApplication`
- 创建必需的目录结构（data/, logs/, backups/）
- 加载 `QSettings` 配置
- 作为程序入口，按需实例化各模块

**输入：** 无
**输出：**
- `config.py` 提供全局配置常量类 `AppConfig`

**config.py 接口定义：**
```python
class AppConfig:
    # 路径（运行时由 QSettings 或默认值填充）
    DATA_DIR: str          # %APPDATA%/trove/data
    BACKUP_DIR: str        # %APPDATA%/trove/backups
    LOG_DIR: str           # %APPDATA%/trove/logs

    # 剪贴板
    CLIP_MAX_HISTORY: int  # 默认 1000

    # 备份
    BACKUP_INTERVAL_MIN: int  # 默认 30
    BACKUP_MAX_VERSIONS: int  # 默认 5

    # 热键
    HOTKEY_SEARCH: str     # 默认 Ctrl+Alt+V
    HOTKEY_NEW_NOTE: str   # 默认 Ctrl+Alt+N
    HOTKEY_PASTE: str      # 默认 Ctrl+Shift+V

    # 笔记
    NOTE_FONT_SIZE: int    # 默认 14

    # 托盘
    CLOSE_TO_TRAY: bool    # 默认 True

    # 主题
    THEME: str             # 默认 light_blue.xml
```

**验证方式：** 运行 `python main.py`，无报错退出，目录结构已创建。

---

### M01 - 数据库层

**文件：** `data/db.py`

**职责：**
- 管理 SQLite 连接（WAL 模式）
- 提供统一的 `execute()` / `executemany()` 接口
- 数据库迁移（版本化建表）
- 线程安全的写入队列（生产者-消费者）

**依赖：** M00（需要 `AppConfig.DATA_DIR`）

**公开接口：**
```python
class Database:
    def __init__(self, db_path: str): ...
    def execute(self, sql: str, params=()) -> cursor: ...
    def fetchone(self, sql: str, params=()) -> tuple | None: ...
    def fetchall(self, sql: str, params=()) -> list[tuple]: ...
    def enqueue_write(self, sql: str, params=()): ...   # 异步写入
    def migrate(self, migrations: dict[int, str]): ...   # 版本迁移
    def close(self): ...
```

**需要调用的迁移脚本（内部版本号）：**
1. `clipboard.db` → 建 `history` 表 + 索引
2. `notes.db` → 建 `notes` 表 + `notes_fts` 虚拟表 + `tags` 表 + `note_tags` 表
3. `tasks.db` → 建 `tasks` 表 + `task_logs` 表 + 索引

**验证方式：** 实例化 `Database`，执行建表，用 `DB Browser for SQLite` 查看表结构无误。

---

### M02 - 主窗口框架

**文件：** `ui/main_window.py`

**职责：**
- 左侧 QListWidget 侧边栏（ClipCache / NoteNest / TaskFlow / 设置）
- 右侧 QStackedWidget 页面容器
- 注册页面映射：`{"clip": ClipPage, "note": NotePage, "task": TaskPage, "settings": SettingsPage}`
- 窗口关闭事件 → 隐藏到托盘（如果启用）

**依赖：** M00（需要 `QApplication` 已初始化）

**公开接口：**
```python
class MainWindow(QMainWindow):
    stack: QStackedWidget
    nav_list: QListWidget

    def register_page(self, key: str, widget: QWidget): ...
    def switch_to_page(self, key: str): ...
    def closeEvent(self, event): ...  # 最小化到托盘
```

**页面占位约定：** 被 M02 依赖的页面模块需要提供一个工厂函数：
```python
def create_page(...) -> QWidget:
    """返回该模块的主页面控件"""
```

**验证方式：** 运行后显示空窗口，侧边栏可点击切换占位页面（空白 QWidget）。

---

### M03 - ClipCache 剪贴板历史

#### M03.1 数据模型与 CRUD

**文件：** `core/clipboard_monitor.py`（前半部分 - 数据操作类）

**职责：**
- 封装 `history` 表的增删改查
- 插入时带 MD5 去重（内存缓存上一次 hash）
- 数量上限检查与清理（非星标旧记录删除）
- 星标切换

**依赖：** M01（需要 `Database` 实例操作 `clipboard.db`）

**公开接口：**
```python
class ClipStore:
    def __init__(self, db: Database): ...
    def add(self, content: str) -> bool: ...        # 去重后插入，返回是否真正插入
    def delete(self, clip_id: int): ...
    def toggle_star(self, clip_id: int) -> bool: ... # 返回新状态
    def search(self, keyword: str, starred_only: bool = False,
               limit: int = 50, offset: int = 0) -> list[dict]: ...
    def get_count(self) -> int: ...
    def get_recent(self, limit: int = 50, offset: int = 0) -> list[dict]: ...
    def enforce_cap(self, max_count: int): ...       # 超出上限时清理
```

**返回字典格式：**
```python
{"id": int, "content": str, "timestamp": int, "starred": bool}
```

**验证方式：** 单元测试 add/search/delete/toggle_star，确认去重和上限清理逻辑。

---

#### M03.2 后台监听线程

**文件：** `core/clipboard_monitor.py`（后半部分 - 监听类）

**职责：**
- 创建隐藏 QWindow，注册 `AddClipboardFormatListener`
- 在 `nativeEvent` 中捕获 `WM_CLIPBOARDUPDATE`
- 获取剪贴板文本，经隐私正则过滤后通过信号发射

**依赖：** M03.1（需要 `ClipStore`）

**公开接口：**
```python
from PySide6.QtCore import QObject, Signal

class ClipboardMonitor(QObject):
    new_content = Signal(str)   # 发射到 UI 更新 + 写入数据库

    def __init__(self, clip_store: ClipStore, parent=None): ...
    def start(self): ...        # 注册窗口钩子
    def stop(self): ...         # 注销钩子
    def set_privacy_filters(self, patterns: list[str]): ...  # 正则列表
```

**内部逻辑：**
1. `nativeEvent` 收到 `WM_CLIPBOARDUPDATE` → 通过信号通知
2. 主线程槽函数调用 `QApplication.clipboard().text()`
3. 遍历 `privacy_filters`，匹配则丢弃
4. 调用 `clip_store.add()` 写入
5. 发射 `new_content` 信号触发 UI 刷新

**验证方式：** 启动监听后复制文本，确认信号发射，数据库有新记录。

---

#### M03.3 UI 页面

**文件：** `ui/clip_page.py`, `ui/widgets/clip_item_delegate.py`

**职责：**
- 顶部搜索框 + 星标过滤 Toggle
- QListView + QStyledItemDelegate（单行省略 + 相对时间 + 星标图标）
- 双击复制到剪贴板
- 右键菜单：复制、星标切换、删除、转笔记
- 转笔记：将内容传给 NoteNest 模块创建新笔记
- 底部状态栏显示条数

**依赖：** M02（注册到主窗口）, M03.1（数据操作）, M03.2（接收信号）

**工厂函数：**
```python
# ui/clip_page.py
def create_page(clip_store: ClipStore, monitor: ClipboardMonitor) -> QWidget: ...
```

**转笔记回调：** 页面构造函数接受 `on_convert_to_note: Callable[[str], None]`，由上层组装时注入。

**验证方式：** 页面显示历史列表，搜索/过滤/右键菜单功能正常，复制后剪贴板内容更新。

---

### M04 - NoteNest 微笔记

#### M04.1 数据模型与 CRUD（含 FTS5 + 标签）

**文件：** `core/note_manager.py`

**职责：**
- 封装 `notes`、`notes_fts`、`tags`、`note_tags` 四表的 CRUD
- FTS5 触发器同步
- 标签增删 + 多对多关联（UI 层限制每笔记最多 1 个标签）
- 排序逻辑（sort_order / 时间）
- 颜色筛选

**依赖：** M01（需要 `Database` 实例操作 `notes.db`）

**公开接口：**
```python
class NoteStore:
    def __init__(self, db: Database): ...
    def create(self, title: str, content: str = "") -> int: ...
    def update(self, note_id: int, **fields): ...  # 支持 color/font_color/note_type/task_schedule/auto_startup
    def delete(self, note_id: int): ...           # 软删除（移入回收站）
    def hard_delete(self, note_id: int): ...       # 永久删除
    def delete_many(self, note_ids: list[int]): ...
    def restore(self, note_id: int): ...           # 恢复
    def empty_trash(self): ...                     # 清空回收站
    def get_trashed(self) -> list[dict]: ...       # 获取回收站列表
    def get(self, note_id: int) -> dict | None: ...
    def search(self, keyword: str, tag_ids: list[int] = None, ...): ...
    def get_all(self, tag_ids=None, sort_by="sort_order", color=None,
                note_type=None, include_deleted=False) -> list[dict]: ...
    def convert_type(self, note_id: int) -> str: ...  # 普通↔任务互转
    def reorder(self, note_ids: list[int]): ...

    # 标签
    def add_tag(self, name: str) -> int: ...
    def get_all_tags(self) -> list[dict]: ...
    def set_note_tags(self, note_id: int, tag_ids: list[int]): ...
    def get_note_tags(self, note_id: int) -> list[dict]: ...
    def get_all_unique_colors(self) -> list[str]: ...  # 所有使用过的颜色

    # 浮动
    def set_floating(self, note_id: int, floating: bool): ...
    def get_floating(self) -> list[dict]: ...
```

**返回字典格式（笔记）：**
```python
{"id": int, "title": str, "content": str, "color": str,
 "sort_order": int, "created": int, "modified": int, "is_floating": int,
 "tags": [{"id": int, "name": str}]}
```

**验证方式：** 单元测试 CRUD、搜索、标签筛选组合。

---

#### M04.2 卡片墙组件

**文件：** `ui/widgets/card_flow.py`, `ui/widgets/note_card.py`, `ui/widgets/note_float.py`, `ui/widgets/task_note_card.py`, `ui/widgets/task_note_float.py`

**职责：**
- CardFlowWidget：手动 positioning 自适应网格容器，支持拖拽排序
- NoteCard：普通笔记卡片，显示标题/摘要/颜色/标签/浮动开关
- NoteFloatWindow：无边框置顶悬浮窗，可拖拽、锁/解锁、图片自适应、字体颜色
- TaskNoteCard：任务笔记勾选框清单卡片，点击切换完成状态
- TaskNoteFloat：任务笔记交互式悬浮窗，勾选实时同步数据库

**依赖：** 无（纯 UI 组件）

**公开接口：**
```python
class CardFlowWidget(QWidget):
    order_changed = Signal(list)   # 拖拽后新的 [note_id, ...] 顺序

    def set_drag_enabled(self, enabled: bool): ...
    def clear(self): ...
    def add_card(self, widget: QWidget): ...
    def layout_cards(self): ...
    def cards(self) -> list: ...
    def card_ids(self) -> list[int]: ...

class NoteCard(QFrame):
    double_clicked = Signal(int)      # note_id → 打开编辑器
    float_toggled = Signal(int, bool) # note_id, is_floating
    delete_requested = Signal(int)    # note_id

    def __init__(self, note_data: dict, parent=None): ...
    def update_data(self, note_data: dict): ...
    def set_floating_state(self, floating: bool): ...
    def set_select_mode(self, enabled: bool): ...
    def is_checked(self) -> bool: ...

class NoteFloatWindow(QWidget):
    unfloated = Signal(int)       # 关闭悬浮
    edit_requested = Signal(int)  # 请求编辑

    def __init__(self, note_data: dict, font_size: int = 14, parent=None): ...
    def update_content(self, note_data: dict, font_size: int = None): ...
```

**验证方式：** 放入不同数量的卡片，调整窗口宽度，验证换行和拖拽重排。

---

#### M04.3 UI 页面 + 编辑器

**文件：** `ui/note_page.py`, `ui/widgets/note_editor.py`

**职责：**
- 顶部工具栏：新建按钮、搜索框、排序切换、批量操作
- 标签下拉筛选 + 颜色筛选按钮
- 嵌入 CardFlowWidget + 卡片控件
- NoteEditor：QDialog，编辑标题/内容/标签/颜色
- 批量操作：颜色设置、标签设置、删除
- 浮动窗口管理（创建/关闭/恢复/编辑同步）
- 接收来自 ClipCache 的"转笔记"回调

**依赖：** M02（页面注册）, M04.1（数据操作）, M04.2（卡片+布局）

**工厂函数：**
```python
# ui/note_page.py
def create_page(note_store: NoteStore, font_size: int = 14) -> QWidget: ...
```

**验证方式：** 创建/编辑/删除/导出笔记，标签/颜色筛选，拖拽排序均正常。

---

### M05 - TaskFlow 本地定时小助手

#### M05.1 数据模型与 CRUD（任务 + 日志）

**文件：** `core/task_manager.py`

**职责：**
- 封装 `tasks` 表和 `task_logs` 表的 CRUD
- 任务启用/禁用切换
- 执行日志记录与查询
- 按状态筛选（进行中 / 已过期 / 已停用）

**依赖：** M01（需要 `Database` 实例操作 `tasks.db`）

**公开接口：**
```python
class TaskStore:
    def __init__(self, db: Database): ...

    # 任务 CRUD
    def create(self, name: str, description: str = "",
               rule_type: str = "daily", rule_value: str = "09:00",
               action_type: str = "popup", action_value: str = "",
               start_date: int = None, end_date: int = None) -> int: ...
    def update(self, task_id: int, **fields): ...
    def delete(self, task_id: int): ...
    def get(self, task_id: int) -> dict | None: ...
    def get_all(self, status_filter: str = "all") -> list[dict]: ...
    def toggle_enabled(self, task_id: int) -> bool: ...  # 返回新状态
    def search(self, keyword: str) -> list[dict]: ...     # 搜索任务名和描述

    # 日志
    def log(self, task_id: int, status: str, message: str = ""): ...
    def get_logs(self, task_id: int, limit: int = 50) -> list[dict]: ...
    def clear_logs(self, task_id: int = None): ...  # task_id=None 清除所有
```

**返回字典格式（任务）：**
```python
{
    "id": int, "name": str, "description": str,
    "rule_type": str,      # once / daily / weekly / monthly / cron
    "rule_value": str,     # 具体规则值
    "start_date": int | None, "end_date": int | None,
    "action_type": str,    # popup / sound / open_file / open_folder / run_script
    "action_value": str,   # 文件路径 / 命令等
    "enabled": int, "created": int, "modified": int
}
```

**返回字典格式（日志）：**
```python
{"id": int, "task_id": int, "triggered_at": int, "status": str, "message": str}
```

**状态筛选：**
- `"all"` — 全部
- `"active"` — enabled=1 且（无 end_date 或 end_date > now）
- `"expired"` — end_date 已过
- `"disabled"` — enabled=0

**数据库迁移脚本：**
```python
TaskMigrations = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            description  TEXT DEFAULT '',
            rule_type    TEXT NOT NULL,
            rule_value   TEXT NOT NULL,
            start_date   INTEGER,
            end_date     INTEGER,
            action_type  TEXT NOT NULL,
            action_value TEXT DEFAULT '',
            enabled      INTEGER DEFAULT 1,
            created      INTEGER,
            modified     INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS task_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id      INTEGER NOT NULL,
            triggered_at INTEGER NOT NULL,
            status       TEXT NOT NULL,
            message      TEXT DEFAULT '',
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id)",
        "CREATE INDEX IF NOT EXISTS idx_task_logs_time ON task_logs(triggered_at)",
    ],
}
```

**验证方式：** 单元测试 CRUD、状态筛选、日志记录与查询。

---

#### M05.2 调度引擎（时间规则匹配 + 动作触发）

**文件：** `core/task_scheduler.py`

**职责：**
- 后台线程，每秒轮询一次
- 解析五种时间规则（once / daily / weekly / monthly / cron）判断是否应触发
- 触发时执行对应动作并写入日志
- 通过信号通知 UI 弹出提醒窗口
- 支持暂停/恢复（免打扰模式）

**依赖：** M05.1（TaskStore）, 内置 `schedule` 库或 `croniter`

**公开接口：**
```python
from PySide6.QtCore import QObject, Signal

class TaskScheduler(QObject):
    remind_triggered = Signal(dict)   # 任务数据 → UI 弹出提醒窗口
    action_executed = Signal(int, str) # task_id, status
    
    def __init__(self, task_store: TaskStore): ...
    def start(self): ...
    def stop(self): ...
    def pause(self): ...   # 暂停调度（免打扰）
    def resume(self): ...  # 恢复调度
    def is_paused(self) -> bool: ...

class RuleParser:
    """时间规则解析与匹配"""
    @staticmethod
    def should_trigger(task: dict) -> bool:
        """判断任务当前是否应触发"""
        ...
```

**时间规则格式：**

| 规则类型 | `rule_value` 格式 | 示例 |
|----------|-------------------|------|
| `once` | `"YYYY-MM-DD HH:MM"` | `"2026-06-10 09:00"` |
| `daily` | `"HH:MM"` | `"09:00"` |
| `weekly` | `"1,3,5@HH:MM"` | `"1,3,5@09:00"`（周一三五） |
| `monthly` | `"15@HH:MM"` | `"15@09:00"`（每月 15 号） |
| `cron` | 标准 Cron 表达式 | `"0 9 * * 1-5"`（工作日 9:00）|

**动作执行逻辑：**
```python
def execute_action(task: dict):
    if task["action_type"] == "popup":
        # 发射 remind_triggered 信号 → UI 弹窗
    elif task["action_type"] == "sound":
        # 播放音频文件或默认系统音
    elif task["action_type"] == "open_file":
        # os.startfile(task["action_value"])
    elif task["action_type"] == "open_folder":
        # os.startfile(task["action_value"])
    elif task["action_type"] == "run_script":
        # 弹确认框 → subprocess.run(...)
    task_store.log(task["id"], "success" 或 "failure", message)
```

**安全规则：**
- `run_script` 动作执行前必须通过信号请求 UI 确认
- 确认后以 `subprocess.run` 执行，超时设置 30 秒
- 执行结果记录到日志

**验证方式：** 创建一个 1 分钟后触发的 daily 任务，确认到时间后日志有记录，弹窗正常显示。

---

#### M05.3 UI 页面（任务列表 + 创建/编辑 + 提醒弹窗）

**文件：** `ui/task_page.py`, `ui/widgets/task_editor.py`, `ui/widgets/task_reminder_popup.py`

**职责：**
- 任务列表（QTableView）：显示状态图标、任务名、时间规则摘要、动作类型、操作按钮
- 顶部筛选下拉框（全部 / 进行中 / 已过期 / 已停用）
- [+ 新建任务] 按钮 → TaskEditor (QDialog)
- 双击任务 → TaskEditor 编辑
- TaskEditor：表单编辑任务名、描述、时间规则、动作类型。弹窗提醒动作为文本编辑+插入图片（非文件选择）
- 提醒弹窗：无边框置顶，显示任务名 + 说明 + [知道了] 按钮

**依赖：** M02（页面注册）, M05.1（TaskStore）, M05.2（TaskScheduler）

**工厂函数：**
```python
# ui/task_page.py
def create_page(task_store: TaskStore, scheduler: TaskScheduler) -> QWidget: ...
```

**TaskEditor 界面布局：**
```
┌─────────────────────────────────────┐
│  新建任务 / 编辑任务                  │
│                                     │
│  任务名：[________________]          │
│  描述：  [________________]          │
│                                     │
│  时间规则：[ daily ▼]                │
│  时间值： [ 09:00   ]               │
│  开始日期：[ 可选    ] 结束日期：[ 可选]│
│                                     │
│  动作类型：[ popup ▼]                │
│  动作参数：[ 可选文件路径/命令  ]      │
│                                     │
│            [取消]    [保存]          │
└─────────────────────────────────────┘
```

**提醒弹窗布局：**
```
┌─────────────────────────────────────┐
│  🔔  定时提醒                        │
│                                     │
│        任务名称（大字加粗）            │
│        任务说明（小字灰色）            │
│                                     │
│            [  知道了  ]              │
└─────────────────────────────────────┘
```

- 无边框、居中显示、始终置顶
- 点击"知道了"或按 ESC 关闭
- 可配置字体大小

**验证方式：** 完整流程：创建任务 → 列表显示 → 编辑 → 启用/禁用 → 到期弹窗提醒。

---

### M06 - 全局搜索

**文件：** `core/search_engine.py`, `ui/search_window.py`

**职责：**
- 聚合 ClipCache / NoteNest / TaskFlow 三个数据源的搜索结果
- 分组展示在浮动搜索窗口中

**依赖：** M03.1（ClipStore.search）, M04.1（NoteStore.search）, M05.1（TaskStore.search）, M07（若通过热键唤出）

**公开接口：**
```python
class SearchEngine(QObject):
    search_completed = Signal(list)  # 分组结果

    def __init__(self, clip_store: ClipStore, note_store: NoteStore,
                 task_store: TaskStore): ...
    def search(self, keyword: str): ...

class SearchWindow(QDialog):
    """浮动搜索窗口，始终置顶"""
    jump_to = Signal(str, dict)  # module_name, entry_data

    def __init__(self, engine: SearchEngine, parent=None): ...
    def show_and_focus(self): ...   # 显示并将焦点移到搜索框
```

**搜索结果格式：**
```python
[
    {"module": "clip", "results": [...ClipStore 返回的 dict...]},
    {"module": "note", "results": [...NoteStore 返回的 dict...]},
    {"module": "task", "results": [...TaskStore 返回的 dict...]},
]
```

**验证方式：** 三模块各有数据时，搜索关键词能返回分组结果，点击结果可跳转到对应页面。

---

### M07 - 系统托盘 + 全局热键

**文件：** `core/tray_manager.py`

**职责：**
- `QSystemTrayIcon`：图标 + 右键菜单（显示/隐藏/新建笔记/暂停提醒/退出）
- 关闭窗口 → 隐藏到托盘
- 全局热键注册（RegisterHotKey + nativeEvent WM_HOTKEY）
- `Ctrl+Alt+V` → 唤出 SearchWindow
- `Ctrl+Alt+N` → 快速新建笔记
- `Ctrl+Shift+V` → 粘贴历史选择弹窗

**依赖：** M02（MainWindow）, M06（SearchWindow）, M04.3（新建笔记）, M05.2（暂停/恢复）

**公开接口：**
```python
class TrayManager:
    def __init__(self): ...
    def setup_hotkeys(self, config, on_search, on_new_note, on_paste): ...
    def setup_tray(self, app, window, on_new_note, on_quit,
                   on_pause=None): ...  # on_pause: 免打扰开关回调
    def shutdown(self): ...
```

**验证方式：** 托盘图标显示，右键菜单有效，全局热键在任意窗口可触发。

---

### M08 - 备份系统

**文件：** `core/backup.py`

**职责：**
- 定时备份（QTimer，每 30 分钟）→ 复制 `clipboard.db`、`notes.db`、`tasks.db` 到备份目录
- 保留最近 5 个版本（按时间戳命名子目录）
- 手动备份：打包为 ZIP（zipfile）
- 手动恢复：选择 ZIP 或文件夹，校验后覆盖

**依赖：** M00（`AppConfig.BACKUP_DIR`）, M01（数据库路径）

**公开接口：**
```python
class BackupManager(QObject):
    backup_completed = Signal(bool, str)   # 成功/失败, 消息

    def __init__(self, config: AppConfig): ...
    def start_auto_backup(self): ...       # 启动定时器
    def stop_auto_backup(self): ...
    def manual_backup(self, dest_zip: str): ...
    def restore(self, source: str) -> bool: ...
```

**验证方式：** 定时备份生成目录，手动备份生成 ZIP，恢复后数据一致。

---

### M09 - 设置页面

**文件：** `ui/settings_page.py`

**职责：**
- 配置所有用户可调参数：
  - 最大剪贴板条数
  - 自动删除超期剪贴内容
  - 备份间隔 / 保留版本数
  - 热键组合（编辑时自动暂停全局热键防冲突）
  - 主题切换（中文名、实时生效、禁用滚轮）
  - 隐私过滤正则列表（增删）
  - 是否关闭到托盘
  - 开机自启动

**依赖：** M00（QSettings 读写）, M02（页面注册）

**工厂函数：**
```python
# ui/settings_page.py
def create_page(app_config: AppConfig, on_privacy_filters_changed) -> QWidget: ...
```

**验证方式：** 修改设置后重启应用，设置生效。

---

### M10 - 打包部署

**文件：** `build.spec`（PyInstaller spec）

**职责：**
- PyInstaller 打包配置：`--windowed --icon=icon.ico --add-data "theme;theme"`
- 包含 qt-material 主题文件
- 生成便携版 exe

**依赖：** 全部模块

**验证方式：** 生成的 exe 在全新 Windows 系统上可运行。

---

## 四、开发执行顺序（给 AI 的指令序列）

```
Phase 1: 打地基（基础设施，无 UI 交互）
  [M00] 项目骨架 → 创建 main.py + config.py + 目录
  [M01] 数据库层 → data/db.py（WAL + 迁移 + 写入队列）

Phase 2: 主窗口（空壳 UI）
  [M02] 主窗口框架 → ui/main_window.py（侧边栏 + QStackedWidget）

Phase 3: 核心模块（按依赖链串行，模块间可并行）
  3a. ClipCache 链：
    [M03.1] → [M03.2] → [M03.3]
  3b. NoteNest 链：
    [M04.1] → [M04.2] → [M04.3]
  3c. TaskFlow 链：
    [M05.1] → [M05.2] → [M05.3]

Phase 4: 全局集成
  [M09] 设置页面（先做，以便热键/备份可配置）
  [M06] 全局搜索
  [M07] 系统托盘 + 全局热键
  [M08] 备份系统

Phase 5: 收尾
  [M10] 打包测试
```

---

## 五、模块间数据流契约

### 5.1 ClipCache 数据流

```
剪贴板系统事件
  → ClipboardMonitor (nativeEvent)
  → 信号 new_content(str)
  → ClipStore.add() → clipboard.db
  → ClipPage.update_list()
```

### 5.2 转笔记数据流

```
ClipPage 右键 "转笔记"
  → 触发 on_convert_to_note 回调
  → NoteStore.create(title="", content=clip_content)
  → NotePage 刷新
```

### 5.3 TaskFlow 调度数据流

```
TaskScheduler 后台线程（每秒轮询）
  → RuleParser.should_trigger(task)
  → 匹配 → execute_action(task)
    ├─ popup: 信号 → TaskPage.show_reminder_popup()
    ├─ sound: 播放音频
    ├─ open_file/open_folder: os.startfile()
    └─ run_script: 信号 → UI 确认 → subprocess.run()
  → TaskStore.log(task_id, status, message)
  → 写入 task_logs 表
```

### 5.4 全局搜索数据流

```
用户按下 Ctrl+Alt+V 或点击搜索
  → SearchWindow 显示
  → 用户输入关键词
  → SearchEngine.search(keyword)
    ├→ ClipStore.search(keyword)
    ├→ NoteStore.search(keyword)
    └→ TaskStore.search(keyword)
  → SearchWindow 渲染分组结果
  → 点击结果 → MainWindow.switch_to_page(module) → 定位具体条目
```

### 5.5 备份数据流

```
QTimer 触发
  → BackupManager.backup()
  → 复制 clipboard.db, notes.db, tasks.db
  → %APPDATA%/trove/backups/backup_<timestamp>/
  → 清理超过 BACKUP_MAX_VERSIONS 的旧备份
```

---

## 六、验证检查清单

每完成一个模块后，执行以下验证：

| 模块 | 验证项 |
|------|--------|
| M00 | `python main.py` 无报错退出，目录已创建 |
| M01 | 建表成功，WAL 模式启用 |
| M02 | 窗口显示，侧边栏可切换占位页 |
| M03 | 复制文本后列表更新，搜索/星标/删除可用 |
| M04 | 创建/编辑/删除笔记，标签/颜色筛选，拖拽排序 |
| M05 | 创建任务→调度触发→弹窗/动作执行→日志记录 |
| M06 | 搜索返回三模块分组结果，点击跳转 |
| M07 | 托盘图标+菜单，全局热键在任意窗口生效 |
| M08 | 定时备份生成目录，手动打包 ZIP |
| M09 | 修改设置重启后生效 |
| M10 | 打包 exe 在干净系统可运行 |
