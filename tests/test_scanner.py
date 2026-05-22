from pathlib import Path

from tianwen_clearc.scanner import DirectoryScanner, scan_path


def test_scan_path_counts_files_and_sizes(tmp_path) -> None:
    (tmp_path / "a.txt").write_bytes(b"hello")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.log").write_bytes(b"0123456789")

    root = scan_path(tmp_path)

    assert root.size == 15
    assert root.file_count == 2
    assert root.dir_count == 1
    assert [child.name for child in root.children] == ["nested", "a.txt"]


def test_scan_path_skips_symlink(tmp_path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("target", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        return

    root = scan_path(tmp_path)

    assert root.file_count == 1
    assert all(child.name != "link.txt" for child in root.children)


def test_disappearing_file_is_silently_ignored(monkeypatch) -> None:
    scanner = DirectoryScanner()

    class Entry:
        path = "/tmp/gone.txt"

    def raise_file_not_found(
        path: Path,
        cancel_event,
        on_progress,
    ):
        raise FileNotFoundError(path)

    monkeypatch.setattr(scanner, "_scan_path", raise_file_not_found)

    assert scanner._scan_entry(Entry(), None, None) is None
    assert scanner.progress.skipped_count == 0
    assert scanner.skipped_paths == []


def test_permission_error_records_skipped_path() -> None:
    scanner = DirectoryScanner()
    progress_updates = []

    scanner._record_skip(
        Path("/private"),
        PermissionError("denied"),
        progress_updates.append,
        force=True,
    )

    assert scanner.progress.skipped_count == 1
    assert scanner.skipped_paths[0].path == "/private"
    assert "无权限" in scanner.skipped_paths[0].reason
    assert progress_updates[-1].skipped_count == 1
