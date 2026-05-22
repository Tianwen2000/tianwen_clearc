from __future__ import annotations

from dataclasses import dataclass

from tianwen_clearc.models import ScanNode


@dataclass(slots=True)
class FilterSpec:
    """
    过滤条件规格，描述用户在 UI 中输入的所有过滤参数。
    各条件之间是 AND 关系：节点需同时满足所有非空条件才被保留。
    """
    query: str = ""         # 关键字，匹配文件名或路径（大小写不敏感）
    extension: str = ""     # 扩展名过滤，如 ".log" 或 "*.log"
    min_size: int = 0       # 最小字节数，0 表示不限制
    node_kind: str = "all"  # "all" / "files"（仅文件）/ "dirs"（仅目录）

    @property
    def normalized_query(self) -> str:
        """去除首尾空格并转小写，使匹配大小写不敏感。"""
        return self.query.strip().lower()

    @property
    def normalized_extension(self) -> str:
        """
        统一扩展名格式：
          - "*.log" → ".log"（去掉通配符星号）
          - "log"   → ".log"（补点）
          - ".log"  → ".log"（保持不变）
        """
        value = self.extension.strip().lower()
        if value.startswith("*."):
            return value[1:]
        if value and not value.startswith("."):
            return f".{value}"
        return value

    @property
    def is_empty(self) -> bool:
        """所有条件均为默认值时返回 True，用于跳过过滤直接返回深拷贝。"""
        return (
            not self.normalized_query
            and not self.normalized_extension
            and self.min_size <= 0
            and self.node_kind == "all"
        )


def node_matches(node: ScanNode, spec: FilterSpec) -> bool:
    """
    判断单个节点是否满足过滤条件（不考虑子节点）。
    用于叶子节点（文件）的直接匹配，以及目录节点的"自身是否匹配"判断。
    """
    # 类型过滤
    if spec.node_kind == "files" and node.is_dir:
        return False
    if spec.node_kind == "dirs" and not node.is_dir:
        return False

    # 关键字过滤：匹配文件名或完整路径
    query = spec.normalized_query
    if query and query not in node.name.lower() and query not in node.path.lower():
        return False

    # 扩展名过滤：目录没有扩展名，直接不匹配
    extension = spec.normalized_extension
    if extension and (node.is_dir or node.extension != extension):
        return False

    # 大小过滤
    return not (spec.min_size > 0 and node.size < spec.min_size)


def filter_tree(root: ScanNode, spec: FilterSpec) -> ScanNode:
    """
    对整棵树应用过滤条件，返回过滤后的树副本（不修改原树）。

    - 无过滤条件：直接返回深拷贝，保留完整结构。
    - 有过滤条件：调用 _filter_node 递归过滤，再排序（大块在前）。
    - 若根节点本身被完全过滤掉（无匹配子节点），返回只有根节点的空树，
      确保 UI 有节点可显示。
    """
    if spec.is_empty:
        return root.deep_copy()

    filtered = _filter_node(root, spec, is_root=True)
    if filtered is not None:
        filtered.sort_children()
        return filtered
    return root.shallow_copy(children=[])


def _filter_node(node: ScanNode, spec: FilterSpec, *, is_root: bool = False) -> ScanNode | None:
    """
    递归过滤节点，返回过滤后的副本，或 None（节点及其子节点均不匹配时）。

    文件节点：直接用 node_matches 判断，匹配则返回浅拷贝，否则返回 None。

    目录节点的处理逻辑：
    1. 若目录自身名称匹配（且非扩展名过滤、且非根节点），保留整棵子树（deep_copy），
       不再向下过滤——这样 "Windows" 目录会把里面所有文件都带出来。
    2. 否则递归过滤子节点，收集匹配的子节点构建新目录。
    3. 根节点（is_root=True）即使无匹配子节点也保留空壳，确保 UI 不崩溃。

    注：扩展名过滤启用时禁止目录"自身匹配"逻辑，避免把整个目录的文件都带出来
        而绕过扩展名筛选。
    """
    if not node.is_dir:
        return node.shallow_copy() if node_matches(node, spec) else None

    # 扩展名过滤时目录不能自身匹配（目录无扩展名，也不应继承所有子文件）
    extension_filter_active = bool(spec.normalized_extension)
    dir_self_matches = node_matches(node, spec) and not extension_filter_active

    # 非根目录自身匹配：保留完整子树，无需继续向下过滤
    if dir_self_matches and not is_root:
        return node.deep_copy()

    # 向下递归过滤子节点
    children = []
    for child in node.children:
        filtered_child = _filter_node(child, spec)
        if filtered_child is not None:
            children.append(filtered_child)

    # 根节点始终保留（即使 children 为空），非根目录无匹配子节点则丢弃
    if children or is_root:
        return node.shallow_copy(children=children)
    return None
