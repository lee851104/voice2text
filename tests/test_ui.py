import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from meeting_notes.ui import MainWindow
from meeting_notes.models import Project, Minutes, Evidence


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def project():
    p = Project(title="設計週會", date="2026-10-12")
    p.add_chunk({"segments":[{"start":1,"end":3,"speaker":"A","text":"原本的內容。"}]},0,0)
    p.transcription_complete = True
    p.minutes = Minutes(summary=[Evidence(text="原本摘要", sources=["s0-0"])])
    return p


def test_editing_transcript_invalidates_preview_and_keeps_word_export(app, tmp_path):
    window = MainWindow(data_root=tmp_path)
    window.set_project(project())
    assert "原本摘要" in window.preview.toPlainText()
    window.transcript.item(0, 2).setText("修改後的內容。")
    assert window.project.minutes is None
    assert "原本摘要" not in window.preview.toPlainText()
    assert window.export_button.isEnabled()
    assert window.project.segments[0].original_text == "原本的內容。"
    window.close()


@pytest.mark.parametrize("operation", ["relink", "start_job", "close"])
def test_lifecycle_clears_pending_playback(app, tmp_path, monkeypatch, operation):
    from PySide6.QtCore import QObject, Signal
    from meeting_notes import ui

    class IdleJob(QObject):
        progress = Signal(str, int)
        completed = Signal(object)
        failed = Signal(str, object)
        finished = Signal()

        def __init__(self, *args):
            super().__init__()

        def start(self):
            pass

    window = MainWindow(data_root=tmp_path)
    window.set_project(project())
    window.pending_seek = (1000, 2000)
    monkeypatch.setattr(ui, "MeetingJob", IdleJob)
    monkeypatch.setattr(ui.QFileDialog, "getOpenFileName", lambda *a: (str(tmp_path / "new.wav"), ""))
    if operation == "relink":
        window.relink_audio()
    elif operation == "start_job":
        window.key_input.setText("offline-test")
        window.start_job("summarize")
        window.job_finished()
    else:
        window.close()
    assert window.pending_seek is None
    window.start_pending_playback()
    window.close()


def test_metadata_edits_invalidate_summary_and_api_key_is_not_persisted(app, tmp_path):
    window = MainWindow(data_root=tmp_path)
    window.set_project(project())
    window.key_input.setText("test-secret-do-not-save")
    window.title_input.setText("新的名稱")
    assert window.project.title == "新的名稱"
    assert window.project.minutes is None
    window.autosave()
    for path in tmp_path.rglob("*.json"):
        assert "test-secret-do-not-save" not in path.read_text(encoding="utf-8")
    window.close()


def test_busy_state_prevents_editing_inputs_and_export(app, tmp_path):
    window = MainWindow(data_root=tmp_path)
    window.set_project(project())
    window.set_busy(True)
    assert not window.transcript.isEnabled()
    assert not window.export_button.isEnabled()
    assert not window.title_input.isEnabled()
    window.set_busy(False)
    assert window.transcript.isEnabled()
    assert window.export_button.isEnabled()
    window.close()


def test_rejected_request_keeps_copyable_details_without_overfilling_status(app, tmp_path):
    window = MainWindow(data_root=tmp_path)
    details = "OpenAI 未接受此請求。\n回應狀態碼：400\n服務回覆：Audio too long"
    window.job_failed(details, project())
    assert window.status.text() == "OpenAI 未接受此請求。"
    assert window.last_error == details
    assert not window.error_button.isHidden()
    assert window.error_button.isEnabled()
    window.close()


def test_reimport_of_same_recording_keeps_previous_corrected_session(app, tmp_path):
    from meeting_notes.storage import load_project
    window = MainWindow(data_root=tmp_path)
    original = project()
    original.audio_hash = "a" * 64
    original.edit_segment("s0-0", "已經校對的文字")
    window.set_project(original)
    window.autosave()
    reimported = project()
    reimported.audio_hash = "a" * 64
    window.set_project(reimported)
    window.autosave()
    saved = list((tmp_path / "sessions").glob("*.json"))
    assert len(saved) == 2
    restored = load_project(tmp_path / "sessions" / f"{original.session_id}.json")
    assert restored.segments[0].text == "已經校對的文字"
    window.close()


def test_playback_waits_for_media_loading_before_seeking(app, tmp_path):
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QMediaPlayer

    class LoadingPlayer:
        def __init__(self):
            self.url = QUrl()
            self.state = QMediaPlayer.MediaStatus.NoMedia
            self.positions = []
            self.playing = False

        def source(self):
            return self.url

        def setSource(self, url):
            self.url, self.state = url, QMediaPlayer.MediaStatus.LoadingMedia

        def mediaStatus(self):
            return self.state

        def isSeekable(self):
            return self.state == QMediaPlayer.MediaStatus.LoadedMedia

        def setPosition(self, position):
            assert self.state != QMediaPlayer.MediaStatus.LoadingMedia
            self.positions.append(position)

        def play(self):
            self.playing = True

        def stop(self):
            self.playing = False

    window = MainWindow(data_root=tmp_path)
    p = project()
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fixture")
    p.source_path = str(audio)
    window.set_project(p)
    window.transcript.selectRow(0)
    player = LoadingPlayer()
    window.player = player
    window.play_selected()
    assert not player.playing
    assert player.positions == []
    player.state = QMediaPlayer.MediaStatus.LoadedMedia
    window.media_status_changed(player.state)
    assert player.positions == [1000]
    assert player.playing
    window.close()
