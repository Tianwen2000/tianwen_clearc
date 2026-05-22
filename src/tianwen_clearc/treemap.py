from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

# ──────────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Rect:
    """不可变矩形，单位为像素浮点。frozen=True 保证布局计算中不会被意外修改。"""
    x: float
    y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        # 负值宽高视为 0，防止缩进后出现负面积
        return max(self.width, 0) * max(self.height, 0)

    def inset(self, value: float) -> Rect:
        """向内收缩 value 像素（四边同时缩进），用于留出 padding/border 空间。"""
        shrink = value * 2
        return Rect(
            self.x + value,
            self.y + value,
            max(self.width - shrink, 0),
            max(self.height - shrink, 0),
        )

    def contains(self, x: float, y: float) -> bool:
        """判断像素坐标是否落在矩形内，用于鼠标命中检测。"""
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height


@dataclass(frozen=True, slots=True)
class WeightedItem(Generic[T]):
    """带权重的泛型数据项，weight 决定在 treemap 中占多大面积。"""
    value: T
    weight: float


@dataclass(frozen=True, slots=True)
class LayoutItem(Generic[T]):
    """布局结果：原始数据 + 计算出的矩形区域 + 原始权重（供渲染层使用）。"""
    value: T
    rect: Rect
    weight: float


# ──────────────────────────────────────────────────────────────
# 对外入口
# ──────────────────────────────────────────────────────────────

def layout_treemap(
    items: list[WeightedItem[T]],
    bounds: Rect,
    *,
    padding: float = 2.0,
) -> list[LayoutItem[T]]:
    """
    将带权重的条目列表映射到 bounds 内的矩形布局（Squarify 算法）。

    padding：在 bounds 四边留出的空白像素，防止相邻块紧贴边框。
    返回列表顺序与面积无关，渲染时按顺序绘制即可（父块先画，子块后画盖在上面）。
    """
    usable = bounds.inset(padding)
    if usable.area <= 0:
        return []

    # 过滤掉 weight <= 0 的条目（空目录、0 字节文件），避免除零
    positive_items = [item for item in items if item.weight > 0]
    if not positive_items:
        return []

    # 按权重降序排列：Squarify 对有序输入的长宽比更优
    positive_items.sort(key=lambda item: item.weight, reverse=True)

    # 将权重缩放为像素面积，使所有条目面积之和 == usable.area
    total = sum(item.weight for item in positive_items)
    scale = usable.area / total if total else 0
    entries = [(item, item.weight * scale) for item in positive_items]

    result: list[LayoutItem[T]] = []
    _squarify(entries, usable.x, usable.y, usable.width, usable.height, result)
    return result


# ──────────────────────────────────────────────────────────────
# Squarify 核心算法（Bruls et al. 2000）
# ──────────────────────────────────────────────────────────────

def _squarify(
    entries: list[tuple[WeightedItem[T], float]],
    x: float,
    y: float,
    width: float,
    height: float,
    result: list[LayoutItem[T]],
) -> None:
    """
    递归地将 entries（已按面积降序）填入 (x, y, width, height) 所描述的剩余空间。

    核心思路：
      - 逐个尝试把条目加入当前"行"（row）。
      - 每次加入前用 _worst() 评估长宽比质量；若加入后变差则提前提交当前行，
        缩小剩余空间，然后对剩余条目递归（实为迭代）。
      - 最终所有条目都被分配到某个矩形块中。
    """
    row: list[tuple[WeightedItem[T], float]] = []
    remaining = entries[:]

    while remaining:
        item = remaining[0]
        side = min(width, height)   # 当前容器的短边，是评估长宽比的基准

        # 若 row 为空（必须至少放一个），或加入新条目能改善（或持平）长宽比，则加入
        if not row or _worst(row + [item], side) <= _worst(row, side):
            row.append(item)
            remaining.pop(0)
        else:
            # 加入后长宽比变差：提交当前行，用返回的剩余空间继续下一轮
            x, y, width, height = _layout_row(row, x, y, width, height, result)
            row = []

    # 循环结束后 remaining 为空，但 row 可能还有未提交的条目
    if row:
        _layout_row(row, x, y, width, height, result)


def _worst(row: list[tuple[WeightedItem[T], float]], side: float) -> float:
    """
    计算当前行在短边长度为 side 时的"最差长宽比"（Bruls 论文的 worst() 函数）。

    推导：若 row 沿 side 方向排列，条目 i 的两条边分别为：
      - 固定边 = row_total_area / side（所有条目共享）
      - 变化边 = item_area_i * side / row_total_area
    最差长宽比 = max(固定边/变化边的最大值, 变化边/固定边的最大值)
               = max(side² * max_area / sum², sum² / (side² * min_area))

    返回值越小说明布局越接近正方形；用于决定是否继续向行中添加条目。
    """
    if not row or side <= 0:
        return float("inf")
    areas = [area for _, area in row]
    row_sum = sum(areas)
    if row_sum <= 0:
        return float("inf")
    max_area = max(areas)
    min_area = min(areas)
    if min_area <= 0:
        return float("inf")
    side_squared = side * side
    return max(
        (side_squared * max_area) / (row_sum * row_sum),
        (row_sum * row_sum) / (side_squared * min_area),
    )


def _layout_row(
    row: list[tuple[WeightedItem[T], float]],
    x: float,
    y: float,
    width: float,
    height: float,
    result: list[LayoutItem[T]],
) -> tuple[float, float, float, float]:
    """
    将 row 中的条目实际放置到矩形中，并返回剩余空间坐标。

    关键原则：始终沿"短边"方向切割，这样条目的两条边之比最接近 1:1。

    - 宽容器（width >= height）：沿左侧切出一条竖列（column）。
        列宽 = row_total_area / height（短边），
        各条目在列内从上到下堆叠，高度 = item_area / 列宽。
        切割后剩余空间：x 右移，width 减小。

    - 高容器（height > width）：沿顶部切出一条横行（row）。
        行高 = row_total_area / width（短边），
        各条目在行内从左到右排列，宽度 = item_area / 行高。
        切割后剩余空间：y 下移，height 减小。

    注意：早期实现用 row_area/width（长边）作为分母，产生扁条；
    正确做法必须用短边（height 或 width）作为分母。
    """
    row_area = sum(area for _, area in row)
    if row_area <= 0 or width <= 0 or height <= 0:
        return x, y, width, height

    if width >= height:
        # 宽容器：在左侧切一条竖列，条目从上到下堆叠
        col_width = min(row_area / height, width)   # 用短边 height 做分母
        cursor_y = y
        for item, area in row:
            item_height = area / col_width if col_width else 0
            result.append(
                LayoutItem(
                    value=item.value,
                    rect=Rect(x, cursor_y, col_width, item_height),
                    weight=item.weight,
                )
            )
            cursor_y += item_height
        # 剩余空间：x 右移，宽度缩小
        return x + col_width, y, max(width - col_width, 0), height

    # 高容器：在顶部切一条横行，条目从左到右排列
    row_height = min(row_area / width, height)      # 用短边 width 做分母
    cursor_x = x
    for item, area in row:
        item_width = area / row_height if row_height else 0
        result.append(
            LayoutItem(
                value=item.value,
                rect=Rect(cursor_x, y, item_width, row_height),
                weight=item.weight,
            )
        )
        cursor_x += item_width
    # 剩余空间：y 下移，高度缩小
    return x, y + row_height, width, max(height - row_height, 0)
