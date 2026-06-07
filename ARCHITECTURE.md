# trove 架构文档

## 一、项目概述

trove 是一款面向 Windows 平台的离线效率工具，集成三大核心模块：剪贴板历史管理（ClipCache）、微笔记（NoteNest）、本地定时小助手（TaskFlow）。技术栈为 Python + PySide6。

---

## 二、项目结构

```
trove/
├── main.py                  # 入口，初始化 QApplication，组装所有模块
├── config.py                # 全局配置（含笔记预设颜色）
├── core/
│   ├── clipboard_monitor.py # ClipStore + ClipboardMonitor（剪贴板 CRUD + Win32 钩子）
│   ├── note_manager.py      # NoteStore（笔记/任务笔记/标签 CRUD + FTS5 + 回收站）
│   ├── task_manager.py      # TaskStore（定时任务 + 日志 CRUD）
│   ├── task_scheduler.py    # TaskScheduler + RuleParser（调度引擎）
│   ├── search_engine.py     # SearchEngine（三模块聚合搜索，子线程）
│   ├── backup.py            # BackupManager（自动/手动备份）
│   └── tray_manager.py      # TrayManager（系统托盘 + 全局热键）
├── ui/
│   ├── main_window.py       # 主窗口（侧边栏 + QStackedWidget + 页面切换信号）
│   ├── clip_page.py         # 剪贴板历史页面
│   ├── note_page.py         # 笔记页面（普通/任务/回收站三标签页）
│   ├── task_page.py         # 定时任务页面
│   ├── settings_page.py     # 设置页（主题中文名、防滚轮、实时切换）
│   ├── search_window.py     # 浮动搜索窗口（可拖拽、三模块搜索）
│   ├── paste_popup.py       # 粘贴选择弹窗（可拖拽）
│   └── widgets/
│       ├── note_card.py         # 普通笔记卡片
│       ├── note_editor.py       # 笔记编辑器（图文/任务/配色/定时）
│       ├── note_float.py        # 普通笔记悬浮窗（锁/解锁、图片自适应）
│       ├── task_note_card.py    # 任务笔记卡片（勾选框清单）
│       ├── task_note_float.py   # 任务笔记交互式悬浮窗
│       ├── task_editor.py       # 任务编辑器（弹窗图文提醒）
│       ├── task_reminder_popup.py # 定时提醒弹窗（可拖拽缩放、图文适配）
│       ├── card_flow.py         # 自适应网格布局
│       ├── flow_layout.py       # 流式布局
│       └── clip_item_delegate.py # 剪贴板自定义绘制
├── data/
│   └── db.py                    # SQLite 管理（WAL、迁移、写入队列）
└── assets/                      # 图标资源（锁/解锁等）
```

---

## 三、技术栈与关键依赖

| 层次 | 技术选择 | 说明 |
|------|----------|------|
| GUI | PySide6 + qt-material | Material Design 主题，离线使用 |
| 数据库 | sqlite3（标准库） | 剪贴板、笔记与定时任务模块 |
| 剪贴板监听 | win32clipboard + ctypes | Windows 消息钩子，WM_CLIPBOARDUPDATE |
| 全局热键 | keyboard / pynput | 系统级快捷键注册 |
| 定时调度 | schedule / APScheduler | 轻量级 cron 解析与任务触发 |
| 打包 | PyInstaller | 生成便携版 exe |

---

## 四、全局架构设计

### 4.1 进程模型

```
┌─────────────────────────────────────────────┐
│                    主进程                     │
│  ┌──────────┐  ┌──────────────────────────┐ │
│  │  UI 线程  │  │      后台工作线程          │ │
│  │          │  │  ┌────────────────────┐  │ │
│  │ QWidget  │◄─┤──│ clipboard_monitor  │  │ │
│  │ 事件循环  │  │  └────────────────────┘  │ │
│  │          │  │  ┌────────────────────┐  │ │
│  │ 信号/槽  │  │  │  db writer queue   │  │ │
│  │          │  │  └────────────────────┘  │ │
│  │          │  │  ┌────────────────────┐  │ │
│  │          │  │  │  backup timer      │  │ │
│  │          │  │  └────────────────────┘  │ │
│  │          │  │  ┌────────────────────┐  │ │
│  │          │  │  │  task scheduler    │  │ │
│  └──────────┘  │  └────────────────────┘  │ │
│                └──────────────────────────┘ │
└─────────────────────────────────────────────┘
```

- **UI 线程**：处理所有界面渲染和用户交互。
- **后台线程**：剪贴板监听、数据库写入队列、定时备份、定时任务调度，通过 Qt 信号与 UI 线程通信。

### 4.2 模块隔离

三个功能模块各自独立管理数据模型，暴露统一的数据访问接口供搜索模块调用：

```
┌─────────────────────────────────────────────┐
│              Search Engine                  │
│         (统一搜索，聚合两模块数据)            │
├──────────────┬──────────────┬───────────────┤
│  ClipCache   │  NoteNest    │   TaskFlow    │
│  (剪贴板)     │  (微笔记)     │  (定时助手)    │
├──────────────┼──────────────┼───────────────┤
│ clipboard.db │  notes.db    │  tasks.db     │
└──────────────┴──────────────┴───────────────┘
```

### 4.3 数据存储

| 数据文件 | 格式 | 用途 |
|----------|------|------|
| `clipboard.db` | SQLite | 剪贴板历史记录 |
| `notes.db` | SQLite | 笔记与标签数据 |
| `tasks.db` | SQLite | 定时任务与执行日志 |
| `QSettings` (INI) | %APPDATA%/trove/ | 用户偏好配置 |

---

## 五、ClipCache 模块 - 剪贴板历史

### 5.1 架构

```
┌──────────────────────────────────────────────┐
│              ClipCache 页面                    │
│  ┌──────────────────────────────────────────┐│
│  │  搜索框 + 星标过滤按钮                     ││
│  ├──────────────────────────────────────────┤│
│  │  QListView + QStyledItemDelegate         ││
│  │  (虚拟列表，倒序显示)                      ││
│  ├──────────────────────────────────────────┤│
│  │  状态栏（条目数量）                         ││
│  └──────────────────────────────────────────┘│
│           ▲ 右键菜单：复制/星标/删除/转笔记      │
└──────────────────────────────────────────────┘
                    ▲
                    │ 信号/槽
┌───────────────────┴──────────────────────────┐
│         ClipboardMonitor (后台线程)            │
│  ┌────────────────────────────────────────┐  │
│  │  AddClipboardFormatListener(hwnd)      │  │
│  │  ↓ WM_CLIPBOARDUPDATE                  │  │
│  │  → nativeEvent 捕获                     │  │
│  │  → 获取文本 → MD5 去重 → 信号发射         │  │
│  └────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────┐  │
│  │  隐私过滤：正则匹配 → 匹配则丢弃           │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### 5.2 数据库表结构

```sql
CREATE TABLE history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    content   TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    starred   INTEGER DEFAULT 0
);
CREATE INDEX idx_history_timestamp ON history(timestamp);
```

- WAL 模式提升并发写入性能。
- 插入操作在后台线程执行。

### 5.3 数量上限策略

达到最大条数（默认 1000）时，删除最旧的非星标记录，事务中执行：

```sql
DELETE FROM history
WHERE id NOT IN (
    SELECT id FROM history
    WHERE starred = 1
    ORDER BY timestamp DESC LIMIT <上限>
)
AND starred = 0
ORDER BY timestamp ASC LIMIT <超出数>;
```

---

## 六、NoteNest 模块 - 微笔记

### 6.1 架构

```
┌──────────────────────────────────────────────┐
│              NoteNest 页面                     │
│  ┌──────────────────────────────────────────┐│
│  │  新建按钮 + 搜索框 + 排序 + 批量操作        ││
│  ├──────────────────────────────────────────┤│
│  │  标签下拉筛选 + 颜色筛选                    ││
│  ├──────────────────────────────────────────┤│
│  │  CardFlowWidget 卡片墙                    ││
│  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐            ││
│  │  │卡片│ │卡片│ │卡片│ │卡片│  ...        ││
│  │  └────┘ └────┘ └────┘ └────┘            ││
│  │  （支持拖拽排序 / 批量操作）                 ││
│  └──────────────────────────────────────────┘│
│           ▲ 双击 → NoteEditor (QDialog)       │
└──────────────────────────────────────────────┘
```

### 6.2 数据库表结构

```sql
-- 笔记主表
CREATE TABLE notes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT,
    content       TEXT DEFAULT '',
    color         TEXT DEFAULT '#FFFFFF',
    font_color    TEXT DEFAULT '#000000',
    sort_order    INTEGER DEFAULT 0,
    created       INTEGER,
    modified      INTEGER,
    is_floating   INTEGER DEFAULT 0,
    is_deleted    INTEGER DEFAULT 0,
    note_type     TEXT DEFAULT 'normal',
    task_schedule TEXT DEFAULT '',
    auto_startup  INTEGER DEFAULT 0
);

-- 全文搜索
CREATE VIRTUAL TABLE notes_fts
USING fts5(title, content, content=notes, content_rowid=id);

-- 标签系统（多对多，UI 层限制每笔记最多 1 个标签）
CREATE TABLE tags (
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE
);
CREATE TABLE note_tags (
    note_id INTEGER,
    tag_id  INTEGER,
    PRIMARY KEY (note_id, tag_id)
);
```

### 6.3 关键实现

- **NotePage 三标签页**：普通笔记 / 任务笔记 / 回收站，各自独立的卡片视图。
- **普通笔记**：NoteCard + NoteFloatWindow，支持图文混排、8 色预设+自定义配色、悬浮锁/解锁。
- **任务笔记**：TaskNoteCard（勾选框清单）+ TaskNoteFloat（交互式悬浮窗），支持定时弹出和开机自启。
- **回收站**：软删除机制，NoteCard 选择模式查看，可恢复或永久删除。
- **NoteEditor**：统一编辑器，支持普通/任务笔记切换、图片插入、配色自定义、定时规则设置。
- **CardFlowWidget**：手动 positioning 自适应网格容器，支持拖拽排序。
- **标签系统**：每个笔记最多 1 个标签（最多 5 字），下拉框筛选。

---

## 七、TaskFlow 模块 - 本地定时小助手

### 7.1 一句话描述

一个完全离线的轻量级提醒与自动化工具，能在指定时间弹出通知、打开文件或执行自定义脚本，成为桌面的可靠小秘书。

### 7.2 架构

```
┌──────────────────────────────────────────────┐
│              TaskFlow 页面                     │
│  ┌──────────────────────────────────────────┐│
│  │  [+ 新建任务]  [筛选: 全部/进行中/已过期]    ││
│  ├──────────────────────────────────────────┤│
│  │  QTableView 任务列表                      ││
│  │  ┌──────┬────────┬────────┬──────┬─────┐││
│  │  │ 状态  │ 任务名  │ 时间规则│ 动作 │ 操作│││
│  │  ├──────┼────────┼────────┼──────┼─────┤││
│  │  │ ●    │ 喝水提醒 │ 每1小时 │ 弹窗 │ ✕  │││
│  │  │ ○    │ 日报    │ 每天18:00│ 脚本│ ✕  │││
│  │  └──────┴────────┴────────┴──────┴─────┘││
│  └──────────────────────────────────────────┘│
│           ▲ 双击 → TaskEditor (QDialog)       │
│  ┌──────────────────────────────────────────┐│
│  │  执行日志面板（可选展开）                    ││
│  └──────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
                    ▲
                    │ 信号/槽
┌───────────────────┴──────────────────────────┐
│         TaskScheduler (后台线程)               │
│  ┌────────────────────────────────────────┐  │
│  │  schedule 库轮询（每秒检查一次）           │  │
│  │  → 匹配时间规则                          │  │
│  │  → 触发动作：弹窗 / 声音 / 打开 / 执行     │  │
│  │  → 写入执行日志                          │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### 7.3 数据库表结构

```sql
-- 任务主表
CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    rule_type   TEXT NOT NULL,     -- once/daily/weekly/monthly/cron
    rule_value  TEXT NOT NULL,     -- 具体规则值
    start_date  INTEGER,          -- 开始日期时间戳（可选）
    end_date    INTEGER,          -- 结束日期时间戳（可选）
    action_type TEXT NOT NULL,    -- popup/sound/open_file/open_folder/run_script
    action_value TEXT DEFAULT '', -- 动作参数（文件路径/命令等）
    enabled     INTEGER DEFAULT 1,
    created     INTEGER,
    modified    INTEGER
);

-- 执行日志表
CREATE TABLE task_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL,
    triggered_at INTEGER NOT NULL,  -- 触发时间戳
    status      TEXT NOT NULL,      -- success/failure/skipped
    message     TEXT DEFAULT '',    -- 执行结果或错误信息
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
CREATE INDEX idx_task_logs_task_id ON task_logs(task_id);
CREATE INDEX idx_task_logs_triggered ON task_logs(triggered_at);
```

### 7.4 时间规则设计

| 规则类型 | `rule_value` 格式 | 示例 |
|----------|-------------------|------|
| `once` | `"YYYY-MM-DD HH:MM"` | `"2026-06-10 09:00"` |
| `daily` | `"HH:MM"` | `"09:00"` (每天 9:00) |
| `weekly` | `"1,3,5@HH:MM"` | `"1,3,5@09:00"` (周一三五 9:00) |
| `monthly` | `"15@HH:MM"` | `"15@09:00"` (每月 15 号 9:00) |
| `cron` | 标准 Cron 表达式 | `"0 9 * * 1-5"` (工作日 9:00) |

- 所有规则的分钟级精度由 scheduler 轮询保证。
- Cron 表达式支持秒级可选（`"0 */30 9-18 * * *"`）。

### 7.5 动作类型

| 动作 | `action_type` | `action_value` | 说明 |
|------|---------------|----------------|------|
| 弹窗提醒 | `popup` | HTML（文字+图片） | 图文混排提醒弹窗，可拖拽缩放，图片自适应 |
| 声音提示 | `sound` | 音频文件路径（空=系统音） | 播放指定音频或内置提示音 |
| 打开文件 | `open_file` | 文件路径 | 用系统默认程序打开 |
| 打开文件夹 | `open_folder` | 文件夹路径 | 用资源管理器打开 |
| 运行脚本 | `run_script` | `.bat/.sh/.py` 路径 | 执行前弹确认框 |

### 7.6 提醒弹窗设计

```
┌─────────────────────────────────┐
│  🔔  定时提醒                    │  ← 标题栏（可拖拽）
├─────────────────────────────────┤
│                                 │
│        任务名称（大字）            │
│        任务说明（小字灰）          │
│                                 │
│     [可选：内嵌图片 / 音效]        │
│                                 │
│            [知道了]              │  ← 关闭按钮
└─────────────────────────────────┘
```

- 无边框、居中显示、始终置顶。
- 点击"知道了"或按 ESC 关闭。
- 支持自定义背景色、字体大小。

### 7.7 任务管理

- **启用/禁用**：列表内勾选框，禁用后 scheduler 跳过该任务。
- **状态筛选**：全部 / 进行中（enabled=1 且未过期）/ 已过期（end_date 已过）/ 已停用（enabled=0）。
- **日志回溯**：每任务可展开查看历史触发记录，含时间、状态、消息。

### 7.8 安全与隐私

- **完全离线**：代码不含任何遥测或网络请求。
- **本地存储**：任务和日志仅存于 `tasks.db`。
- **脚本确认**：`run_script` 类型动作执行前必须弹框确认，防止误操作。
- **加密存储（可选）**：后续可通过主密码对 `tasks.db` 加密。

---

## 八、统一搜索

### 8.1 架构

```
┌──────────────────────────────────────────────┐
│             SearchEngine                      │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │  数据源                               │    │
│  │  ┌────────────┐ ┌──────────┐ ┌─────┐│    │
│  │  │ ClipCache  │ │ NoteNest │ │TaskFlow│  │
│  │  │ SQLITE LIKE│ │  LIKE    │ │ LIKE  │  │
│  │  └────────────┘ └──────────┘ └──────┘│    │
│  └──────────────────────────────────────┘    │
│                    ▼                          │
│  ┌──────────────────────────────────────┐    │
│  │  QTreeView / QListWidget 分组展示     │    │
│  │  (模块图标 + 摘要 + 点击跳转)          │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

- 可通过 `Ctrl+Alt+V` 热键唤出浮动搜索窗口。
- 搜索范围：剪贴板历史（content）、笔记（title + content）、定时任务（name + description）。

---

## 九、全局功能

### 9.1 深色模式

通过 qt-material 的 `apply_stylesheet` 动态切换 `light_blue.xml` / `dark_teal.xml`。

### 9.2 备份系统

```
┌─────────────────────────┐
│   定时备份（每30分钟）      │
│   clipboard.db           │
│   notes.db      ──→  %APPDATA%/trove/backups/
│   tasks.db               │  保留最近 5 个版本
└─────────────────────────┘
┌─────────────────────────┐
│   手动备份               │
│   打包为 ZIP ← zipfile    │
└─────────────────────────┘
```

### 9.3 系统托盘

```
┌───────────────────────────┐
│  QSystemTrayIcon          │
│  右键菜单：                │
│    - 显示主窗口            │
│    - 新建笔记              │
│    - 暂停所有提醒          │
│    - 退出                 │
│  点击：显示/隐藏主窗口      │
│  关闭窗口：隐藏到托盘       │
```

### 9.4 全局热键

| 快捷键 | 功能 | 实现 |
|--------|------|------|
| `Ctrl+Alt+V` | 唤出搜索窗口 | RegisterHotKey + WM_HOTKEY |
| `Ctrl+Alt+N` | 新建笔记 | RegisterHotKey + WM_HOTKEY |
| `Ctrl+Shift+V` | 粘贴历史选择 | RegisterHotKey + WM_HOTKEY |

- 通过 `ctypes.windll.user32.RegisterHotKey` 注册。
- 在 `nativeEvent` 中监听 `WM_HOTKEY`。
- 快捷键可配置，避免冲突。

### 9.5 免打扰模式

- 托盘菜单中的「暂停所有提醒」选项。
- 开启后 TaskFlow 调度器停止触发，提醒弹窗不再弹出。
- 关闭后自动恢复所有进行中任务的调度。

---

## 十、线程安全设计

```
剪贴板监听线程                    UI 主线程
     │                              │
     ├── 获取文本 ──► 信号 ──► 槽：更新 UI
     │                              │
     │                         槽：写入队列
     │                              │
     │                              ▼
     │                    数据库写入线程
     │                    (生产者-消费者队列)
     │                    SQLite 串行写入
     │
定时任务调度线程
     │
     ├── 每秒轮询 ──► 信号 ──► 槽：触发提醒弹窗
     │
     ├── 写日志 ──► 队列 ──► 数据库写入线程
```

- 数据库写入统一由后台线程队列串行处理，避免多线程 SQLite 并发问题。
- 异常时记录日志（`%APPDATA%/trove/logs/`），UI 层通过 `QMessageBox` 提示。

---

## 十一、开发优先级

```
Phase 1: 基础框架
├── main_window.py（侧边栏 + StackedWidget）
├── db.py（数据库初始化）
├── config.py（QSettings 配置系统）
└── main.py（QApplication 入口）

Phase 2: 核心模块（可并行）
├── ClipCache（剪贴板监听 + 历史列表）
├── NoteNest（卡片墙 + 标签系统 + 拖拽排序）
└── TaskFlow（任务 CRUD + scheduler 调度 + 提醒弹窗）

Phase 3: 全局集成
├── SearchEngine（统一搜索）
├── 全局热键 + 系统托盘
├── 自动备份 + 手动导入导出
└── 免打扰模式
```

---

## 十二、部署与打包

- **打包命令**：
  ```
  pyinstaller --windowed --icon=icon.ico --add-data "theme;theme" main.py
  ```
- **目标平台**：Windows 10/11，64 位，Python 3.10+ 64bit。
- **安装程序**（可选）：Inno Setup 生成开始菜单快捷方式和卸载入口。
- **配置文件**：`%APPDATA%/trove/settings.ini`。
- **日志文件**：`%APPDATA%/trove/logs/`。
