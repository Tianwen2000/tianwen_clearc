from tianwen_clearc.models import ScanNode, format_size


def test_format_size() -> None:
    assert format_size(500) == "500 B"
    assert format_size(2048) == "2.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"


def test_scan_node_add_child_updates_counts() -> None:
    root = ScanNode(name="root", path="/root", is_dir=True)
    root.add_child(ScanNode(name="a.txt", path="/root/a.txt", is_dir=False, size=100, file_count=1))
    child_dir = ScanNode(name="logs", path="/root/logs", is_dir=True, size=200, file_count=2)
    root.add_child(child_dir)

    assert root.size == 300
    assert root.file_count == 3
    assert root.dir_count == 1

