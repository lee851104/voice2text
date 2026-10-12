from __future__ import annotations

import os
from pathlib import Path
import tempfile

from .models import Project


def data_directory() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    result = base / "MeetingNotes"
    result.mkdir(parents=True, exist_ok=True)
    return result


def save_project(project: Project, path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".meeting-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(project.model_dump_json(indent=2))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_project(path: Path) -> Project:
    path = Path(path)
    if path.stat().st_size > 50_000_000:
        raise ValueError("會議專案檔過大")
    return Project.model_validate_json(path.read_text(encoding="utf-8"))
