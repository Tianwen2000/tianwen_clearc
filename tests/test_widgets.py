from PySide6.QtWidgets import QApplication

from tianwen_clearc.models import ScanNode
from tianwen_clearc.widgets import TreemapWidget


def app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_treemap_keeps_tiny_items_visible() -> None:
    app()
    root = ScanNode(name="PycharmProjects", path="/PycharmProjects", is_dir=True)
    for name, size in [
        ("pipenv_project", 4_800_000_000),
        ("Virtualenv_project", 2_900_000_000),
        ("Tianwen", 1_023_700_000),
        ("qixiang_tools", 588_300_000),
        (".DS_Store", 6_000),
        (".idea", 4_600),
    ]:
        root.add_child(ScanNode(name=name, path=f"/PycharmProjects/{name}", is_dir=True, size=size))

    widget = TreemapWidget()
    widget.resize(1000, 600)
    widget.set_root(root)

    names = {item.value.name for item in widget._items}
    tiny_items = [item for item in widget._items if item.value.name in {".DS_Store", ".idea"}]

    assert names == {
        "pipenv_project",
        "Virtualenv_project",
        "Tianwen",
        "qixiang_tools",
        ".DS_Store",
        ".idea",
    }
    assert all(item.rect.area >= 18_000 for item in tiny_items)


def test_treemap_previews_nested_children() -> None:
    app()
    root = ScanNode(name="root", path="/root", is_dir=True)
    projects = ScanNode(
        name="projects",
        path="/root/projects",
        is_dir=True,
        size=8_000_000_000,
    )
    projects.add_child(
        ScanNode(
            name="math_maker",
            path="/root/projects/math_maker",
            is_dir=True,
            size=3_600_000_000,
        )
    )
    projects.add_child(
        ScanNode(
            name="tianwen_clearC",
            path="/root/projects/tianwen_clearC",
            is_dir=True,
            size=1_200_000_000,
        )
    )
    root.add_child(projects)
    root.add_child(
        ScanNode(name="Downloads", path="/root/Downloads", is_dir=True, size=1_000_000_000)
    )

    widget = TreemapWidget()
    widget.resize(1000, 600)
    widget.set_root(root)

    names = {item.value.name for item in widget._items}

    assert {"projects", "Downloads", "math_maker", "tianwen_clearC"} <= names
