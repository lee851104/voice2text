"""Build reproducible share packages from explicit source allowlists."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile


ROOT_FILES = {"app.py", "requirements.txt", "requirements-dev.txt", "requirements-lock.txt",
    "MeetingNotes.spec", "README.md", "使用說明.txt", "LICENSE.txt", ".gitignore", ".gitattributes", "pytest.ini"}
TREES = {"meeting_notes": {".py"}, "scripts": {".py", ".ps1"}, "tests": {".py"}, "docs": {".md"}}


def build_environment():
    """Do not collect incompatible DLLs from unrelated tools on the host PATH."""
    env = os.environ.copy()
    windows = Path(env.get("WINDIR", "C:/Windows"))
    env["PATH"] = os.pathsep.join(str(p) for p in (
        Path(sys.executable).parent, Path(sys.base_prefix), windows / "System32", windows))
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def source_files(root: Path):
    root = Path(root).resolve()
    for name in sorted(ROOT_FILES):
        path = root / name
        if path.is_file() and not path.is_symlink():
            yield path
    template = root / 'assets' / 'department-template.docx'
    if template.is_file() and not template.is_symlink():
        yield template
    for directory, extensions in TREES.items():
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and path.suffix in extensions and not path.is_symlink() and "__pycache__" not in path.parts:
                if root not in path.resolve().parents:
                    raise ValueError("Source path escaped project root")
                text = path.read_text(encoding="utf-8")
                if re.search(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{25,}", text):
                    raise ValueError(f"Possible credential in {path.name}; release refused")
                yield path


def build_source_zip(root, destination):
    root, destination = Path(root).resolve(), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_files(root):
            archive.write(path, "MeetingNotes-source/" + path.relative_to(root).as_posix())


def gather_licenses(destination):
    destination.mkdir(parents=True, exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("Python runtime license is required for distribution")
    (destination / "Python-LICENSE.txt").write_bytes(python_license.read_bytes())
    inventory = []
    for dist in sorted(metadata.distributions(), key=lambda d:d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        inventory.append({"name":name, "version":dist.version,
            "license":dist.metadata.get("License-Expression") or dist.metadata.get("License", "See package license files"),
            "source":dist.metadata.get_all("Project-URL") or [dist.metadata.get("Home-page", "")]})
        for file in dist.files or []:
            if any(word in file.name.lower() for word in ("license", "copying", "notice")) and file.suffix.lower() in {".txt",".md",".rst","", ".html"}:
                original = dist.locate_file(file)
                if original.is_file():
                    target = destination / name / str(file).replace("..", "_")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(original.read_bytes())
    (destination / "packages.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "NOTICE.txt").write_text(
        "Third-party software retains its own licenses. See included package license files and packages.json.\n"
        "Qt/PySide6 uses dynamically linked libraries under LGPLv3 or other applicable Qt licenses.\n"
        "You may replace the shared Qt libraries with compatible modified versions; reverse engineering for debugging such modifications is permitted.\n"
        "Qt/PySide source: https://download.qt.io/official_releases/QtForPython/ and https://download.qt.io/official_releases/qt/\n"
        "PyAV source: https://github.com/PyAV-Org/PyAV ; wheel build recipes: https://github.com/PyAV-Org/pyav-wheels\n"
        "FFmpeg source: https://ffmpeg.org/download.html ; linked component notices are included with PyAV and Qt.\n"
        "Application source and build instructions are included in the source directory.\n", encoding="utf-8")


def build(root, source_only=False):
    root = Path(root).resolve()
    release = root / "release"
    release.mkdir(exist_ok=True)
    source_zip = release / "MeetingNotes-source.zip"
    build_source_zip(root, source_zip)
    outputs = [source_zip]
    if not source_only:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "MeetingNotes.spec"],
            cwd=root, env=build_environment(), check=True)
        package = root / "dist" / "MeetingNotes"
        if not (package / "MeetingNotes.exe").is_file():
            raise RuntimeError("Executable missing after build")
        gather_licenses(package / "THIRD_PARTY_LICENSES")
        for name in ("使用說明.txt", "LICENSE.txt"):
            (package / name).write_bytes((root / name).read_bytes())
        portable = release / "MeetingNotes-Windows-x64.zip"
        with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    archive.write(path, "MeetingNotes/" + path.relative_to(package).as_posix())
            for path in source_files(root):
                archive.write(path, "MeetingNotes/source/" + path.relative_to(root).as_posix())
        outputs.append(portable)
    lines = [hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name for path in outputs]
    (release / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for path in outputs:
        print(f"{path.name}: {path.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[1], args.source_only)
