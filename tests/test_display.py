from tianwen_clearc import display


def test_display_name_uses_windows_shell_fallback_for_broken_text(monkeypatch) -> None:
    monkeypatch.setattr(display.os, "name", "nt")
    monkeypatch.setattr(display, "_windows_shell_display_name", lambda path: "双文档")

    assert display.display_name_for_path("\ufffd\ufffd\ufffd", r"C:\Users\broken") == "双文档"


def test_display_name_keeps_normal_text_without_shell_lookup(monkeypatch) -> None:
    monkeypatch.setattr(display.os, "name", "nt")

    def fail_if_called(path: str) -> str:
        raise AssertionError(path)

    monkeypatch.setattr(display, "_windows_shell_display_name", fail_if_called)

    assert display.display_name_for_path("天河", r"C:\Users\Tianhe") == "天河"
