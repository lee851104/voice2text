import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from meeting_notes.summary_ui import SummaryWindow
from meeting_notes.summary_models import SummaryProject,parse_summary

def test_long_paragraph_expands_without_inner_scroll_and_keeps_draft_on_check():
    app=QApplication.instance() or QApplication([])
    w=SummaryWindow();w.resize(1060,700)
    p=SummaryProject(items=parse_summary('- 原始內容。'));w.set_project(p);w.show();app.processEvents()
    key=p.items[0].id;edit=w.preview.edits[key];before=edit.height()
    text=('長內容需要完整顯示，不能在段落文字框中被裁切。'*12)+'\n新段落內容。'
    edit.setPlainText(text);app.processEvents()
    assert edit.height()>before*3
    assert edit.verticalScrollBar().maximum()==0
    w.set_all(False);app.processEvents();w.set_all(True);app.processEvents()
    assert w.preview.edits[key].toPlainText()==text
    assert p.items[0].source=='原始內容。'
    w.dirty=False;w.close()
