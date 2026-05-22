from PySide6.QtWidgets import QApplication

from tianwen_clearc.main_window import MainWindow, missing_path_message
from tianwen_clearc.scanner import ScanProgress, SkippedPath


def app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_missing_path_message_explains_what_to_do() -> None:
    message = missing_path_message("/tmp/deleted-folder")

    assert "不存在" in message
    assert "删除" in message
    assert "/tmp/deleted-folder" in message
    assert "重新选择" in message


def test_scan_progress_uses_skipped_language() -> None:
    app()
    window = MainWindow()

    window.on_scan_progress(
        ScanProgress(
            scanned_files=3,
            scanned_dirs=2,
            scanned_bytes=1024,
            skipped_count=1,
            skipped_paths=(SkippedPath("/private", "无权限：denied"),),
        )
    )

    assert "无权限跳过 1 项" in window.status.currentMessage()
    assert window.skipped_details_button.isEnabled()
    assert window.skipped_details_button.text() == "无权限跳过 1 项"
