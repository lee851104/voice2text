"""文字摘要專案；原始文字與使用者編輯分開保存。"""
from __future__ import annotations
import os
import json
import re
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field
from .language import traditional

Section = Literal['chair', 'tracked', 'new', 'closed', 'reports', 'motions', 'previous']
SECTIONS = {'chair':'主席宣達事項', 'tracked':'列管議題', 'new':'新增列管',
    'closed':'解除列管', 'reports':'各單位報告及討論事項', 'motions':'臨時動議', 'previous':'前次議題追蹤'}
DETAILS = {'meeting_name':'會議名稱', 'meeting_time':'會議時間', 'location':'會議地點',
    'attendees':'與會人員', 'chairperson':'會議主持人', 'recorder':'紀錄', 'adjourned_at':'散會時間'}

class SummaryItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(default_factory=lambda: uuid4().hex)
    included: bool = True
    section: Section = 'reports'
    topic: str = ''
    source: str
    text: str

class MeetingDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    meeting_name: str = ''
    meeting_time: str = ''
    location: str = ''
    attendees: str = ''
    chairperson: str = ''
    recorder: str = ''
    adjourned_at: str = ''

class SummaryProject(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format: Literal['meeting-summary-v2'] = 'meeting-summary-v2'
    source: str = ''
    parsed_source: str = ''
    items: list[SummaryItem] = Field(default_factory=list)
    details: MeetingDetails = Field(default_factory=MeetingDetails)
    used_openai: bool = False
    document_edits: dict[str,str] = Field(default_factory=dict)
    source_order: list[str] = Field(default_factory=list)

    def selected(self):
        return [i for i in self.items if i.included and i.text.strip()]

def clean(text):
    return re.sub(r'\*\*|__', '', text).strip()

def parse_summary(source: str) -> list[SummaryItem]:
    result = []
    section: Section = 'reports'
    topic = ''
    pending = []
    def flush():
        if pending:
            raw = '\n'.join(pending).strip()
            result.append(SummaryItem(section=section, topic=topic, source=raw, text=traditional(clean(raw))))
            pending.clear()
    headings = {v:k for k,v in SECTIONS.items()}
    headings['運務處、主管會報、技安會議列管議題']='tracked'
    lines=source.splitlines()
    for line_index,line in enumerate(lines):
        stripped=line.strip()
        if not stripped:
            flush()
            continue
        content=clean(re.sub(r'^#{1,6}\s*', '', stripped))
        numbered=re.match(r'^[一二三四五六七八九十壹貳參肆伍陸柒捌玖拾]+[、.．]\s*(.+)$',content)
        title=(numbered.group(1) if numbered else content).rstrip('：:').strip()
        if title in headings:
            flush(); section=headings[title]; topic=''; continue
        if re.search(r'主席|處長', content) and re.search(r'整理如下|指示如下|裁示如下',content):
            flush(); section='chair'; continue
        if numbered or stripped.startswith('#'):
            flush()
            following=next((s.strip() for s in lines[line_index+1:] if s.strip()),'')
            next_heading=bool(re.match(r'^(?:#{1,6}|[一二三四五六七八九十壹貳參肆伍陸柒捌玖拾]+[、.．])',following))
            if not following or next_heading or (numbered and re.search(r'[。！？；]',title)):
                result.append(SummaryItem(section=section,topic=topic,source=title,text=traditional(title)))
            else: topic=traditional(title)
            continue
        bullet=re.match(r'^(?:[-*•●▪]\s*|\d+[.、)）]\s*|[（(]\d+[)）]\s*)(.+)$',stripped)
        if bullet:
            flush(); pending.append(bullet.group(1))
        else:
            pending.append(stripped)
    flush()
    return result

def save_summary(project: SummaryProject, path):
    path=Path(path)
    descriptor,temp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as f:
            f.write(project.model_dump_json(indent=2))
        os.replace(temp,path)
    finally:
        if Path(temp).exists(): Path(temp).unlink()

def load_summary(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('format')!='meeting-summary-v2':
        raise ValueError('這不是摘要專案。')
    project=SummaryProject.model_validate(data)
    if len({i.id for i in project.items})!=len(project.items):raise ValueError('條目識別碼重複。')
    return project
