"""預覽與匯出共用的文件文字；手動修改與自動內容分開儲存。"""
from dataclasses import dataclass
from .language import traditional

TEMPLATE_SLOTS={
    '會議時間：{{meeting_time}}':'meeting_time','會議地點：{{location}}':'location',
    '與會人員：{{attendees}}':'attendees','會議主持人：{{chairperson}}':'chairperson',
    '使用人工智慧工具：{{tools}}':'tools','紀錄：{{recorder}}':'recorder',
    '主席宣達事項':'heading_chair','運務處、主管會報、技安會議列管議題':'heading_tracked',
    '新增列管：':'heading_new','解除列管：':'heading_closed','各單位報告及討論事項':'heading_reports',
    '臨時動議：':'heading_motions','前次議題追蹤':'heading_previous','散會時間：{{adjourned_at}}':'adjourned_at',
}

def defaults(project):
    details=project.details
    return {'company':'桃園大眾捷運股份有限公司','meeting_name':details.meeting_name or '處務會議紀錄',
        'meeting_time':'會議時間：'+details.meeting_time,'location':'會議地點：'+details.location,
        'attendees':'與會人員：'+details.attendees,'chairperson':'會議主持人：'+details.chairperson,
        'tools':'使用人工智慧工具：'+('NotebookLM、OpenAI' if project.used_openai else 'NotebookLM'),
        'recorder':'紀錄：'+details.recorder,'adjourned_at':'散會時間：'+details.adjourned_at,
        'heading_chair':'主席宣達事項','heading_tracked':'運務處、主管會報、技安會議列管議題',
        'heading_new':'新增列管：','heading_closed':'解除列管：','heading_reports':'各單位報告及討論事項',
        'heading_motions':'臨時動議：','heading_previous':'前次議題追蹤'}

def static_text(project,key):
    return traditional(project.document_edits.get(key,defaults(project)[key]))

@dataclass
class DocumentBlock:
    key:str
    text:str
    kind:str='heading'
    prefix:str=''
    section:str=''

def number(value):
    digits='零一二三四五六七八九'
    if value<10:return digits[value]
    if value<100:return (digits[value//10] if value>=20 else '')+'十'+(digits[value%10] if value%10 else '')
    return str(value)

def document_blocks(project):
    result=[]
    def fixed(key,prefix='',kind='heading'):
        result.append(DocumentBlock(key,static_text(project,key),kind,prefix))
    def entries(section):
        rows=[i for i in project.items if i.included and i.section==section]
        index=0
        for item in rows:
            if item.text.strip():index+=1
            prefix='' if not item.text.strip() or section in ('new','closed') else number(index)+'、'
            result.append(DocumentBlock(item.id,traditional(item.text),'item',prefix,section))
        return len([i for i in rows if i.text.strip()])
    fixed('company',kind='company');fixed('meeting_name',kind='title')
    for key,prefix in [('meeting_time','壹、'),('location','貳、'),('attendees','參、'),('chairperson','肆、'),('tools','伍、')]:
        fixed(key,prefix,'metadata')
    fixed('recorder',kind='recorder')
    fixed('heading_chair','陸、');entries('chair')
    fixed('heading_tracked','柒、');tracked_count=entries('tracked')
    fixed('heading_new',number(tracked_count+1)+'、','subheading');entries('new')
    fixed('heading_closed',number(tracked_count+2)+'、','subheading');entries('closed')
    fixed('heading_reports','捌、');entries('reports')
    fixed('heading_motions','玖、');entries('motions')
    fixed('heading_previous','壹拾、');entries('previous')
    fixed('adjourned_at','壹拾壹、','metadata')
    return result
