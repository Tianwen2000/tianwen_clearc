from __future__ import annotations

from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget


class StableTreeWidget(QTreeWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.horizontalScrollBar().valueChanged.connect(self.reset_horizontal_scroll)

    def scrollTo(  # noqa: N802
        self,
        index: QModelIndex,
        hint: QAbstractItemView.ScrollHint = QAbstractItemView.ScrollHint.EnsureVisible,
    ) -> None:
        return

    def reset_horizontal_scroll(self) -> None:
        bar = self.horizontalScrollBar()
        if bar.value() != 0:
            bar.setValue(0)
