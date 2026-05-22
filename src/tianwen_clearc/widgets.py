from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from tianwen_clearc.models import ScanNode
from tianwen_clearc.treemap import LayoutItem, Rect, WeightedItem, layout_treemap


class TreemapWidget(QWidget):
    """
    Treemap 可视化控件，用 QPainter 直接绘制，实现嵌套矩形图。

    渲染原理：
      _layout_items() 生成一个扁平的 LayoutItem 列表，其中既包含目录块（父）
      也包含其子内容块（子）。绘制时按列表顺序画——父块先画（大背景色），
      子块后画（覆盖在父块内部），视觉上形成"带标题栏的目录框 + 内部内容"的效果。

    导航：双击目录块进入（push stack），点"上级"退出（pop stack）。
    """

    # ── 布局与渲染常量 ───────────────────────────────────────

    # 最小可读 tile 面积（像素²）。给 KB 级小项目保留可见区域，避免被压成 1px 点。
    MIN_READABLE_TILE_AREA = 22000

    # 视觉补偿（visual floor）占视口总面积的最大比例。
    # 对极小文件的权重做上调，保证当前层级的每个项目都能显示完整。
    MAX_TOTAL_FLOOR_RATIO = 0.42

    # 嵌套渲染最大深度：防止递归过深导致帧率下降
    MAX_PREVIEW_DEPTH = 4

    # 单层渲染的最大子节点数：超出部分截断，避免绘制数千个 1px 块
    MAX_PREVIEW_CHILDREN = 220

    # 目录块内部内容区域的最小尺寸：小于此值的目录块不展开显示子内容
    MIN_NESTED_WIDTH = 128
    MIN_NESTED_HEIGHT = 86

    # ── Qt 信号 ──────────────────────────────────────────────
    node_selected = Signal(object)          # 单击选中节点
    node_activated = Signal(object)         # 双击激活节点（进入目录）
    context_requested = Signal(object, QPoint)  # 右键请求上下文菜单
    navigation_changed = Signal(object)     # 导航层级变化（进入/退出目录）

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)     # 不按下按钮也能触发 mouseMoveEvent，用于 hover
        self.setMinimumSize(420, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._root: ScanNode | None = None      # 扫描树根节点（保持不变）
        self._current: ScanNode | None = None   # 当前视图节点（双击导航后改变）
        self._stack: list[ScanNode] = []        # 导航栈，go_up() 时 pop
        self._items: list[LayoutItem[ScanNode]] = []    # 当前帧的全部布局项
        self._selected: ScanNode | None = None  # 单击选中的节点
        self._hovered: ScanNode | None = None   # 鼠标悬停的节点

    # ── 公共接口 ─────────────────────────────────────────────

    @property
    def current_node(self) -> ScanNode | None:
        return self._current

    @property
    def selected_node(self) -> ScanNode | None:
        return self._selected

    def set_root(self, root: ScanNode | None) -> None:
        """加载新的扫描结果，重置导航栈并重新布局。"""
        self._root = root
        self._current = root
        self._stack = [root] if root else []
        self._selected = None
        self._hovered = None
        self._layout_items()
        self.navigation_changed.emit(root)
        self.update()

    def go_up(self) -> None:
        """退出当前目录，回到上一层（弹出导航栈）。"""
        if len(self._stack) <= 1:
            return
        self._stack.pop()
        self._current = self._stack[-1]
        self._selected = None
        self._layout_items()
        self.navigation_changed.emit(self._current)
        self.update()

    def reset_view(self) -> None:
        """回到根节点视图（清空导航栈）。"""
        if self._root:
            self.set_root(self._root)

    # ── Qt 事件 ──────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # 关闭抗锯齿，像素对齐更清晰
        painter.fillRect(self.rect(), QColor("#f7f4ee"))  # 背景色

        if not self._current:
            painter.setPen(QColor("#61594d"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "选择目录后开始扫描")
            return

        if not self._current.children:
            painter.setPen(QColor("#61594d"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "当前视图没有可显示的文件")
            return

        # 按列表顺序绘制：父块先画，子块后画（子块自然覆盖父块内部）
        for item in self._items:
            self._paint_item(painter, item)

    def resizeEvent(self, event) -> None:  # noqa: N802
        # 窗口大小变化时重新计算布局（布局依赖 self.width() / self.height()）
        self._layout_items()
        super().resizeEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # 只在 hover 节点变化时更新，避免每次移动都触发全量重绘
        item = self._item_at(event.position().x(), event.position().y())
        node = item.value if item else None
        if node is self._hovered:
            return
        self._hovered = node
        if node:
            QToolTip.showText(event.globalPosition().toPoint(), self._tooltip(node), self)
        else:
            QToolTip.hideText()
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        item = self._item_at(event.position().x(), event.position().y())
        self._selected = item.value if item else None
        if self._selected:
            self.node_selected.emit(self._selected)
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        item = self._item_at(event.position().x(), event.position().y())
        if not item:
            return
        node = item.value
        self.node_activated.emit(node)
        # 只有有子节点的目录才能进入（文件和空目录不导航）
        if node.is_dir and node.children:
            self._current = node
            self._stack.append(node)
            self._selected = None
            self._layout_items()
            self.navigation_changed.emit(node)
            self.update()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        item = self._item_at(event.pos().x(), event.pos().y())
        if item:
            self._selected = item.value
            self.node_selected.emit(self._selected)
            self.context_requested.emit(self._selected, event.globalPos())
            self.update()

    # ── 布局计算 ─────────────────────────────────────────────

    def _layout_items(self) -> None:
        """重新计算整个视图的布局，结果存入 self._items。"""
        if not self._current:
            self._items = []
            return
        bounds = Rect(0, 0, self.width(), self.height())
        # 顶层 padding=6：在视口边缘留出明显间距
        self._items = self._layout_children(self._current, bounds, depth=0, padding=6)

    def _layout_children(
        self,
        node: ScanNode,
        bounds: Rect,
        *,
        depth: int,
        padding: float,
    ) -> list[LayoutItem[ScanNode]]:
        """
        递归生成 node 的子节点布局列表。

        直接子节点（direct_items）先加入结果，然后对足够大的目录块递归生成
        其内部子节点（nested_items）也追加到同一列表。

        这样 self._items 是扁平列表但顺序有保证：父块 → 子块 → 孙块，
        paintEvent 按顺序画，后画的覆盖先画的，自然形成嵌套效果。
        """
        nodes = [child for child in node.children[:self.MAX_PREVIEW_CHILDREN] if child.size > 0]
        if not nodes or bounds.area <= 0:
            return []

        items = self._weighted_items(nodes, bounds.area)
        direct_items = layout_treemap(items, bounds, padding=padding)
        nested_items = list(direct_items)   # 先拷贝一份，后续 extend 子节点

        if depth >= self.MAX_PREVIEW_DEPTH:
            return nested_items

        for item in direct_items:
            child_bounds = self._nested_bounds(item.rect)
            # 只对足够大的目录块展开子内容，太小的块展开后子块会重叠
            if (
                item.value.is_dir
                and item.value.children
                and child_bounds.width >= self.MIN_NESTED_WIDTH
                and child_bounds.height >= self.MIN_NESTED_HEIGHT
            ):
                nested_items.extend(
                    self._layout_children(
                        item.value,
                        child_bounds,
                        depth=depth + 1,
                        padding=2,  # 嵌套层 padding 更小，节省空间
                    )
                )

        return nested_items

    def _nested_bounds(self, rect: Rect) -> Rect:
        """
        计算目录块内可用于放置子内容的区域，需去除：
        - 外边距（inset 5px）：目录块的视觉边框
        - 顶部标题栏（header_height）：显示目录名和大小的区域

        标题高度根据块高自适应：块足够高时用 38px（名称+大小两行），
        较矮时用 22px（单行紧凑标题）。
        """
        inset = rect.inset(5)
        header_height = 38 if inset.height >= 118 else 22
        return Rect(
            inset.x,
            inset.y + header_height,
            inset.width,
            max(inset.height - header_height, 0),
        )

    def _weighted_items(
        self,
        nodes: list[ScanNode],
        viewport_area: float,
    ) -> list[WeightedItem[ScanNode]]:
        """
        将节点列表转为带权重的布局输入，并对极小文件做视觉补偿（visual floor）。

        问题背景：若某目录下有 1 个 10GB 文件和 100 个 1KB 文件，
        直接用字节数作权重会导致 1KB 文件被压缩到不可见的 1px 点。

        解决方案：计算一个视觉最小面积 (min_tile_area)，
        将其换算回"最小字节数"(visual_floor)，
        每个节点的权重 = max(实际大小, visual_floor)。

        参数调优：
        - MIN_READABLE_TILE_AREA=22000：小项目也能显示名字和大小
        - MAX_TOTAL_FLOOR_RATIO=0.42：当前层级项目较少时，给小项目留出可读空间
        """
        if not nodes:
            return []

        viewport_area = max(viewport_area, 1)
        total_size = sum(node.size for node in nodes)

        # 每个条目的最大补偿面积 = 视口 × MAX_TOTAL_FLOOR_RATIO ÷ 条目数
        max_floor_area = viewport_area * self.MAX_TOTAL_FLOOR_RATIO / len(nodes)
        # 取 MIN_READABLE_TILE_AREA 和 max_floor_area 的较小值，防止补偿过度
        min_tile_area = min(self.MIN_READABLE_TILE_AREA, max_floor_area)
        # 将像素面积换算回字节域（面积/总面积 = 字节/总字节）
        visual_floor = total_size * min_tile_area / viewport_area

        return [
            WeightedItem(value=node, weight=max(node.size, visual_floor))
            for node in nodes
        ]

    # ── 绘制 ─────────────────────────────────────────────────

    def _paint_item(self, painter: QPainter, item: LayoutItem[ScanNode]) -> None:
        """
        绘制单个 tile（文件或目录块）。

        视觉层次：
        - inset(2)：每个块内缩 2px，形成相邻块之间的视觉间距
        - fillRect：填充背景色
        - drawRect：绘制边框（选中时加粗且变深色）
        - 文字：高度 >= 38px 时显示名称+大小两行；较矮时显示单行紧凑标签；
                宽度 < 52px 或高度 < 16px 时不显示文字（避免溢出）
        """
        node = item.value
        rect = item.rect.inset(2)
        qrect = QRectF(rect.x, rect.y, rect.width, rect.height)
        color = self._color_for(node)
        if node is self._hovered:
            color = color.lighter(112)  # hover 时略微提亮
        painter.fillRect(qrect, color)

        # 选中时用深色粗边框突出显示
        pen_color = QColor("#1f2528") if node is self._selected else QColor("#ffffff")
        pen_width = 2 if node is self._selected else 1
        painter.setPen(QPen(pen_color, pen_width))
        painter.drawRect(qrect)

        # 块太小时不绘制文字（文字会溢出或根本放不下）
        if rect.width < 52 or rect.height < 16:
            return

        painter.setPen(QColor("#111714"))
        metrics = QFontMetrics(painter.font())
        text_width = int(rect.width - 10)   # 左右各留 5px padding

        if rect.height >= 38:
            # 两行：第一行名称，第二行大小
            title = metrics.elidedText(node.display_name, Qt.TextElideMode.ElideRight, text_width)
            size = metrics.elidedText(node.formatted_size, Qt.TextElideMode.ElideRight, text_width)
            painter.drawText(QRectF(rect.x + 5, rect.y + 4, rect.width - 10, 18), title)
            painter.setPen(QColor("#2d3a35"))
            painter.drawText(QRectF(rect.x + 5, rect.y + 22, rect.width - 10, 18), size)
            return

        # 单行紧凑：名称 + 大小合并，超长时截断
        compact_text = f"{node.display_name}  {node.formatted_size}"
        compact_label = metrics.elidedText(compact_text, Qt.TextElideMode.ElideRight, text_width)
        painter.drawText(
            QRectF(rect.x + 5, rect.y, rect.width - 10, rect.height),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            compact_label,
        )

    # ── 命中检测 ─────────────────────────────────────────────

    def _item_at(self, x: float, y: float) -> LayoutItem[ScanNode] | None:
        """
        从后向前遍历 _items，返回坐标命中的最顶层块。
        反向遍历是因为子块排在父块后面，应优先被命中（子块覆盖在父块上面）。
        """
        for item in reversed(self._items):
            if item.rect.contains(x, y):
                return item
        return None

    # ── 颜色映射 ─────────────────────────────────────────────

    def _color_for(self, node: ScanNode) -> QColor:
        """
        根据节点类型/扩展名分配颜色：
        - 目录：统一金黄色（与背景形成对比，突出目录边框）
        - 常见扩展名：预定义颜色（压缩包蓝、视频红、图片绿……）
        - 其他扩展名：用扩展名字符的 ASCII 码取模，从 6 种柔和色中选一种，
                      保证同类扩展名颜色稳定（不随扫描顺序变化）
        """
        if node.is_dir:
            return QColor("#d9a441")
        extension = node.extension or "<none>"
        palette = {
            ".zip": "#80b1d3",
            ".rar": "#80b1d3",
            ".7z": "#80b1d3",
            ".mp4": "#fb8072",
            ".mov": "#fb8072",
            ".mkv": "#fb8072",
            ".jpg": "#b3de69",
            ".jpeg": "#b3de69",
            ".png": "#b3de69",
            ".log": "#bebada",
            ".tmp": "#fdb462",
            ".py": "#8dd3c7",
        }
        if extension in palette:
            return QColor(palette[extension])
        # 哈希到 6 种备用色，相同扩展名始终映射到相同颜色
        index = sum(ord(char) for char in extension) % 6
        return QColor(["#fccde5", "#bc80bd", "#ccebc5", "#ffed6f", "#a6cee3", "#fdbf6f"][index])

    # ── Tooltip ──────────────────────────────────────────────

    def _tooltip(self, node: ScanNode) -> str:
        """悬停提示：显示名称、大小、完整路径，目录额外显示子项统计，有错误时附上错误信息。"""
        lines = [
            node.display_name,
            node.formatted_size,
            node.path,
        ]
        if node.is_dir:
            lines.append(f"{node.file_count} files, {node.dir_count} dirs")
        if node.scan_error:
            lines.append(node.scan_error)
        return "\n".join(lines)
