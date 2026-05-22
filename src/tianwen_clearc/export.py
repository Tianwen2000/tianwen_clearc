from __future__ import annotations

import csv
import json
from pathlib import Path

from tianwen_clearc.models import ScanNode


def export_csv(root: ScanNode, destination: str | Path) -> None:
    destination = Path(destination)
    with destination.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "path",
                "name",
                "type",
                "size_bytes",
                "size",
                "files",
                "dirs",
                "modified_at",
                "skipped_reason",
            ]
        )
        for node in root.walk():
            writer.writerow(
                [
                    node.path,
                    node.name,
                    "dir" if node.is_dir else "file",
                    node.size,
                    node.formatted_size,
                    node.file_count,
                    node.dir_count,
                    node.modified_at or "",
                    node.scan_error or "",
                ]
            )


def export_json(root: ScanNode, destination: str | Path) -> None:
    destination = Path(destination)
    with destination.open("w", encoding="utf-8") as file:
        json.dump(root.to_dict(include_children=True), file, ensure_ascii=False, indent=2)
