from tianwen_clearc.filters import FilterSpec, filter_tree, node_matches
from tianwen_clearc.models import ScanNode


def make_tree() -> ScanNode:
    root = ScanNode(name="root", path="/root", is_dir=True)
    root.add_child(
        ScanNode(name="photo.jpg", path="/root/photo.jpg", is_dir=False, size=300, file_count=1)
    )
    root.add_child(
        ScanNode(name="notes.txt", path="/root/notes.txt", is_dir=False, size=20, file_count=1)
    )
    logs = ScanNode(name="logs", path="/root/logs", is_dir=True)
    logs.add_child(
        ScanNode(name="app.log", path="/root/logs/app.log", is_dir=False, size=500, file_count=1)
    )
    root.add_child(logs)
    root.sort_children()
    return root


def test_node_matches_extension() -> None:
    node = ScanNode(name="app.log", path="/tmp/app.log", is_dir=False, size=100, file_count=1)

    assert node_matches(node, FilterSpec(extension="*.log"))
    assert not node_matches(node, FilterSpec(extension="*.jpg"))


def test_filter_tree_keeps_ancestors_for_matching_files() -> None:
    root = filter_tree(make_tree(), FilterSpec(extension="log"))

    assert root.size == 500
    assert root.children[0].name == "logs"
    assert root.children[0].children[0].name == "app.log"


def test_filter_tree_by_min_size() -> None:
    root = filter_tree(make_tree(), FilterSpec(min_size=250))
    names = {child.name for child in root.children}

    assert "photo.jpg" in names
    assert "notes.txt" not in names
