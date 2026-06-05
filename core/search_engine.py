"""全局搜索引擎 - SearchEngine。

聚合 ClipCache / NoteNest 两个数据源的搜索结果。
"""

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, Slot


class _SearchWorker(QRunnable):
    """在子线程中执行搜索，避免阻塞 UI。"""

    def __init__(self, keyword, clip_store, note_store, callback):
        super().__init__()
        self._keyword = keyword
        self._clip_store = clip_store
        self._note_store = note_store
        self._callback = callback

    def run(self):
        results = []
        keyword = self._keyword

        # ClipCache
        clip_results = self._clip_store.search(keyword) if self._clip_store else []
        results.append({"module": "clip", "label": "剪贴板历史", "results": clip_results})

        # NoteNest
        note_results = self._note_store.search(keyword) if self._note_store else []
        results.append({"module": "note", "label": "微笔记", "results": note_results})

        self._callback(results)


class SearchEngine(QObject):
    """全局搜索引擎。

    用法:
        engine = SearchEngine(clip_store, note_store)
        engine.search_completed.connect(handle_results)
        engine.search("关键词")
    """

    search_completed = Signal(list)  # 分组结果

    def __init__(self, clip_store=None, note_store=None):
        super().__init__()
        self._clip_store = clip_store
        self._note_store = note_store
        self._pool = QThreadPool()

    def search(self, keyword: str):
        if not keyword.strip():
            self.search_completed.emit([])
            return
        worker = _SearchWorker(
            keyword, self._clip_store, self._note_store,
            self._on_results,
        )
        self._pool.start(worker)

    @Slot(list)
    def _on_results(self, results):
        self.search_completed.emit(results)