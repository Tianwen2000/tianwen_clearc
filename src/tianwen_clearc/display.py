from __future__ import annotations

import ctypes
import os
import unicodedata
from functools import lru_cache

REPLACEMENT_CHAR = "\ufffd"


def display_name_for_path(name: str, path: str) -> str:
    """
    Return a UI-safe display name for a filesystem item.

    On Windows, a few special folders or legacy-created names may arrive with
    replacement characters already in the Python string. When that happens,
    ask the Windows Shell for the Explorer display name as a fallback.
    """
    text = _normalize_text(name or path)
    if os.name == "nt" and _looks_broken(text):
        shell_name = _windows_shell_display_name(path)
        if shell_name and not _looks_broken(shell_name):
            return shell_name
    return text


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _looks_broken(text: str) -> bool:
    return REPLACEMENT_CHAR in text


@lru_cache(maxsize=4096)
def _windows_shell_display_name(path: str) -> str:
    if os.name != "nt":
        return ""

    class SHFILEINFO(ctypes.Structure):
        _fields_ = [
            ("hIcon", ctypes.c_void_p),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", ctypes.c_ulong),
            ("szDisplayName", ctypes.c_wchar * 260),
            ("szTypeName", ctypes.c_wchar * 80),
        ]

    shgfi_displayname = 0x000000200
    info = SHFILEINFO()
    result = ctypes.windll.shell32.SHGetFileInfoW(
        str(path),
        0,
        ctypes.byref(info),
        ctypes.sizeof(info),
        shgfi_displayname,
    )
    if not result:
        return ""
    return _normalize_text(info.szDisplayName)
