from PySide6.QtWidgets import QApplication

from tianwen_clearc.main_window import MainWindow
from tianwen_clearc.models import ScanNode


def app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_deep_tree_item_lazy_loads_and_expands_on_click() -> None:
    app()
    window = MainWindow()
    root = ScanNode(name="root", path="/root", is_dir=True)
    current = root
    for depth in range(6):
        child = ScanNode(name=f"level-{depth}", path=f"/root/level-{depth}", is_dir=True)
        current.add_child(child)
        current = child

    window.populate_tree(root)

    item = window.tree.topLevelItem(0)
    for _ in range(4):
        item = item.child(0)

    assert item.childCount() == 1
    assert window.has_tree_placeholder(item)

    window.show_tree_item_details(item, 0)

    assert item.childCount() == 1
    assert not window.has_tree_placeholder(item)
    assert item.isExpanded()


def test_tree_click_resets_horizontal_scroll() -> None:
    app()
    window = MainWindow()
    root = ScanNode(name="root", path="/root", is_dir=True)
    child = ScanNode(name="very-long-child-name", path="/root/very-long-child-name", is_dir=True)
    root.add_child(child)

    window.populate_tree(root)
    item = window.tree.topLevelItem(0).child(0)
    window.tree.horizontalScrollBar().setValue(99)
    window.show_tree_item_details(item, 0)

    assert window.tree.horizontalScrollBar().value() == 0


def test_tree_click_restores_name_column_width() -> None:
    app()
    window = MainWindow()
    root = ScanNode(name="root", path="/root", is_dir=True)
    root.add_child(
        ScanNode(
            name="deep-file-with-a-long-name.py",
            path="/root/deep-file-with-a-long-name.py",
            is_dir=False,
            size=10,
        )
    )

    window.populate_tree(root)
    item = window.tree.topLevelItem(0).child(0)
    expected_width = window.tree.columnWidth(0)
    window.tree.setColumnWidth(0, expected_width + 500)
    window.tree.horizontalScrollBar().setValue(200)
    window.show_tree_item_details(item, 0)

    assert window.tree.columnWidth(0) == expected_width
    assert window.tree.horizontalScrollBar().value() == 0
