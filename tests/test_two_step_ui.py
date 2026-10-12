import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from meeting_notes.summary_ui import SummaryWindow
from meeting_notes.summary_models import SummaryProject,parse_summary

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])

def test_two_steps_and_large_paste_area(app):
    w=SummaryWindow();w.resize(1366,768);w.show();app.processEvents()
    assert w.pages.count()==2 and w.pages.currentIndex()==0
    assert w.source_input.height()>w.height()*.7
    w.source_input.setPlainText('- 測試一。\n- 測試二。');w.split_source();app.processEvents()
    assert w.pages.currentIndex()==1 and w.splitter.count()==2
    assert w.job is None and not w.api_dialog.isVisible()
    assert w.preview.height()>w.height()*.7
    w.dirty=False;w.close()

def test_inline_all_text_edits_persist_through_checks_and_steps(app):
    w=SummaryWindow();p=SummaryProject(items=parse_summary('- 保留事項。\n- 隱藏事項。'));w.set_project(p)
    first=p.items[0].id
    w.preview.edits[first].setPlainText('直接修改。\n另起段落。')
    w.preview.edits['meeting_time'].setPlainText('會議時間：手動填寫')
    w.preview.edits['heading_chair'].setPlainText('修改章節名稱')
    w.preview.edits['company'].setPlainText('修改公司名稱')
    item=p.items[0]
    w.remove_items([first])
    assert '直接修改' not in w.preview.toPlainText()
    w.insert_items([first],'reports')
    assert '直接修改' in w.preview.toPlainText()
    w.pages.setCurrentIndex(0);w.go_review()
    assert item.text=='直接修改。\n另起段落。'
    assert item.source=='保留事項。'
    assert p.document_edits['heading_chair']=='修改章節名稱'
    assert p.document_edits['company']=='修改公司名稱'
    assert w.preview.edits['meeting_time'].toPlainText()=='會議時間：手動填寫'
    w.dirty=False;w.close()

def test_section_move_retains_edit_and_add_has_editable_blank(app):
    w=SummaryWindow();w.set_project(SummaryProject(items=parse_summary('- 第一則。')))
    first=w.project.items[0].id
    w.preview.edits[first].setPlainText('修改後的文字')
    w.insert_items([first],'chair')
    assert w.project.items[0].section=='chair'
    assert w.preview.edits[first].toPlainText()=='修改後的文字'
    w.add_item();item=w.project.items[-1]
    assert item.id in w.preview.edits
    w.preview.edits[item.id].setPlainText('手動新增')
    assert w.export_button.isEnabled()
    w.dirty=False;w.close()

def test_empty_item_does_not_consume_number_and_prefix_updates_inline(app):
    w=SummaryWindow();p=SummaryProject(items=parse_summary('列管議題\n- 第一則。\n- 第二則。'));w.set_project(p)
    first,second=[i.id for i in p.items]
    w.preview.edits[first].setPlainText('')
    prefixes={b.key:b.prefix for b in w.preview.blocks}
    assert prefixes[first]=='' and prefixes[second]=='一、'
    assert prefixes['heading_new']=='二、'
    w.preview.edits[first].setPlainText('恢復內容')
    prefixes={b.key:b.prefix for b in w.preview.blocks}
    assert prefixes[first]=='一、' and prefixes[second]=='二、'
    assert prefixes['heading_new']=='三、'
    w.dirty=False;w.close()

def test_preview_normalizes_traditional_on_focus_out(app):
    from PySide6.QtGui import QFocusEvent
    from PySide6.QtCore import QEvent
    w=SummaryWindow();w.set_project(SummaryProject(items=parse_summary('- 內容。')))
    edit=w.preview.edits[w.project.items[0].id];edit.setPlainText('预算执行')
    edit.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
    assert edit.toPlainText()=='預算執行'
    assert edit.toPlainText()==w.project.items[0].text
    w.dirty=False;w.close()
