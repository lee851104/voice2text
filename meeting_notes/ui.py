from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QDate, QUrl, Signal, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QToolButton, QLineEdit, QDateEdit, QFrame, QFileDialog, QTabWidget,
    QSplitter, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QPlainTextEdit, QProgressBar, QMessageBox, QInputDialog,
    QStyledItemDelegate, QComboBox, QAbstractItemView)

from .models import Project, timestamp
from .storage import data_directory, load_project, save_project
from .export import export_docx
from .workers import MeetingJob
from .theme import STYLE
from . import __version__

SUPPORTED = {".mp3", ".m4a", ".wav", ".mp4", ".webm", ".mpeg", ".mpga", ".ogg", ".flac", ".aac"}


def label(text, name=None):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName("primary")
    item.clicked.connect(callback)
    return item


class SpeakerDelegate(QStyledItemDelegate):
    chosen = Signal(int, str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        for key, name in self.window.project.speakers.items():
            editor.addItem(name, key)
        return editor

    def setEditorData(self, editor, index):
        editor.setCurrentIndex(editor.findData(self.window.project.segments[index.row()].speaker))

    def setModelData(self, editor, model, index):
        self.chosen.emit(index.row(), editor.currentData())


class MainWindow(QMainWindow):
    def __init__(self, data_root=None):
        super().__init__()
        self.root = Path(data_root) if data_root else data_directory()
        self.project = Project(date=QDate.currentDate().toString("yyyy-MM-dd"))
        self.job = None
        self.busy = False
        self.close_pending = False
        self.loading = False
        self.segment_end = None
        self.pending_seek = None
        self.last_error = ""
        self.setWindowTitle(f"會議筆記 Meeting Notes {__version__}")
        self.resize(1160, 880)
        self.setMinimumSize(980, 740)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.play_position)
        self.player.mediaStatusChanged.connect(self.media_status_changed)
        self.player.seekableChanged.connect(lambda *_: self.start_pending_playback())
        self.player.errorOccurred.connect(lambda *_: self.status.setText("音檔無法播放，請重新連結原始錄音，或確認檔案格式。"))
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.autosave)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(28, 22, 28, 20)
        outer.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(label("會議筆記", "brand"))
        head.addWidget(label("MEETING NOTES", "muted"))
        head.addStretch()
        head.addWidget(label("本機工作空間", "badge"))
        outer.addLayout(head)
        outer.addWidget(label("把錄音整理成可追溯、可編輯的會議紀錄。", "muted"))

        card = QFrame()
        card.setObjectName("card")
        setup = QVBoxLayout(card)
        setup.setContentsMargins(18, 14, 18, 14)
        form = QHBoxLayout()
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("會議名稱，例如：產品進度週會")
        self.title_input.textChanged.connect(self.metadata_changed)
        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        self.date_input.dateChanged.connect(self.metadata_changed)
        form.addWidget(self.title_input, 1)
        form.addWidget(self.date_input)
        setup.addLayout(form)
        drop = QFrame()
        drop.setObjectName("drop")
        drop_layout = QHBoxLayout(drop)
        drop_layout.setContentsMargins(14, 12, 14, 12)
        self.file_label = label("將錄音拖曳到視窗，或選擇檔案\nMP3 · M4A · WAV · MP4 · WebM", "muted")
        self.file_label.setWordWrap(True)
        drop_layout.addWidget(self.file_label, 1)
        self.choose_button = button("選擇錄音", self.choose_file)
        drop_layout.addWidget(self.choose_button)
        setup.addWidget(drop)
        settings_row = QHBoxLayout()
        self.settings_toggle = QToolButton()
        self.settings_toggle.setText("連線設定")
        self.settings_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.settings_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.toggled.connect(self.toggle_settings)
        settings_row.addWidget(self.settings_toggle)
        settings_row.addStretch()
        settings_row.addWidget(label("錄音與文字將傳至 OpenAI，費用由你的金鑰帳戶支付。", "muted"))
        setup.addLayout(settings_row)
        self.settings_panel = QWidget()
        settings = QHBoxLayout(self.settings_panel)
        settings.setContentsMargins(0, 0, 0, 0)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("OpenAI API Key（應用程式介面金鑰），關閉程式後清除")
        self.key_input.textChanged.connect(self.refresh_buttons)
        self.model_input = QLineEdit("gpt-4.1-mini")
        self.model_input.setMaximumWidth(175)
        self.model_input.setToolTip("整理摘要使用的模型；語音辨識固定使用 gpt-4o-transcribe-diarize。")
        settings.addWidget(self.key_input, 1)
        settings.addWidget(label("摘要模型", "muted"))
        settings.addWidget(self.model_input)
        self.settings_panel.hide()
        setup.addWidget(self.settings_panel)
        outer.addWidget(card)

        operations = QHBoxLayout()
        self.transcribe_button = button("1　開始轉錄", lambda: self.start_job("transcribe"), True)
        self.summarize_button = button("2　整理會議紀錄", lambda: self.start_job("summarize"))
        self.cancel_button = button("取消", self.cancel_job)
        self.cancel_button.hide()
        operations.addWidget(self.transcribe_button)
        operations.addWidget(self.summarize_button)
        operations.addWidget(self.cancel_button)
        operations.addStretch()
        self.count_label = label("尚未匯入錄音", "muted")
        operations.addWidget(self.count_label)
        outer.addLayout(operations)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        outer.addWidget(self.progress)
        self.status = label("先匯入錄音並輸入金鑰。轉錄後可校對姓名與發言。", "muted")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, 1)
        self.error_button = button("查看錯誤", self.show_error)
        self.error_button.hide()
        status_row.addWidget(self.error_button)
        outer.addLayout(status_row)
        self.tabs = QTabWidget()
        review = QWidget()
        review_layout = QVBoxLayout(review)
        review_layout.setContentsMargins(0, 10, 0, 0)
        split = QSplitter()
        speaker_panel = QWidget()
        speakers_layout = QVBoxLayout(speaker_panel)
        speakers_layout.setContentsMargins(0, 0, 6, 0)
        speakers_layout.addWidget(label("說話者 · 雙擊修改姓名", "muted"))
        self.speaker_list = QListWidget()
        self.speaker_list.itemChanged.connect(self.speaker_renamed)
        speakers_layout.addWidget(self.speaker_list)
        speaker_actions = QHBoxLayout()
        self.add_speaker_button = button("新增", self.add_speaker)
        self.merge_button = button("合併人物", self.merge_speaker)
        speaker_actions.addWidget(self.add_speaker_button)
        speaker_actions.addWidget(self.merge_button)
        speakers_layout.addLayout(speaker_actions)
        split.addWidget(speaker_panel)
        self.transcript = QTableWidget(0, 3)
        self.transcript.setHorizontalHeaderLabels(["錄音時間", "說話者", "發言內容（雙擊編輯）"])
        self.transcript.verticalHeader().hide()
        self.transcript.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.transcript.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.transcript.setAlternatingRowColors(True)
        self.transcript.setShowGrid(False)
        self.transcript.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.transcript.setColumnWidth(0, 98)
        self.transcript.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.transcript.setColumnWidth(1, 170)
        self.transcript.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.transcript.itemChanged.connect(self.transcript_changed)
        self.delegate = SpeakerDelegate(self)
        self.delegate.chosen.connect(self.speaker_reassigned)
        self.transcript.setItemDelegateForColumn(1, self.delegate)
        split.addWidget(self.transcript)
        split.setSizes([235, 800])
        review_layout.addWidget(split, 1)
        playback = QHBoxLayout()
        self.play_button = button("試聽選取段落", self.play_selected)
        self.stop_button = button("停止", self.stop_playback)
        self.relink_button = button("重新連結錄音", self.relink_audio)
        playback.addWidget(self.play_button)
        playback.addWidget(self.stop_button)
        playback.addWidget(self.relink_button)
        playback.addStretch()
        playback.addWidget(label("跨錄音分段的人物，請試聽確認後再合併。", "muted"))
        review_layout.addLayout(playback)
        self.tabs.addTab(review, "校對逐字稿")
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("確認說話者與逐字稿後，按「整理會議紀錄」。\n也可以直接匯出逐字稿。")
        self.tabs.addTab(self.preview, "會議紀錄預覽")
        outer.addWidget(self.tabs, 1)
        footer = QHBoxLayout()
        self.open_button = button("開啟專案", self.open_project)
        self.save_button = button("儲存專案", self.save_as)
        self.recover_button = button("恢復上次工作", self.recover)
        footer.addWidget(self.open_button)
        footer.addWidget(self.save_button)
        footer.addWidget(self.recover_button)
        footer.addStretch()
        self.export_button = button("匯出 Word", self.export_word, True)
        footer.addWidget(self.export_button)
        outer.addLayout(footer)
        self.refresh_buttons()

    def toggle_settings(self, opened):
        self.settings_panel.setVisible(opened)
        self.settings_toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)

    def dragEnterEvent(self, event):
        if not self.busy and event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() in SUPPORTED:
                event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.busy:
            self.select_audio(Path(event.mimeData().urls()[0].toLocalFile()))
            event.acceptProposedAction()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "選擇會議錄音", "", "錄音檔 (*.mp3 *.m4a *.wav *.mp4 *.webm *.mpeg *.mpga *.ogg *.flac *.aac)")
        if path:
            self.select_audio(Path(path))

    def select_audio(self, path):
        if not path.is_file():
            self.status.setText("找不到錄音檔。")
            return
        if self.project.segments:
            answer = QMessageBox.question(self, "建立新會議", "目前校對內容會自動備份。要匯入另一場錄音嗎？")
            if answer != QMessageBox.StandardButton.Yes:
                return
            if not self.autosave():
                return
        self.stop_playback()
        project = Project(title=path.stem, date=self.date_input.date().toString("yyyy-MM-dd"), source_path=str(path.resolve()))
        self.set_project(project)
        self.settings_toggle.setChecked(not bool(self.key_input.text().strip()))
        self.status.setText("錄音已就緒。按「開始轉錄」將音訊送至 OpenAI。")

    def relink_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "連結此份逐字稿的原始錄音", "", "錄音檔 (*.mp3 *.m4a *.wav *.mp4 *.webm *.mpeg *.mpga *.ogg *.flac *.aac)")
        if path:
            self.stop_playback()
            self.project.source_path = path
            self.file_label.setText(Path(path).name)
            self.file_label.setToolTip(path)
            self.save_timer.start(500)
            self.refresh_buttons()

    def metadata_changed(self, *_):
        if self.loading:
            return
        self.project.title = self.title_input.text().strip() or "未命名會議"
        self.project.date = self.date_input.date().toString("yyyy-MM-dd")
        self.changed()

    def set_project(self, project):
        self.stop_playback()
        self.loading = True
        self.project = project
        self.title_input.setText(project.title if project.title != "未命名會議" else "")
        date = QDate.fromString(project.date, "yyyy-MM-dd")
        if date.isValid():
            self.date_input.setDate(date)
        self.file_label.setText(Path(project.source_path).name if project.source_path else "未連結錄音，可使用下方按鈕重新連結")
        self.file_label.setToolTip(project.source_path)
        self.speaker_list.clear()
        for key, name in project.speakers.items():
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.speaker_list.addItem(item)
        self.transcript.setRowCount(len(project.segments))
        for row, segment in enumerate(project.segments):
            time_item = QTableWidgetItem(timestamp(segment.start))
            time_item.setFlags(time_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            time_item.setToolTip(f"{timestamp(segment.start)} – {timestamp(segment.end)}")
            self.transcript.setItem(row, 0, time_item)
            self.transcript.setItem(row, 1, QTableWidgetItem(project.speakers[segment.speaker]))
            text = QTableWidgetItem(segment.text)
            text.setToolTip("原始辨識：" + segment.original_text)
            self.transcript.setItem(row, 2, text)
        self.transcript.resizeRowsToContents()
        self.count_label.setText(f"{len(project.speakers)} 位說話者 · {len(project.segments)} 段發言" if project.segments else "尚無逐字稿")
        self.loading = False
        self.refresh_preview()
        self.refresh_buttons()

    def changed(self):
        self.project.minutes = None
        self.refresh_preview()
        self.refresh_buttons()
        self.save_timer.start(600)

    def transcript_changed(self, item):
        if self.loading or item.column() != 2:
            return
        self.project.edit_segment(self.project.segments[item.row()].id, item.text())
        self.changed()

    def speaker_renamed(self, item):
        if self.loading:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if not item.text().strip():
            self.set_project(self.project)
            return
        self.project.rename_speaker(key, item.text())
        self.changed()
        self.set_project(self.project)

    def speaker_reassigned(self, row, speaker):
        self.project.reassign_segment(self.project.segments[row].id, speaker)
        self.changed()
        QTimer.singleShot(0, lambda: self.set_project(self.project))

    def add_speaker(self):
        name, ok = QInputDialog.getText(self, "新增說話者", "姓名或代稱")
        if ok and name.strip():
            self.project.speakers[f"manual:{uuid4().hex}"] = name.strip()
            self.changed()
            self.set_project(self.project)

    def merge_speaker(self):
        item = self.speaker_list.currentItem()
        if not item:
            self.status.setText("先在左側選擇要合併的說話者。")
            return
        source = item.data(Qt.ItemDataRole.UserRole)
        keys = [key for key in self.project.speakers if key != source]
        options = [f"{index + 1}. {self.project.speakers[key]}" for index, key in enumerate(keys)]
        if not options:
            return
        target, ok = QInputDialog.getItem(self, "合併說話者", f"將「{item.text()}」的所有發言歸給：", options, 0, False)
        if ok:
            self.project.merge_speakers(source, keys[options.index(target)])
            self.changed()
            self.set_project(self.project)

    def refresh_preview(self):
        minutes = self.project.minutes
        if not minutes:
            self.preview.setPlainText("尚未整理會議紀錄，或校對內容已變更。\n\n確認姓名與發言後，按「整理會議紀錄」。\n目前仍可匯出完整逐字稿。" if self.project.segments else "")
            return
        by_id = {s.id:s for s in self.project.segments}

        def point(entry):
            sources = "、".join(dict.fromkeys(timestamp(by_id[source].start) for source in entry.sources))
            return f"• {entry.text}  ［{sources}］"

        lines = [self.project.title, self.project.date, "", "會議摘要"]
        lines.extend(point(p) for p in minutes.summary)
        for topic in minutes.topics:
            lines.extend(["", topic.title])
            lines.extend(point(p) for p in topic.points)
        lines.extend(["", "各人發言重點"])
        for person in minutes.people:
            lines.append(self.project.speakers[person.speaker])
            lines.extend(point(p) for p in person.points)
        lines.extend(["", "會議決議"])
        lines.extend(point(p) for p in minutes.decisions)
        if not minutes.decisions:
            lines.append("未記錄到明確決議。")
        lines.extend(["", "待辦事項"])
        for action in minutes.actions:
            lines.append(f"• {action.task}\n  負責人：{action.owner or '未指定'}　期限：{action.deadline or '未指定'}")
        if not minutes.actions:
            lines.append("未記錄到明確待辦事項。")
        self.preview.setPlainText("\n".join(lines))

    def refresh_buttons(self, *_):
        if not hasattr(self, "export_button"):
            return
        has_key = bool(self.key_input.text().strip())
        has_segments = bool(self.project.segments)
        self.transcribe_button.setEnabled(not self.busy and bool(self.project.source_path) and has_key)
        self.summarize_button.setEnabled(not self.busy and has_segments and self.project.transcription_complete and has_key)
        self.export_button.setEnabled(not self.busy and has_segments)
        self.save_button.setEnabled(not self.busy and has_segments)
        self.play_button.setEnabled(not self.busy and has_segments and bool(self.project.source_path))
        self.recover_button.setEnabled(not self.busy and (self.root / "last-session.json").exists())

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.title_input, self.date_input, self.choose_button, self.key_input,
            self.model_input, self.transcript, self.speaker_list, self.add_speaker_button,
            self.merge_button, self.open_button, self.relink_button):
            widget.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.refresh_buttons()

    def start_job(self, action):
        if self.busy:
            return
        if not self.key_input.text().strip():
            self.settings_toggle.setChecked(True)
            self.key_input.setFocus()
            return
        self.stop_playback()
        self.last_error = ""
        self.error_button.hide()
        self.set_busy(True)
        self.job = MeetingJob(action, self.key_input.text(), self.project, self.root, self.model_input.text())
        self.job.progress.connect(self.job_progress)
        self.job.completed.connect(self.job_completed)
        self.job.failed.connect(self.job_failed)
        self.job.finished.connect(self.job_finished)
        self.job.start()

    def job_progress(self, text, value):
        self.status.setText(text)
        self.progress.setRange(0, 0 if value < 0 else 100)
        if value >= 0:
            self.progress.setValue(value)

    def job_completed(self, project):
        self.set_project(project)
        self.autosave()
        if project.minutes:
            self.tabs.setCurrentIndex(1)
        elif not project.segments:
            self.status.setText("轉錄完成，但沒有辨識到發言。請確認錄音內容。")

    def job_failed(self, message, project):
        self.set_project(project)
        self.autosave()
        self.last_error = message
        self.status.setText(message.split("\n", 1)[0])
        self.error_button.show()

    def show_error(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("處理錯誤")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        first, _, details = self.last_error.partition("\n")
        dialog.setText(first)
        if details:
            dialog.setInformativeText(details)
        dialog.setStandardButtons(QMessageBox.StandardButton.Close)
        copy = dialog.addButton("複製錯誤", QMessageBox.ButtonRole.ActionRole)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.last_error))
        dialog.exec()

    def job_finished(self):
        self.progress.setRange(0, 100)
        self.set_busy(False)
        if self.job:
            self.job.deleteLater()
            self.job = None
        if self.close_pending:
            self.close()

    def cancel_job(self):
        if self.job:
            self.job.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在取消。進行中的請求需等待回應，仍可能計費；完成後不會再上傳下一段。")

    def play_selected(self):
        row = self.transcript.currentRow()
        if row < 0:
            self.status.setText("先選取一段發言，再按試聽。")
            return
        path = Path(self.project.source_path)
        if not path.is_file():
            self.status.setText("找不到原始錄音，請按「重新連結錄音」。")
            return
        segment = self.project.segments[row]
        url = QUrl.fromLocalFile(str(path.resolve()))
        self.stop_playback()
        self.pending_seek = (int(segment.start * 1000), int(segment.end * 1000))
        if self.player.source() != url:
            self.player.setSource(url)
        self.start_pending_playback()

    def media_status_changed(self, status):
        self.start_pending_playback()

    def start_pending_playback(self):
        if self.pending_seek is None or self.player.mediaStatus() in (
            QMediaPlayer.MediaStatus.NoMedia, QMediaPlayer.MediaStatus.LoadingMedia,
            QMediaPlayer.MediaStatus.InvalidMedia):
            return
        if not self.player.isSeekable():
            return
        start, end = self.pending_seek
        self.pending_seek = None
        self.segment_end = end
        self.player.setPosition(start)
        self.player.play()

    def stop_playback(self):
        self.pending_seek = None
        self.segment_end = None
        self.player.stop()

    def play_position(self, position):
        if self.segment_end is not None and position >= self.segment_end:
            self.player.pause()
            self.segment_end = None

    def autosave(self):
        if not self.project.segments:
            return True
        try:
            session_root = (self.root / "sessions").resolve()
            session_path = (session_root / f"{self.project.session_id}.json").resolve()
            if not session_path.is_relative_to(session_root):
                raise ValueError("Invalid session path")
            save_project(self.project, session_path)
            save_project(self.project, self.root / "last-session.json")
            self.refresh_buttons()
            return True
        except (OSError, ValueError):
            self.status.setText("自動儲存失敗，請按「儲存專案」選擇可寫入的位置。")
            return False

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "儲存可繼續校對的專案", "會議.meeting.json", "會議專案 (*.meeting.json)")
        if path:
            try:
                save_project(self.project, Path(path))
                self.status.setText("專案已儲存；包含逐字稿但不包含金鑰或錄音。")
            except OSError:
                self.status.setText("無法儲存專案，請選擇可寫入的位置。")

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "開啟會議專案", "", "會議專案 (*.meeting.json *.json)")
        if path:
            self.load_path(Path(path))

    def recover(self):
        self.load_path(self.root / "last-session.json")

    def load_path(self, path):
        try:
            project = load_project(path)
        except (OSError, ValueError):
            self.status.setText("無法讀取此專案，請確認檔案格式與版本。")
            return
        if self.project.segments and not self.autosave():
            return
        self.stop_playback()
        self.set_project(project)
        self.status.setText("專案已載入。若錄音位置不同，可重新連結後試聽。")

    def export_word(self):
        path, _ = QFileDialog.getSaveFileName(self, "匯出 Word 會議紀錄", "會議紀錄.docx", "Word 文件 (*.docx)")
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != ".docx":
            destination = destination.with_suffix(".docx")
        try:
            export_docx(self.project, destination)
            self.status.setText(f"已匯出：{destination.name}")
        except (OSError, ValueError):
            self.status.setText("匯出失敗，請關閉同名 Word 文件，或選擇其他位置。")

    def closeEvent(self, event):
        if self.busy:
            self.close_pending = True
            self.cancel_job()
            event.ignore()
            return
        self.save_timer.stop()
        if not self.autosave():
            answer = QMessageBox.question(self, "尚未儲存", "自動儲存失敗。仍要關閉並放棄未儲存的修改嗎？")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.key_input.clear()
        self.stop_playback()
        event.accept()
