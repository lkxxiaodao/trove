<div align="center">

# 🗄️ InfoVault

**Windows 离线效率工具 — 剪贴板历史 · 微笔记 · 定时任务，三位一体**

</div>

---

## 📖 简介

InfoVault 是一款基于 **Python + PySide6 (Qt6)** 开发的 Windows 桌面效率工具，完全离线运行，数据全部存储在本地 SQLite 数据库中。它集成了**剪贴板历史管理 (ClipCache)**、**微笔记卡片 (NoteNest)** 和**本地定时调度 (TaskFlow)** 三大模块，帮你高效管理日常工作流。

无论你是每天在海量文本碎片中切换，还是习惯随手记录灵感，抑或需要定时提醒与自动化执行任务，InfoVault 都能一站式满足你。

---

## ✨ 功能特性

### 📋 ClipCache — 剪贴板历史

- **自动记录**：通过 Windows 原生钩子监听剪贴板变化，自动保存文本、文件路径和图片
- **MD5 智能去重**：重复内容不重复插入，而是自动提升到列表顶部
- **多种显示**：文本内容、文件列表、缩略图三种视图，一目了然
- **容量上限**：默认 1000 条，超出时自动清理最旧非星标记录（可自定义 100~50000）
- **隐私过滤**：支持正则表达式过滤列表，匹配的敏感内容自动丢弃，不留痕迹

### 🫷 NoteNest — 微笔记卡片

- **卡片式笔记**：220×150 精美卡片，支持标题、正文、颜色标签和标签标记
- **标签与颜色**：8 种预设主题色，单选标签（最多 5 字），支持按颜色 / 标签快速筛选
- **拖拽排序**：自定义排序模式下可手动拖拽卡片重新排列
- **悬浮笔记**：可将任意笔记「悬浮」到桌面，无边框置顶显示，自由移动和调整大小
- **批量操作**：批量选择模式，一键删除 / 导出多张卡片
- **全文搜索**：基于 SQLite FTS5 的实时全文检索

### ⏰ TaskFlow — 本地定时调度

- **5 种时间规则**：一次性、每天、每周（可指定星期几）、每月（指定日期 / 月末）、间隔 N 天
- **多动作支持**：弹窗提醒、打开应用、打开文件 / 文件夹、运行脚本（需确认）
- **声音提醒**：可选系统提示音或自定义 wav / mp3 等音频文件
- **执行日志**：每任务最近 30 条执行记录，轻松回溯
- **防重复触发**：同一分钟内永不重复执行

### 🔍 全局搜索

- **跨模块聚合**：同时搜索剪贴板历史与微笔记内容
- **全局热键**：`Ctrl + Alt + V` 在任意窗口唤出浮动搜索弹窗
- **200ms 防抖**：输入自动节流，子线程搜索不卡 UI
- **按模块分组**：结果以树形分组展示，双击快速跳转

### ⚡ 快速粘贴

- **全局热键**：`Ctrl + Shift + V` 唤出粘贴历史选择弹窗
- **智能定位**：弹窗自动出现在当前光标附近
- **一键回填**：选中历史条目后自动模拟 Ctrl+V 粘贴到前台应用

### 🎨 界面主题

- 8 种 Material Design 主题（亮色 / 暗色）
- 笔记字体大小可调（10~36pt）
- 随你喜好自由切换

### 🖥️ 系统集成

- **全局热键**：`Ctrl+Alt+V` 搜索、`Ctrl+Alt+N` 新建笔记、`Ctrl+Shift+V` 快速粘贴（均可自定义）
- **系统托盘**：关闭窗口默认隐藏到托盘，后台常驻运行
- **托盘菜单**：右键托盘图标可快速显示窗口、新建笔记或退出

### 🔒 备份与恢复

- **自动备份**：定时复制 3 个数据库文件到备份目录（间隔可配）
- **版本保留**：保留最近 N 个版本，自动清理旧备份
- **手动导出**：一键打包为 ZIP 文件
- **一键恢复**：从 ZIP 或文件夹恢复数据（恢复前自动先备份当前状态）

---

## 🚀 快速开始

### 从源码运行

```bash
# 克隆仓库
git clone https://github.com/your-username/InfoVault.git

# 进入源码目录
cd InfoVault

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```
---

## 🏗️ 项目架构

```
InfoVault/
├── main.py                   # 应用入口：初始化应用、组装所有模块
├── config.py                 # 全局配置（单例 AppConfig，JSON 后端持久化）
├── requirements.txt          # 依赖清单
├── icon.ico                  # 应用图标
│
├── core/                     # 核心业务逻辑层
│   ├── clipboard_monitor.py     # ClipStore (CRUD) + ClipboardMonitor (Win32 钩子)
│   ├── note_manager.py          # NoteStore (笔记 + FTS5 + 标签 CRUD)
│   ├── task_manager.py          # TaskStore (任务 + 日志 CRUD)
│   ├── task_scheduler.py        # TaskScheduler + RuleParser (调度引擎)
│   ├── search_engine.py         # SearchEngine (跨模块聚合搜索，子线程)
│   ├── backup.py                # BackupManager (自动 / 手动备份，ZIP 打包)
│   └── tray_manager.py          # TrayManager (系统托盘 + 全局热键)
│
├── ui/                       # 视图层 (PySide6)
│   ├── main_window.py           # 主窗口（侧边栏 + QStackedWidget 多页面）
│   ├── clip_page.py             # ClipPage — 剪贴板历史页面
│   ├── note_page.py             # NotePage — 笔记卡片墙管理页面
│   ├── task_page.py             # TaskPage — 定时任务列表页面
│   ├── settings_page.py         # SettingsPage — 设置页面
│   ├── search_window.py         # SearchWindow — 浮动搜索窗口
│   ├── paste_popup.py           # PastePopup — 粘贴选择弹窗
│   └── widgets/
│       ├── card_flow.py         # CardFlowWidget — 手动定位网格 + 拖拽排序
│       ├── flow_layout.py       # FlowLayout — 自适应换行布局
│       ├── note_card.py         # NoteCard — 笔记卡片控件
│       ├── note_editor.py       # NoteEditor — 笔记编辑对话框
│       ├── note_float.py        # NoteFloatWindow — 桌面悬浮笔记窗
│       ├── clip_item_delegate.py # ClipItemDelegate — 剪贴板列表自定义绘制
│       ├── task_editor.py       # TaskEditor — 任务编辑对话框
│       └── task_reminder_popup.py # TaskReminderPopup — 提醒弹窗
│
└── data/                     # 数据访问层
    └── db.py                    # Database 层 (WAL 模式、版本迁移、写入队列)
```

### 架构分层

```
┌─────────────────────────────────────────┐
│              UI (ui/)                   │  ← PySide6 控件
├─────────────────────────────────────────┤
│           Core (core/)                  │  ← 业务逻辑
├─────────────────────────────────────────┤
│           Data (data/)                  │  ← 数据库访问、迁移
└─────────────────────────────────────────┘
```

### 核心数据流

```
剪贴板变化 → WM_CLIPBOARDUPDATE → ClipboardMonitor → ClipStore → clipboard.db
                                                       ↓
                                                  刷新 ClipPage UI

用户右键"转笔记" → NoteStore.create() → notes.db → 刷新 NotePage UI

TaskScheduler._tick()（每秒轮询）→ RuleParser 匹配 → 弹窗 / 执行动作

Ctrl+Alt+V 热键 → SearchWindow 弹出 → SearchEngine（子线程）→ 结果分组展示
```

---

## 🖼️ 界面预览

| 页面 | 说明 |
|------|------|
| **ClipCache** | 左侧剪贴板历史列表 + 搜索框 + 星标过滤，双击回填剪贴板 |
| **NoteNest** | 自适应网格卡片墙，支持拖拽排序、颜色 / 标签筛选、批量操作 |
| **TaskFlow** | 任务列表 + 状态筛选（进行中 / 已过期 / 已停用）+ 执行日志面板 |
| **设置** | 剪贴板上限、隐私过滤、备份策略、全局热键、主题切换、字体调节 |
| **快速搜索** | `Ctrl+Alt+V` 唤出，无边框置顶浮窗，按模块分组展示搜索结果 |
| **快速粘贴** | `Ctrl+Shift+V` 唤出，光标附近弹窗，选择历史条目自动粘贴 |

---

## 🙏 致谢

- [PySide6](https://wiki.qt.io/Qt_for_Python) — Qt6 的 Python 绑定
- [qt-material](https://github.com/UN-GCPDS/qt-material) — Material Design 主题
- [SQLite FTS5](https://www.sqlite.org/fts5.html) — 全文搜索引擎
