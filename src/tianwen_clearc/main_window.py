from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tianwen_clearc.actions import open_path, reveal_in_file_manager
from tianwen_clearc.branding import APP_DISPLAY_NAME, DEFAULT_REPORT_NAME
from tianwen_clearc.export import export_csv, export_json
from tianwen_clearc.filters import FilterSpec, filter_tree
from tianwen_clearc.models import ScanNode, format_size
from tianwen_clearc.scanner import ScanCancelled, ScanProgress, SkippedPath, scan_path
from tianwen_clearc.settings import load_settings, save_settings
from tianwen_clearc.tree_widgets import StableTreeWidget
from tianwen_clearc.widgets import TreemapWidget


def missing_path_message(path: str) -> str:
    """生成"路径不存在"的提示文字，供对话框显示。"""
    return (
        "所选路径不存在，可能已经被删除、移动或重命名。\n\n"
        f"路径：{path}\n\n"
        "请点击“选择”重新选择一个存在的磁盘或目录，然后再扫描。"
    )


# ──────────────────────────────────────────────────────────────
# 后台扫描工作线程
# ──────────────────────────────────────────────────────────────

class ScanWorker(QObject):
    """
    在 QThread 中执行目录扫描，通过 Qt 信号将结果传回主线程。

    为什么用 QObject + moveToThread 而不是直接继承 QThread：
    - QObject 的信号槽跨线程是安全的（自动 QueuedConnection）。
    - moveToThread 模式更易于管理生命周期和取消逻辑。

    取消机制：cancel() 设置 threading.Event，
    scan_path() 在每个条目扫描前检查该 Event，触发 ScanCancelled 异常。
    """
    progress = Signal(object)   # 参数：ScanProgress 快照
    finished = Signal(object)   # 参数：ScanNode 根节点
    failed = Signal(str)        # 参数：错误提示文字
    cancelled = Signal()        # 无参数，扫描被用户取消

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        self._cancel_event = threading.Event()

    @Slot()
    def run(self) -> None:
        """QThread.started 信号触发此方法，在工作线程中执行扫描。"""
        try:
            root = scan_path(
                self.path,
                cancel_event=self._cancel_event,
                on_progress=self.progress.emit,
            )
        except ScanCancelled:
            self.cancelled.emit()
        except FileNotFoundError:
            self.failed.emit(missing_path_message(self.path))
        except Exception as exc:  # pragma: no cover - UI boundary
            self.failed.emit(f"扫描过程中发生错误：\n\n{exc}")
        else:
            self.finished.emit(root)

    def cancel(self) -> None:
        """由主线程调用，通知工作线程尽快停止扫描。"""
        self._cancel_event.set()


# ──────────────────────────────────────────────────────────────
# 主窗口
# ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    TREE_PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 1

    """
    应用主窗口，负责协调 UI 构建、扫描线程管理、过滤、导出和导航。

    数据流：
      扫描完成 → raw_root（原始树）
      apply_filter() → view_root（过滤后副本）→ 更新 TreemapWidget + StableTreeWidget
      用户在 treemap 导航 → 只改变 treemap 内部视图，不影响 view_root
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1180, 760)
        self.settings = load_settings()
        self.raw_root: ScanNode | None = None   # 扫描结果原始树（不被过滤修改）
        self.view_root: ScanNode | None = None  # 当前显示树（过滤后副本）
        self.thread: QThread | None = None
        self.worker: ScanWorker | None = None
        self.skipped_paths: list[SkippedPath] = []
        self._build_ui()
        self._restore_settings()

    def closeEvent(self, event) -> None:  # noqa: N802
        # 关窗时保存设置，并请求取消正在进行的扫描（不强制等待线程结束）
        self._save_settings()
        if self.worker:
            self.worker.cancel()
        super().closeEvent(event)

    # ── UI 构建 ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        """
        构建完整 UI 布局：
          顶部栏：目标路径 + 操作按钮（选择/扫描/取消/上级/导出）
          过滤栏：关键字 + 扩展名 + 最小大小 + 类型下拉
          内容区：垂直 Splitter，上方目录树，下方 treemap
          底部：状态栏
        """
        container = QWidget(self)
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(10, 10, 10, 8)
        root_layout.setSpacing(8)

        # ── 路径行 ──
        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("选择要扫描的磁盘或目录")
        self.browse_button = QPushButton("选择")
        self.scan_button = QPushButton("扫描")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        self.up_button = QPushButton("上级")
        self.up_button.setEnabled(False)
        self.export_button = QPushButton("导出")
        self.export_button.setEnabled(False)

        path_row.addWidget(QLabel("目标"))
        path_row.addWidget(self.path_input, 1)
        path_row.addWidget(self.browse_button)
        path_row.addWidget(self.scan_button)
        path_row.addWidget(self.cancel_button)
        path_row.addWidget(self.up_button)
        path_row.addWidget(self.export_button)

        # ── 过滤行 ──
        filter_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("关键字")
        self.extension_input = QLineEdit()
        self.extension_input.setPlaceholderText("扩展名，例如 *.log")
        self.min_size_input = QLineEdit()
        self.min_size_input.setPlaceholderText("最小 MB")
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("全部", "all")
        self.kind_combo.addItem("仅文件", "files")
        self.kind_combo.addItem("仅目录", "dirs")
        self.apply_filter_button = QPushButton("应用过滤")
        self.clear_filter_button = QPushButton("清空")

        filter_row.addWidget(QLabel("过滤"))
        filter_row.addWidget(self.query_input, 2)
        filter_row.addWidget(self.extension_input, 1)
        filter_row.addWidget(self.min_size_input, 1)
        filter_row.addWidget(self.kind_combo)
        filter_row.addWidget(self.apply_filter_button)
        filter_row.addWidget(self.clear_filter_button)

        # ── 详情标签（目录树和 treemap 各一个） ──
        self.tree_detail_label = self._detail_label("目录树：未选择")
        self.treemap_detail_label = self._detail_label("图形树：未选择")

        # ── 目录树控件 ──
        self.tree = StableTreeWidget()
        self.tree.setHeaderLabels(["名称", "大小", "文件", "目录"])
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(190)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setAutoScroll(False)
        self.tree.header().setStretchLastSection(False)
        for column in range(4):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)

        # ── Treemap 控件 ──
        self.treemap = TreemapWidget()

        # ── 两个面板分别放入 QVBoxLayout，再放入 Splitter ──
        tree_panel = QWidget()
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(4)
        tree_layout.addWidget(self.tree_detail_label)
        tree_layout.addWidget(self.tree, 1)

        treemap_panel = QWidget()
        treemap_layout = QVBoxLayout(treemap_panel)
        treemap_layout.setContentsMargins(0, 0, 0, 0)
        treemap_layout.setSpacing(4)
        treemap_layout.addWidget(self.treemap_detail_label)
        treemap_layout.addWidget(self.treemap, 1)

        # 垂直分割：上方目录树占 2/5，下方 treemap 占 3/5
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(tree_panel)
        splitter.addWidget(treemap_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([260, 460])

        root_layout.addLayout(path_row)
        root_layout.addLayout(filter_row)
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(container)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.skipped_details_button = QPushButton("无权限跳过 0 项")
        self.skipped_details_button.setEnabled(False)
        self.skipped_details_button.setVisible(False)
        self.status.addPermanentWidget(self.skipped_details_button)
        self.status.showMessage("准备就绪")

        # ── 信号连接 ──
        self.browse_button.clicked.connect(self.select_path)
        self.scan_button.clicked.connect(self.start_scan)
        self.cancel_button.clicked.connect(self.cancel_scan)
        self.up_button.clicked.connect(self.treemap.go_up)
        self.export_button.clicked.connect(self.export_current_view)
        self.apply_filter_button.clicked.connect(self.apply_filter)
        self.clear_filter_button.clicked.connect(self.clear_filter)
        self.query_input.returnPressed.connect(self.apply_filter)
        self.extension_input.returnPressed.connect(self.apply_filter)
        self.min_size_input.returnPressed.connect(self.apply_filter)
        self.treemap.navigation_changed.connect(self.update_navigation)
        self.treemap.node_selected.connect(self.show_treemap_details)
        self.treemap.context_requested.connect(self.show_context_menu)
        self.tree.itemExpanded.connect(self.ensure_tree_item_children)
        self.tree.itemClicked.connect(self.show_tree_item_details)
        self.tree.itemDoubleClicked.connect(self.show_tree_item_details)
        self.skipped_details_button.clicked.connect(self.show_skipped_details)

    def _detail_label(self, text: str) -> QLabel:
        """创建带统一样式的详情标签（可鼠标选中文本，供用户复制路径）。"""
        label = QLabel(text)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setMinimumHeight(26)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setStyleSheet(
            "QLabel {"
            "background: #ece8df;"
            "border: 1px solid #c8c1b3;"
            "padding: 4px 7px;"
            "color: #1b1b1b;"
            "}"
        )
        return label

    # ── 设置持久化 ───────────────────────────────────────────

    def _restore_settings(self) -> None:
        """启动时从本地配置文件恢复上次扫描的路径。"""
        recent_path = self.settings.get("recent_path")
        if recent_path:
            self.path_input.setText(recent_path)

    def _save_settings(self) -> None:
        """退出前将当前路径输入框内容写入配置文件。"""
        save_settings({"recent_path": self.path_input.text().strip()})

    # ── 扫描流程 ─────────────────────────────────────────────

    @Slot()
    def select_path(self) -> None:
        """打开系统目录选择对话框，将选中路径填入输入框。"""
        start_path = self.path_input.text().strip() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "选择扫描目录", start_path)
        if directory:
            self.path_input.setText(directory)

    @Slot()
    def start_scan(self) -> None:
        """
        启动后台扫描：
        1. 校验路径存在
        2. 重置 UI 状态（清空树和 treemap）
        3. 创建 QThread + ScanWorker，连接信号槽，启动线程
        """
        path = self.path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "缺少路径", "请先选择要扫描的磁盘或目录。")
            self.path_input.setFocus()
            return

        target_path = Path(path).expanduser()
        try:
            path_exists = target_path.exists()
        except OSError:
            path_exists = False
        if not path_exists:
            self.show_missing_path_warning(path)
            return

        # 清空上次扫描结果，防止旧数据残留
        self.raw_root = None
        self.view_root = None
        self.skipped_paths = []
        self.update_skipped_details_button()
        self.tree.clear()
        self.treemap.set_root(None)
        self.tree_detail_label.setText("目录树：扫描中")
        self.treemap_detail_label.setText("图形树：扫描中")
        self.scan_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.status.showMessage("开始扫描...")

        # QThread + moveToThread 模式：worker 在子线程事件循环中运行
        self.thread = QThread(self)
        self.worker = ScanWorker(str(target_path))
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_scan_progress)
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.failed.connect(self.on_scan_failed)
        self.worker.cancelled.connect(self.on_scan_cancelled)
        # 任意终止信号都让线程退出事件循环
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        # 线程结束后自动销毁 worker 和 thread 对象
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._clear_thread_refs)
        self.thread.start()

    @Slot()
    def cancel_scan(self) -> None:
        """请求取消扫描（异步，实际停止由 ScanWorker.run 检测 cancel_event 后处理）。"""
        if self.worker:
            self.worker.cancel()
        self.status.showMessage("正在取消扫描...")

    @Slot(object)
    def on_scan_progress(self, progress: ScanProgress) -> None:
        """接收扫描进度更新，刷新状态栏（由 Qt QueuedConnection 在主线程执行）。"""
        self.skipped_paths = list(progress.skipped_paths)
        self.update_skipped_details_button()
        message = (
            f"扫描中：{progress.scanned_files} 个文件，"
            f"{progress.scanned_dirs} 个目录，{format_size(progress.scanned_bytes)}，"
            f"无权限跳过 {progress.skipped_count} 项"
        )
        self.status.showMessage(message)

    @Slot(object)
    def on_scan_finished(self, root: ScanNode) -> None:
        """扫描成功完成：保存原始结果，触发过滤并更新视图。"""
        self.raw_root = root
        self.apply_filter()     # 用当前过滤条件立即更新视图
        self.scan_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.export_button.setEnabled(True)
        skipped_text = (
            f"，无权限跳过 {len(self.skipped_paths)} 项"
            if self.skipped_paths
            else ""
        )
        self.status.showMessage(
            f"扫描完成：{root.file_count} 个文件，"
            f"{root.dir_count} 个目录，总计 {root.formatted_size}{skipped_text}"
        )

    @Slot(str)
    def on_scan_failed(self, message: str) -> None:
        """扫描失败：弹出错误对话框，恢复按钮状态。"""
        self.scan_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        QMessageBox.warning(self, "无法完成扫描", message)
        self.status.showMessage("扫描失败，请检查目标路径")

    def show_missing_path_warning(self, path: str) -> None:
        """路径不存在时弹出提示，并让输入框获得焦点方便用户重新输入。"""
        QMessageBox.warning(self, "无法开始扫描", missing_path_message(path))
        self.status.showMessage("所选路径不存在，请重新选择扫描目标")
        self.path_input.setFocus()
        self.path_input.selectAll()

    @Slot()
    def on_scan_cancelled(self) -> None:
        self.scan_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status.showMessage("扫描已取消")

    @Slot()
    def _clear_thread_refs(self) -> None:
        """线程结束后清除引用，避免持有已销毁对象的指针。"""
        self.thread = None
        self.worker = None

    def update_skipped_details_button(self) -> None:
        """根据当前跳过详情显示/隐藏状态栏按钮。"""
        count = len(self.skipped_paths)
        self.skipped_details_button.setText(f"无权限跳过 {count} 项")
        self.skipped_details_button.setEnabled(count > 0)
        self.skipped_details_button.setVisible(count > 0)

    @Slot()
    def show_skipped_details(self) -> None:
        """弹出不可访问路径列表，帮助用户确认哪些目录被跳过。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("无权限跳过详情")
        dialog.resize(760, 420)

        layout = QVBoxLayout(dialog)
        label = QLabel(
            f"扫描时有 {len(self.skipped_paths)} 项无法读取，已跳过但不影响其余目录统计。"
        )
        layout.addWidget(label)

        table = QTableWidget(len(self.skipped_paths), 2, dialog)
        table.setHorizontalHeaderLabels(["路径", "原因"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        for row, skipped in enumerate(self.skipped_paths):
            table.setItem(row, 0, QTableWidgetItem(skipped.path))
            table.setItem(row, 1, QTableWidgetItem(skipped.reason))

        layout.addWidget(table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # ── 过滤 ─────────────────────────────────────────────────

    @Slot()
    def apply_filter(self) -> None:
        """
        用当前过滤条件生成 view_root（raw_root 的过滤副本），
        并同步更新 treemap 和目录树两个视图。
        """
        if not self.raw_root:
            return
        spec = self._current_filter()
        self.view_root = filter_tree(self.raw_root, spec)
        self.treemap.set_root(self.view_root)
        self.populate_tree(self.view_root)
        self.tree_detail_label.setText(f"目录树：{self.node_details(self.view_root)}")
        self.treemap_detail_label.setText(f"图形树：{self.node_details(self.view_root)}")
        self.export_button.setEnabled(True)

    @Slot()
    def clear_filter(self) -> None:
        """清空所有过滤输入框，并重新应用（等效于显示完整树）。"""
        self.query_input.clear()
        self.extension_input.clear()
        self.min_size_input.clear()
        self.kind_combo.setCurrentIndex(0)
        self.apply_filter()

    def _current_filter(self) -> FilterSpec:
        """从 UI 控件读取当前过滤参数，min_size 输入框的单位是 MB，转换为字节。"""
        min_size = 0
        text = self.min_size_input.text().strip()
        if text:
            try:
                min_size = int(float(text) * 1024 * 1024)
            except ValueError:
                self.min_size_input.clear()     # 非数字输入直接清空
        return FilterSpec(
            query=self.query_input.text(),
            extension=self.extension_input.text(),
            min_size=min_size,
            node_kind=self.kind_combo.currentData(),
        )

    # ── 目录树填充 ───────────────────────────────────────────

    def populate_tree(self, root: ScanNode) -> None:
        """清空目录树控件，以 root 为顶节点重新填充，并展开顶层节点。"""
        self.tree.clear()
        top = self._tree_item(root)
        self.tree.addTopLevelItem(top)
        self._populate_tree_children(top, root, depth=0)
        self.tree.expandItem(top)
        self.apply_tree_column_widths()
        self.reset_tree_view_position()

    def apply_tree_column_widths(self) -> None:
        """固定目录树列宽，避免点击深层文件时名称列被 Qt 自动撑大。"""
        fixed_columns_width = 88 + 76 + 76
        name_width = max(self.tree.viewport().width() - fixed_columns_width - 28, 260)
        self.tree.setColumnWidth(0, name_width)
        self.tree.setColumnWidth(1, 88)
        self.tree.setColumnWidth(2, 76)
        self.tree.setColumnWidth(3, 76)

    def reset_tree_view_position(self) -> None:
        self.apply_tree_column_widths()
        self.tree.reset_horizontal_scroll()
        QTimer.singleShot(0, self._reset_tree_view_position_later)

    def _reset_tree_view_position_later(self) -> None:
        self.apply_tree_column_widths()
        self.tree.reset_horizontal_scroll()

    def _populate_tree_children(
        self,
        parent_item: QTreeWidgetItem,
        node: ScanNode,
        depth: int,
    ) -> None:
        """
        递归填充目录树子节点，最多展示 4 层深度和每层前 500 个条目。
        超过预载深度的目录会在用户点击时懒加载下一层。
        """
        for child in node.children[:500]:
            item = self._tree_item(child)
            parent_item.addChild(item)
            if child.children and depth < 3:
                self._populate_tree_children(item, child, depth + 1)
            elif child.children:
                self.add_tree_placeholder(item)

    def add_tree_placeholder(self, item: QTreeWidgetItem) -> None:
        """给未懒加载的目录加一个占位子项，让 Qt 默认显示展开箭头。"""
        placeholder = QTreeWidgetItem(["加载中...", "", "", ""])
        placeholder.setData(0, self.TREE_PLACEHOLDER_ROLE, True)
        item.addChild(placeholder)

    def has_tree_placeholder(self, item: QTreeWidgetItem) -> bool:
        return (
            item.childCount() == 1
            and item.child(0).data(0, self.TREE_PLACEHOLDER_ROLE) is True
        )

    @Slot(QTreeWidgetItem)
    def ensure_tree_item_children(self, item: QTreeWidgetItem) -> None:
        """目录项被点击/展开时，按需补齐下一层子节点。"""
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(node, ScanNode) or not node.children:
            return
        if item.childCount() > 0 and not self.has_tree_placeholder(item):
            return

        item.takeChildren()
        for child in node.children[:500]:
            child_item = self._tree_item(child)
            item.addChild(child_item)
            if child.children:
                self.add_tree_placeholder(child_item)
        self.apply_tree_column_widths()
        self.reset_tree_view_position()

    def _tree_item(self, node: ScanNode) -> QTreeWidgetItem:
        """
        创建单个树条目，将 ScanNode 对象存入 UserRole 数据，
        数字列右对齐以便比较大小。
        """
        item = QTreeWidgetItem(
            [
                node.display_name,
                node.formatted_size,
                str(node.file_count),
                str(node.dir_count),
            ]
        )
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        for column in range(1, 4):
            item.setTextAlignment(
                column,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
        return item

    # ── 详情显示 ─────────────────────────────────────────────

    @Slot(QTreeWidgetItem, int)
    def show_tree_item_details(self, item: QTreeWidgetItem, column: int) -> None:
        """目录树单击/双击：将节点详情显示到标签和状态栏。"""
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node, ScanNode):
            self.ensure_tree_item_children(item)
            if node.children:
                item.setExpanded(True)
            self.reset_tree_view_position()
            details = self.node_details(node)
            self.tree_detail_label.setText(f"目录树：{details}")
            self.status.showMessage(details)

    @Slot(object)
    def update_navigation(self, node: ScanNode | None) -> None:
        """
        treemap 导航层级变化时更新 treemap 详情标签和"上级"按钮状态。
        根节点时禁用"上级"按钮（已在最顶层）。
        """
        if not node:
            self.treemap_detail_label.setText("图形树：未选择")
            self.up_button.setEnabled(False)
            return
        self.treemap_detail_label.setText(f"图形树：{self.node_details(node)}")
        self.up_button.setEnabled(node is not self.view_root)

    @Slot(object)
    def show_treemap_details(self, node: ScanNode) -> None:
        """treemap 单击选中：将节点详情显示到标签和状态栏。"""
        details = self.node_details(node)
        self.treemap_detail_label.setText(f"图形树：{details}")
        self.status.showMessage(details)

    def node_details(self, node: ScanNode) -> str:
        """格式化节点的摘要信息：路径 + 大小 + （目录时的）子项统计。"""
        details = f"{node.path} | {node.formatted_size}"
        if node.is_dir:
            details += f" | {node.file_count} 个文件，{node.dir_count} 个目录"
        return details

    # ── 右键菜单 ─────────────────────────────────────────────

    @Slot(object, object)
    def show_context_menu(self, node: ScanNode, global_pos) -> None:
        """弹出右键菜单，提供打开、在资源管理器显示、复制路径三个操作。"""
        menu = QMenu(self)
        open_action = QAction("打开", self)
        reveal_action = QAction("在资源管理器中显示", self)
        copy_action = QAction("复制路径", self)
        open_action.triggered.connect(lambda: open_path(node.path))
        reveal_action.triggered.connect(lambda: reveal_in_file_manager(node.path))
        copy_action.triggered.connect(lambda: QGuiApplication.clipboard().setText(node.path))
        menu.addAction(open_action)
        menu.addAction(reveal_action)
        menu.addAction(copy_action)
        menu.exec(global_pos)

    # ── 导出 ─────────────────────────────────────────────────

    @Slot()
    def export_current_view(self) -> None:
        """
        弹出"另存为"对话框，将当前 view_root 导出为 CSV 或 JSON 文件。
        格式由文件对话框的过滤器选择或文件扩展名决定。
        CSV 默认带 BOM（UTF-8-sig），确保 Excel 正确显示中文路径。
        """
        root = self.view_root
        if not root:
            return
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出报告",
            str(Path.home() / DEFAULT_REPORT_NAME),
            "CSV (*.csv);;JSON (*.json)",
        )
        if not destination:
            return
        try:
            if selected_filter.startswith("JSON") or destination.lower().endswith(".json"):
                export_json(root, destination)
            else:
                if not destination.lower().endswith(".csv"):
                    destination += ".csv"
                export_csv(root, destination)
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self.status.showMessage(f"已导出：{destination}")
