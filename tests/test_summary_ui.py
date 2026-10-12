import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from meeting_notes.summary_ui import SummaryWindow
from meeting_notes.summary_models import SummaryProject,parse_summary

@pytest.fixture(scope='module')
def app(): return QApplication.instance() or QApplication([])

def test_remove_edit_move_live_preview(app):
    w=SummaryWindow()
    w.set_project(SummaryProject(items=parse_summary('- 保留事項。\n- 排除事項。')))
    first=w.project.items[0]
    w.remove_items([w.project.items[1].id])
    assert '排除事項' not in w.preview.toPlainText()
    w.table.selectRow(0)
    w.preview.edits[w.project.items[0].id].setPlainText('改写后的文字。')
    assert w.project.items[0].text=='改寫後的文字。'
    assert w.project.items[0].source=='保留事項。'
    w.insert_items([first.id],'chair')
    assert first.section=='chair'
    assert all(not value for value in w.project.details.model_dump().values())
    w.set_all(False)
    assert not w.export_button.isEnabled()
    w.dirty=False; w.close()

def test_ai_rewrite_can_undo_and_does_not_touch_unselected(app):
    w=SummaryWindow()
    w.set_project(SummaryProject(items=parse_summary('- 第一則。\n- 第二則。')))
    w.project.items[1].included=False
    original=w.project.model_copy(deep=True)
    w.apply_rewrite({w.project.items[0].id:'正式文字。'})
    assert w.project.items[0].text=='正式文字。'
    assert w.project.items[1].text=='第二則。'
    assert w.project.used_openai
    w.undo_rewrite()
    assert w.project==original
    w.dirty=False; w.close()

def test_undo_keeps_later_manual_edits_and_unselected_items(app):
    w=SummaryWindow()
    w.set_project(SummaryProject(items=parse_summary('- 第一則。\n- 第二則。')))
    w.project.items[1].included=False
    w.apply_rewrite({w.project.items[0].id:'正式文字。'})
    w.project.items[1].text='未勾選的人工修訂。'
    w.project.items[0].text='整理後的人工修訂。'
    w.undo_rewrite()
    assert w.project.items[1].text=='未勾選的人工修訂。'
    assert w.project.items[0].text=='整理後的人工修訂。'
    w.dirty=False; w.close()
