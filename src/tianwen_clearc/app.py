from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from tianwen_clearc.branding import APP_DISPLAY_NAME
from tianwen_clearc.main_window import MainWindow


def configure_font(app: QApplication) -> None:
    """Use a Windows font with reliable CJK coverage for item views and custom painting."""
    if sys.platform != "win32":
        return
    available_families = set(QFontDatabase.families())
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "SimSun", "Segoe UI"):
        if family in available_families:
            app.setFont(QFont(family, 9))
            return


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    configure_font(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
