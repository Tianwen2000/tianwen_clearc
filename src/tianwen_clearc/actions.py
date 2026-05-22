from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


def open_path(path: str) -> None:
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if system == "Darwin":
        subprocess.Popen(["open", path])
        return
    subprocess.Popen(["xdg-open", path])


def reveal_in_file_manager(path: str) -> None:
    target = Path(path)
    system = platform.system()
    if system == "Windows":
        subprocess.Popen(["explorer", f"/select,{target}"])
        return
    if system == "Darwin":
        subprocess.Popen(["open", "-R", str(target)])
        return
    open_path(str(target.parent if target.is_file() else target))

