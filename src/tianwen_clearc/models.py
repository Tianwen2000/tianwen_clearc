from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tianwen_clearc.display import display_name_for_path

# 大小单位表，按 1024 进位递增
SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_size(size: int | float) -> str:
    """将字节数转换为人类可读字符串，例如 1536 → '1.5 KB'。"""
    value = float(max(size, 0))
    unit_index = 0
    while value >= 1024 and unit_index < len(SIZE_UNITS) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {SIZE_UNITS[unit_index]}"
    return f"{value:.1f} {SIZE_UNITS[unit_index]}"


@dataclass(slots=True)
class ScanNode:
    """
    文件系统扫描树的节点，既可表示文件也可表示目录。

    slots=True：用 __slots__ 代替 __dict__，减少大规模扫描时的内存占用。
    目录节点的 size / file_count / dir_count 由 add_child() 或
    recalculate_from_children() 累加得出，而非直接赋值。
    """
    name: str               # 文件/目录名（不含父路径）
    path: str               # 完整绝对路径
    is_dir: bool
    size: int = 0           # 字节数；目录为所有子孙文件之和
    modified_at: float | None = None    # Unix 时间戳（st_mtime）
    children: list[ScanNode] = field(default_factory=list)
    file_count: int = 0     # 子孙文件总数（不含目录自身）
    dir_count: int = 0      # 子孙目录总数（不含自身）
    scan_error: str | None = None   # 读取失败时记录错误信息，节点仍保留在树中
    tag: str | None = None  # 预留标签，供过滤或高亮使用

    # ── 只读属性 ────────────────────────────────────────────

    @property
    def extension(self) -> str:
        """返回小写扩展名（含点），目录返回空字符串。"""
        if self.is_dir:
            return ""
        return Path(self.name).suffix.lower()

    @property
    def display_name(self) -> str:
        """优先显示 name，name 为空时降级显示完整 path（根节点场景）。"""
        return display_name_for_path(self.name, self.path)

    @property
    def formatted_size(self) -> str:
        return format_size(self.size)

    # ── 树构建 ──────────────────────────────────────────────

    def add_child(self, child: ScanNode) -> None:
        """
        追加子节点并同步更新父节点的统计数据。
        扫描器逐条调用此方法构建树，无需事后遍历重算。
        """
        self.children.append(child)
        self.size += child.size
        # 子节点是目录：继承其 file_count，dir_count+1（目录本身也算一个）
        # 子节点是文件：file_count+1
        self.file_count += child.file_count if child.is_dir else 1
        self.dir_count += child.dir_count + 1 if child.is_dir else 0

    def sort_children(self) -> None:
        """按 size 降序递归排序，使 treemap 把大块放在左上角（squarify 对有序输入效果更好）。"""
        self.children.sort(key=lambda child: child.size, reverse=True)
        for child in self.children:
            child.sort_children()

    # ── 复制 ────────────────────────────────────────────────

    def shallow_copy(self, children: list[ScanNode] | None = None) -> ScanNode:
        """
        浅拷贝：复制当前节点的所有字段，children 可替换为新列表。
        若提供了 children，会调用 recalculate_from_children() 重新统计大小。
        过滤器用此方法在不修改原树的情况下生成过滤后的树副本。
        """
        copied = ScanNode(
            name=self.name,
            path=self.path,
            is_dir=self.is_dir,
            size=self.size,
            modified_at=self.modified_at,
            children=children or [],
            file_count=self.file_count,
            dir_count=self.dir_count,
            scan_error=self.scan_error,
            tag=self.tag,
        )
        if children is not None:
            copied.recalculate_from_children()
        return copied

    def deep_copy(self) -> ScanNode:
        """递归深拷贝整棵子树，过滤器在"无过滤条件"时用此方法返回完整副本。"""
        return self.shallow_copy([child.deep_copy() for child in self.children])

    def recalculate_from_children(self) -> None:
        """
        根据现有 children 重新计算 size / file_count / dir_count。
        在 shallow_copy 替换了 children 列表后调用，保证统计数据一致。
        """
        if not self.is_dir:
            # 文件节点：统计数据固定，不依赖 children
            self.file_count = 1
            self.dir_count = 0
            return
        self.size = sum(child.size for child in self.children)
        self.file_count = sum(child.file_count if child.is_dir else 1 for child in self.children)
        self.dir_count = sum(child.dir_count + 1 if child.is_dir else 0 for child in self.children)

    # ── 遍历与序列化 ─────────────────────────────────────────

    def walk(self) -> list[ScanNode]:
        """前序遍历整棵子树，返回扁平列表（自身 + 所有子孙）。供 CSV 导出使用。"""
        nodes = [self]
        for child in self.children:
            nodes.extend(child.walk())
        return nodes

    def to_dict(self, include_children: bool = True) -> dict[str, Any]:
        """序列化为字典，include_children=True 时递归包含子树（用于 JSON 导出）。"""
        data: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "is_dir": self.is_dir,
            "size": self.size,
            "formatted_size": self.formatted_size,
            "modified_at": self.modified_at,
            "file_count": self.file_count,
            "dir_count": self.dir_count,
            "scan_error": self.scan_error,
            "skipped_reason": self.scan_error,
            "tag": self.tag,
        }
        if include_children:
            data["children"] = [child.to_dict(include_children=True) for child in self.children]
        return data
