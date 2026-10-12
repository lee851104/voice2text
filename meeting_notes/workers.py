from PySide6.QtCore import QThread, Signal

from .service import MeetingService, friendly_error


class MeetingJob(QThread):
    progress = Signal(str, int)
    completed = Signal(object)
    failed = Signal(str, object)

    def __init__(self, action, key, project, root, summary_model):
        super().__init__()
        self.action, self.key = action, key
        self.project = project.model_copy(deep=True)
        self.root, self.summary_model = root, summary_model

    def run(self):
        service = None
        key_for_redaction = self.key.strip()
        try:
            service = MeetingService(self.key, root=self.root, summary_model=self.summary_model)
            self.key = ""
            if self.action == "transcribe":
                service.transcribe(self.project.source_path, self.project, self.progress.emit, self.isInterruptionRequested)
            else:
                self.project.minutes = service.summarize(self.project, self.progress.emit, self.isInterruptionRequested)
            self.completed.emit(self.project)
        except Exception as error:
            message = friendly_error(error, secret=key_for_redaction)
            stage = "語音轉錄" if self.action == "transcribe" else "整理摘要"
            model = "gpt-4o-transcribe-diarize" if self.action == "transcribe" else self.summary_model
            # The user-entered model may contain arbitrary text; keep it out of diagnostics.
            if self.action != "transcribe":
                model = "摘要設定中的模型"
            message += f"\n處理階段：{stage}\n使用模型：{model}"
            message += f"\n已完成分段：{len(self.project.completed_chunks)} / {self.project.total_chunks}"
            self.failed.emit(message, self.project)
        finally:
            self.key = ""
            key_for_redaction = ""
            if service:
                service.close()
