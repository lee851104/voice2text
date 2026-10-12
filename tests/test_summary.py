from pathlib import Path
import json
import zipfile
import pytest
from docx import Document
from meeting_notes.summary_models import SummaryProject, parse_summary, save_summary, load_summary
from meeting_notes.summary_export import export_summary, preview_html

SAMPLE = '''會議記錄中主席（處長）的各項裁示與指示整理如下：

一、 預算執行與管理控管
- **報表數據細化與量化**：须将预算执行报表进行细化。
  各主管須說明原因。
- **主管說明**：下個月會報說明補救方法。

二、 採購案與專案執行
- **116年案件**：12 月底前完成原則簽。
'''

def test_parse_chair_bullets_and_continuation():
    items = parse_summary(SAMPLE)
    assert len(items) == 3
    assert all(i.section == 'chair' and i.included for i in items)
    assert '各主管須說明原因' in items[0].text
    assert '須將預算執行報表' in items[0].text
    assert '须将预算' in items[0].source
    assert items[2].topic == '採購案與專案執行'

def test_paragraphs_and_explicit_sections():
    items = parse_summary('各單位報告及討論事項\n第一個討論。\n\n第二個討論。\n\n新增列管：\n- 指定追蹤事項。')
    assert [i.section for i in items] == ['reports','reports','new']
    assert parse_summary('完成新的測試。')[0].section == 'reports'

def test_save_roundtrip_and_unknown_schema(tmp_path):
    p = SummaryProject(source=SAMPLE, items=parse_summary(SAMPLE))
    p.items[1].included = False
    path = tmp_path/'文字.summary.json'
    save_summary(p,path)
    assert load_summary(path) == p
    assert 'api_key' not in path.read_text(encoding='utf-8')
    path.write_text('{"format":"unknown"}', encoding='utf-8')
    with pytest.raises(ValueError): load_summary(path)

def test_word_and_preview_only_selected_and_blank_metadata(tmp_path):
    p = SummaryProject(source=SAMPLE, items=parse_summary(SAMPLE))
    p.items[1].included=False
    p.items[0].text='只保留編輯後文字 <安全> & 正確'
    out=tmp_path/'紀錄.docx'
    export_summary(p,out)
    d=Document(out)
    text='\n'.join(x.text for x in d.paragraphs)
    assert '只保留編輯後文字' in text and '下個月會報' not in text
    assert '會議時間：' in text and '民國115' not in text
    assert '本週無新增' not in text and '暫緩' not in text
    assert '前次議題追蹤' in text and '紀錄：' in text
    assert '{{' not in text
    html=preview_html(p)
    assert '&lt;安全&gt; &amp; 正確' in html and '下個月會報' not in html
    with zipfile.ZipFile(out) as z:
        assert any(n.startswith('word/media/') for n in z.namelist())
        assert 'PAGE' in z.read('word/footer1.xml').decode()

def test_empty_selected_export_rejected(tmp_path):
    with pytest.raises(ValueError): export_summary(SummaryProject(),tmp_path/'empty.docx')

def test_numbered_standalone_text_not_lost():
    items=parse_summary('一、請各單位按時完成工作。\n二、下週再討論。')
    assert len(items)==2
    assert '按時完成' in items[0].text and '下週再討論' in items[1].text
    assert len(parse_summary('壹、完成預算\n貳、完成採購'))==2

def test_heading_without_bullets_is_retained():
    items=parse_summary('## 預算執行待辦')
    assert len(items)==1 and items[0].text=='預算執行待辦'

def test_non_project_json_rejected(tmp_path):
    path=tmp_path/'bad.summary.json';path.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError):load_summary(path)

def test_failed_export_preserves_existing_file(tmp_path,monkeypatch):
    from docx.document import Document as DocumentClass
    p=SummaryProject(items=parse_summary('- 內容。'))
    target=tmp_path/'existing.docx'; target.write_bytes(b'existing-document')
    def fail(self,path):
        Path(path).write_bytes(b'incomplete'); raise OSError('disk full')
    monkeypatch.setattr(DocumentClass,'save',fail)
    with pytest.raises(OSError):export_summary(p,target)
    assert target.read_bytes()==b'existing-document'
