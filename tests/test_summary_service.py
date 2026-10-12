import json
from types import SimpleNamespace
import pytest
from meeting_notes.summary_models import SummaryProject, parse_summary
from meeting_notes.summary_service import rewrite_selected, RewriteBatch, RewriteItem, safe_error

class FakeClient:
    def __init__(self, handler):
        self.handler=handler
        self.chat=SimpleNamespace(completions=SimpleNamespace(parse=self.parse))
    def parse(self, **kwargs):
        self.kwargs=kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(refusal=None,parsed=self.handler(kwargs)))])

def test_only_checked_items_sent_and_originals_retained():
    p=SummaryProject(items=parse_summary('- 第一則。\n- 不應上傳。'))
    p.items[1].included=False
    client=FakeClient(lambda k: RewriteBatch(items=[RewriteItem(id=p.items[0].id,text='第一则正式内容。')]))
    updates=rewrite_selected(p,'fake',client=client)
    assert '不應上傳' not in client.kwargs['messages'][1]['content']
    assert client.kwargs['store'] is False
    assert updates=={p.items[0].id:'第一則正式內容。'}
    assert p.items[0].source=='第一則。' and p.items[0].text=='第一則。'

@pytest.mark.parametrize('mode',['missing','duplicate','unknown','blank'])
def test_bad_result_rejected_atomically(mode):
    p=SummaryProject(items=parse_summary('- 第一則。'))
    entry=RewriteItem(id=p.items[0].id,text='正式內容')
    values={'missing':[], 'duplicate':[entry,entry], 'unknown':[RewriteItem(id='other',text='內容')],
        'blank':[RewriteItem(id=entry.id,text=' ')]}
    client=FakeClient(lambda k:RewriteBatch(items=values[mode]))
    with pytest.raises(ValueError): rewrite_selected(p,'fake',client=client)
    assert p.items[0].text=='第一則。'

def test_error_does_not_expose_credentials():
    assert 'fake-secret' not in safe_error(RuntimeError('fake-secret'),'fake-secret')

def test_real_sdk_serializes_strict_schema_and_parses_response():
    import httpx2
    from openai import OpenAI
    p=SummaryProject(items=parse_summary('- 下週二提出報告。'))
    def handler(request):
        assert request.url.path=='/v1/chat/completions'
        body=json.loads(request.content)
        assert body['response_format']['json_schema']['strict'] is True
        assert body['store'] is False
        content=json.dumps({'items':[{'id':p.items[0].id,'text':'請於下週二提出報告。'}]},ensure_ascii=False)
        return httpx2.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':'gpt-4.1-mini',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':content,'refusal':None}}]})
    with OpenAI(api_key='offline-test',http_client=httpx2.Client(transport=httpx2.MockTransport(handler))) as client:
        assert rewrite_selected(p,'offline-test',client=client)[p.items[0].id]=='請於下週二提出報告。'
