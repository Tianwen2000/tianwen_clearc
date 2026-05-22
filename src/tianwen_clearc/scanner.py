from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tianwen_clearc.models import ScanNode


class ScanCancelled(RuntimeError):
    """扫描被主动取消时抛出，供调用方区分"取消"与"出错"两种终止方式。"""


@dataclass(frozen=True, slots=True)
class SkippedPath:
    """扫描时被跳过的路径及原因，用于 UI 展示详情。"""
    path: str
    reason: str


@dataclass(slots=True)
class ScanProgress:
    """扫描进度快照，每次进度回调时传递一份新实例（不修改旧实例，线程安全）。"""
    scanned_files: int = 0
    scanned_dirs: int = 0
    scanned_bytes: int = 0
    skipped_count: int = 0
    skipped_paths: tuple[SkippedPath, ...] = ()
    current_path: str = ""  # 当前正在扫描的路径，用于状态栏显示
    done: bool = False

    @property
    def errors(self) -> int:
        """兼容旧调用；UI 新文案使用 skipped_count。"""
        return self.skipped_count


# 进度回调的类型别名，接收一个 ScanProgress 快照
ProgressCallback = Callable[[ScanProgress], None]


class DirectoryScanner:
    """
    递归目录扫描器，构建 ScanNode 树。

    设计要点：
    - 不直接使用线程，由调用方（ScanWorker）在 QThread 中调用 scan()。
    - 通过 threading.Event 实现取消：扫描循环每处理一个条目前检查 cancel_event。
    - 进度回调有节流（progress_interval），避免高频 UI 刷新造成卡顿。
    - 遇到权限错误或 OSError 时记录错误但继续扫描，不中断整棵树。
    """

    def __init__(
        self,
        *,
        follow_symlinks: bool = False,
        progress_interval: float = 0.15,    # 进度回调最小间隔（秒）
    ) -> None:
        self.follow_symlinks = follow_symlinks
        self.progress_interval = progress_interval
        self.progress = ScanProgress()
        self.skipped_paths: list[SkippedPath] = []
        self._last_emit = 0.0   # 上次发送进度的时间戳（monotonic）

    def scan(
        self,
        root_path: str | os.PathLike[str],
        *,
        cancel_event: threading.Event | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ScanNode:
        """
        扫描入口：解析路径、启动递归扫描、排序结果后返回根节点。
        扫描完成后强制发送一次 done=True 的进度通知，让 UI 知道扫描结束。
        """
        path = Path(root_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(str(path))

        self.progress = ScanProgress(current_path=str(path))
        self.skipped_paths = []
        node = self._scan_path(path, cancel_event, on_progress)
        node.sort_children()    # 按大小降序排列，使 treemap 左上角显示最大块
        self.progress.done = True
        self.progress.current_path = str(path)
        self._emit(on_progress, force=True)
        return node

    def _scan_path(
        self,
        path: Path,
        cancel_event: threading.Event | None,
        on_progress: ProgressCallback | None,
    ) -> ScanNode:
        """
        扫描单个路径（文件或目录）并返回对应节点。

        - 取消检查放在每次递归最开头，保证响应及时。
        - stat 失败时返回带 scan_error 的空节点，保留路径信息，不丢弃。
        - 目录读取失败（PermissionError 等）记录在节点的 scan_error 上，
          已扫描的子节点仍然保留。
        """
        if cancel_event and cancel_event.is_set():
            raise ScanCancelled("Scan cancelled")

        # 获取文件元数据；follow_symlinks=False 时用 lstat 避免跟随符号链接
        try:
            stat_result = path.stat() if self.follow_symlinks else path.lstat()
            modified_at = stat_result.st_mtime
        except FileNotFoundError:
            raise
        except OSError as exc:
            self._record_skip(path, exc, on_progress)
            return ScanNode(
                name=path.name or str(path),
                path=str(path),
                is_dir=self._safe_is_dir(path),
                scan_error=str(exc),
            )

        # 判断是否为目录：follow_symlinks=False 时符号链接不视为目录
        is_dir = path.is_dir() if self.follow_symlinks else path.is_dir() and not path.is_symlink()

        if not is_dir:
            # 文件节点：直接记录大小并返回
            size = stat_result.st_size
            self.progress.scanned_files += 1
            self.progress.scanned_bytes += size
            self.progress.current_path = str(path)
            self._emit(on_progress)
            return ScanNode(
                name=path.name or str(path),
                path=str(path),
                is_dir=False,
                size=size,
                modified_at=modified_at,
                file_count=1,
            )

        # 目录节点：先建空节点，再递归扫描子条目并 add_child 累加
        node = ScanNode(
            name=path.name or str(path),
            path=str(path),
            is_dir=True,
            modified_at=modified_at,
        )
        self.progress.scanned_dirs += 1
        self.progress.current_path = str(path)
        self._emit(on_progress)

        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if cancel_event and cancel_event.is_set():
                        raise ScanCancelled("Scan cancelled")
                    # 跳过符号链接（除非 follow_symlinks=True），防止循环引用
                    if entry.is_symlink() and not self.follow_symlinks:
                        continue
                    child = self._scan_entry(entry, cancel_event, on_progress)
                    if child is not None:
                        node.add_child(child)
        except PermissionError as exc:
            # 目录无读权限：记录跳过详情，已有子节点不丢弃
            node.scan_error = str(exc)
            self._record_skip(path, exc, on_progress, force=True)
        except FileNotFoundError:
            raise
        except OSError as exc:
            node.scan_error = str(exc)
            self._record_skip(path, exc, on_progress, force=True)

        return node

    def _record_skip(
        self,
        path: Path,
        exc: OSError,
        on_progress: ProgressCallback | None,
        *,
        force: bool = False,
    ) -> None:
        """记录一次不可访问路径；这类情况显示为“无权限跳过”。"""
        self.skipped_paths.append(SkippedPath(str(path), self._skip_reason(exc)))
        self.progress.skipped_count = len(self.skipped_paths)
        self.progress.skipped_paths = tuple(self.skipped_paths)
        self.progress.current_path = str(path)
        self._emit(on_progress, force=force)

    def _skip_reason(self, exc: OSError) -> str:
        if isinstance(exc, PermissionError):
            return f"无权限：{exc}"
        return f"无法读取：{exc}"

    def _safe_is_dir(self, path: Path) -> bool:
        try:
            return path.is_dir()
        except OSError:
            return False

    def _scan_entry(
        self,
        entry: os.DirEntry[str],
        cancel_event: threading.Event | None,
        on_progress: ProgressCallback | None,
    ) -> ScanNode | None:
        """
        对单个 DirEntry 进行扫描，屏蔽 FileNotFoundError。
        在 scandir 迭代过程中文件被删除时会触发此错误，直接跳过该条目。
        """
        try:
            return self._scan_path(Path(entry.path), cancel_event, on_progress)
        except FileNotFoundError:
            # 临时文件可能在扫描中途消失；这不是权限问题，不计入跳过详情。
            return None

    def _emit(self, on_progress: ProgressCallback | None, *, force: bool = False) -> None:
        """
        节流发送进度回调。
        正常情况下每隔 progress_interval 秒才真正调用一次回调，
        force=True 时（扫描完成、遇到错误）跳过节流立即发送。
        每次发送都是新的 ScanProgress 实例（值拷贝），防止 UI 线程读到正在修改的数据。
        """
        if not on_progress:
            return
        now = time.monotonic()
        if force or now - self._last_emit >= self.progress_interval:
            self._last_emit = now
            on_progress(
                ScanProgress(
                    scanned_files=self.progress.scanned_files,
                    scanned_dirs=self.progress.scanned_dirs,
                    scanned_bytes=self.progress.scanned_bytes,
                    skipped_count=self.progress.skipped_count,
                    skipped_paths=tuple(self.skipped_paths),
                    current_path=self.progress.current_path,
                    done=self.progress.done,
                )
            )


def scan_path(
    root_path: str | os.PathLike[str],
    *,
    cancel_event: threading.Event | None = None,
    on_progress: ProgressCallback | None = None,
    follow_symlinks: bool = False,
) -> ScanNode:
    """便捷函数：一次性创建 DirectoryScanner 并执行扫描，无需手动实例化。"""
    scanner = DirectoryScanner(follow_symlinks=follow_symlinks)
    return scanner.scan(root_path, cancel_event=cancel_event, on_progress=on_progress)
