"""離線驗證分享包：不讀取金鑰、不連線、不載入使用者資料。"""
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont,QFontDatabase
from docx import Document
from .summary_ui import SummaryWindow
from .summary_models import SummaryProject,parse_summary,save_summary,load_summary
from .summary_export import export_summary
from . import __version__

SAMPLE='會議記錄中主席的各項裁示與指示整理如下：\n\n一、 合成測試資料\n'+ '\n'.join(
    f'- **測試事項 {index}**：請確認第 {index} 份合成測試報告的內容，並於下次測試會議回報。'
    for index in range(1,13))

def diagnose(destination,app):
    root=Path(destination); root.mkdir(parents=True,exist_ok=True)
    for filename in ('msjh.ttc','msjhbd.ttc','segoeui.ttf'):
        font=Path('C:/Windows/Fonts')/filename
        if font.exists():QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Microsoft JhengHei',10))
    project=SummaryProject(source=SAMPLE)
    window=SummaryWindow();window.resize(1366,768);window.set_project(project)
    window.show();app.processEvents()
    window.pages.setCurrentIndex(0);app.processEvents()
    assert window.source_input.height()>window.height()*.7
    window.grab().save(str(root/'步驟一.png'))
    window.go_review();app.processEvents()
    assert len(project.selected())==12 and all(i.section=='chair' for i in project.items)
    assert all(window.table.item(row,0).checkState()==Qt.CheckState.Checked for row in range(12))
    first=project.items[0];excluded=project.items[1]
    window.select_none_button.click()
    assert not project.selected()
    window.table.selectRow(0);window.add_selected_button.click()
    assert first.included and len(project.selected())==1
    window.add_all_button.click();assert len(project.selected())==12
    window.table.item(1,0).setCheckState(Qt.CheckState.Unchecked)
    assert excluded.text not in window.preview.toPlainText()
    window.preview.edits[first.id].setPlainText('測試事項：请确认报告内容，並記錄測試結果。')
    window.preview.edits['meeting_time'].setPlainText('會議時間：測試用時間')
    window.preview.edits['heading_chair'].setPlainText('主席宣達事項（測試修訂）')
    assert '請確認報告內容' in first.text
    window.add_item();app.processEvents()
    manual=project.items[-1];manual_row=window.table.rowCount()-1
    window.table.item(manual_row,0).setCheckState(Qt.CheckState.Unchecked)
    app.processEvents();window.grab().save(str(root/'手動段落刪除.png'))
    window.table.cellWidget(manual_row,2).click();app.processEvents()
    assert manual.id not in {i.id for i in project.items}
    assert manual.id not in project.source_order and manual.id not in window.preview.edits
    assert window.table.rowCount()==12
    save_summary(project,root/'驗證.summary.json');assert load_summary(root/'驗證.summary.json')==project
    export_summary(project,root/'驗證會議紀錄.docx')
    text='\n'.join(p.text for p in Document(root/'驗證會議紀錄.docx').paragraphs)
    assert excluded.text not in text and '主管主動說明' not in text
    assert '暫緩' not in text and '{{' not in text and '民國115' not in text
    assert '測試用時間' in text and '主席宣達事項（測試修訂）' in text
    app.processEvents();window.preview.verticalScrollBar().setValue(0)
    app.processEvents();window.grab().save(str(root/'介面預覽.png'))
    window.dirty=False;window.close()
    (root/'diagnostic-report.json').write_text(json.dumps({'status':'passed','version':__version__,
        'items':12,'selected':11,'selection_export':True,'traditional_chinese':True,
        'project_roundtrip':True,'template_loaded':True,'live_api_tested':False,
        'two_steps':True,'inline_edit_export':True,'block_transfer':True,
        'default_all_included':True,'checkbox_selection':True,
        'delete_unchecked_manual_item':True},indent=2),encoding='utf-8')
    return 0
