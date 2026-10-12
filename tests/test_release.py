import zipfile

from scripts.build_release import build_source_zip


def test_build_path_excludes_unrelated_native_libraries(monkeypatch):
    from scripts.build_release import build_environment
    monkeypatch.setenv("PATH", "C:/unrelated/poppler/Library/bin")
    monkeypatch.setenv("PYTHONPATH", "C:/unrelated/modules")
    env = build_environment()
    assert "unrelated" not in env["PATH"]
    assert "PYTHONPATH" not in env
    assert "System32" in env["PATH"]


def test_source_archive_excludes_user_recordings_keys_and_outputs(tmp_path):
    for name, content in {
        "app.py": "print('app')", "requirements.txt":"openai==3.29.0",
        "meeting_notes/ui.py":"# application", "tests/test_core.py":"# tests",
        ".env":"OPENAI_API_KEY=secret", "recording.wav":"private audio",
        "會議.docx":"private meeting", ".venv/secret.txt":"private",
        "meeting_notes/recording.mp3":"private audio", "qa/meeting.json":"private",
        "release/old.zip":"old release", "docs/private.meeting.json":"private",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    target = tmp_path / "source.zip"
    build_source_zip(tmp_path, target)
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist()) == {
            "MeetingNotes-source/app.py", "MeetingNotes-source/requirements.txt",
            "MeetingNotes-source/meeting_notes/ui.py", "MeetingNotes-source/tests/test_core.py"}
