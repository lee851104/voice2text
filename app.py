import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QLocale, QTranslator, QLibraryInfo
from meeting_notes.summary_ui import SummaryWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MeetingNotes")
    app.setOrganizationName("MeetingNotes")
    QLocale.setDefault(QLocale('zh_TW'))
    translator=QTranslator(app)
    translator.load('qtbase_zh_TW',QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    app.installTranslator(translator)
    if len(sys.argv) == 3 and sys.argv[1] == "--diagnose":
        from meeting_notes.summary_diagnostics import diagnose
        return diagnose(sys.argv[2], app)
    window = SummaryWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
