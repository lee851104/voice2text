from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from meeting_notes.audio import prepare_audio, Cancelled
from meeting_notes.models import Project, Minutes, Evidence, PersonHighlights
from meeting_notes.service import MeetingService, friendly_error
from meeting_notes.storage import load_project


def make_wav(path, seconds=2):
    with wave.open(str(path), "wb") as handle:
        handle.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        handle.writeframes(b"\0\0" * int(seconds * 16000))
    return path


def test_real_audio_transcode_preserves_duration_across_chunks(tmp_path):
    import av
    source = make_wav(tmp_path / "錄音.wav", 3)
    chunks = prepare_audio(source, tmp_path / "audio", lambda *_: None, lambda: False, chunk_seconds=1)
    assert len(chunks) == 3
    assert abs(sum(c.duration for c in chunks) - 3) < .01
    assert chunks[0].offset == 0
    assert abs(chunks[1].offset - chunks[0].duration) < .001
    for chunk in chunks:
        assert 0 < chunk.path.stat().st_size < 25_000_000
        with av.open(str(chunk.path)) as container:
            assert sum(frame.samples for frame in container.decode(audio=0)) > 0


def test_cancelled_audio_never_proceeds_to_upload(tmp_path):
    source = make_wav(tmp_path / "recording.wav")
    with pytest.raises(Cancelled):
        prepare_audio(source, tmp_path / "audio", lambda *_: None, lambda: True)


def test_46_minute_recording_is_uploaded_in_three_short_chunks(tmp_path):
    source = make_wav(tmp_path / "46-minutes.wav", 46 * 60)
    chunks = prepare_audio(source, tmp_path / "audio", lambda *_: None, lambda: False)
    assert len(chunks) == 3
    assert sum(c.duration for c in chunks) == pytest.approx(46 * 60)
    assert all(c.duration <= 1200.2 for c in chunks)
    for previous, current in zip(chunks, chunks[1:]):
        assert current.offset == pytest.approx(previous.offset + previous.duration)


def test_rejected_request_shows_server_reason_but_redacts_credentials():
    import httpx2
    from openai import BadRequestError
    secret = "private-credential-for-this-test"
    error = BadRequestError("request failed", response=httpx2.Response(400,
        request=httpx2.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        headers={"x-request-id":"req_test123"}), body={"error":{
            "message":f"Audio duration 2760 seconds exceeds maximum 1400 seconds. {secret} sk-test-secret",
            "code":"audio_too_long", "param":"file"}})
    message = friendly_error(error, secret=secret)
    assert "2760" in message and "1400" in message and "req_test123" in message
    assert secret not in message and "sk-test-secret" not in message


def test_quota_error_is_distinguished_from_rate_limit():
    import httpx2
    from openai import RateLimitError
    response = httpx2.Response(429, request=httpx2.Request("POST", "https://api.openai.com/v1/audio/transcriptions"))
    quota = friendly_error(RateLimitError("quota", response=response, body={"code":"insufficient_quota"}))
    limited = friendly_error(RateLimitError("rate", response=response, body={"code":"rate_limit_exceeded"}))
    assert "額度" in quota and "頻繁" not in quota
    assert "頻繁" in limited and "額度不足" not in limited


def test_old_partial_transcript_is_not_mixed_with_new_chunk_boundaries(tmp_path, monkeypatch):
    p = Project()
    p.add_chunk({"segments":[{"start":0,"end":1,"speaker":"A","text":"舊版已完成"}]}, 0, 0)
    source = make_wav(tmp_path / "old.wav")
    calls = []
    monkeypatch.setattr("meeting_notes.service.prepare_audio", lambda *_: calls.append("prepare"))
    service = MeetingService("test", root=tmp_path / "data", client=fake_client(lambda **kw: calls.append("request")))
    with pytest.raises(ValueError, match="舊版"):
        service.transcribe(source, p, lambda *_:None, lambda:False)
    assert calls == []
    assert p.segments[0].text == "舊版已完成"


def test_old_complete_checkpoint_is_reused_without_reupload(tmp_path, monkeypatch):
    from meeting_notes.storage import save_project
    from meeting_notes.service import fingerprint
    source = make_wav(tmp_path / "old-complete.wav")
    cached = Project(audio_hash=fingerprint(source, lambda:False), transcription_complete=True)
    cached.add_chunk({"segments":[{"start":0,"end":1,"speaker":"A","text":"已完成轉錄"}]}, 0, 0)
    save_project(cached, tmp_path / "data" / "checkpoints" / f"{cached.audio_hash}.json")
    calls = []
    monkeypatch.setattr("meeting_notes.service.prepare_audio", lambda *_: calls.append("prepare"))
    service = MeetingService("test", root=tmp_path / "data", client=fake_client(lambda **kw: calls.append("request")))
    project = Project()
    session = project.session_id
    service.transcribe(source, project, lambda *_:None, lambda:False)
    assert calls == []
    assert project.transcription_complete and project.session_id == session
    assert project.segments[0].text == "已完成轉錄"


def fake_client(create):
    return SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))


def test_retry_reuses_successful_chunks_and_does_not_save_api_key(tmp_path, monkeypatch):
    from meeting_notes.audio import AudioChunk
    source = make_wav(tmp_path / "recording.wav")
    key = "test-secret-never-write"
    chunks = [AudioChunk(source, 0, 1), AudioChunk(source, 1, 1)]
    monkeypatch.setattr("meeting_notes.service.prepare_audio", lambda *_: chunks)
    count = 0

    def create(**kwargs):
        nonlocal count
        count += 1
        assert kwargs["model"] == "gpt-4o-transcribe-diarize"
        assert kwargs["response_format"] == "diarized_json"
        assert kwargs["chunking_strategy"] == "auto"
        assert not kwargs["file"].closed
        if count == 2:
            raise RuntimeError("network failure")
        return SimpleNamespace(model_dump=lambda: {"segments": [
            {"start":0,"end":1,"speaker":"A","text":"確認進度。"}]})

    service = MeetingService(key, root=tmp_path / "data", client=fake_client(create))
    project = Project(title="重試")
    with pytest.raises(RuntimeError):
        service.transcribe(source, project, lambda *_: None, lambda: False)
    assert project.completed_chunks == [0]
    resumed = Project(title="重試")
    service.transcribe(source, resumed, lambda *_: None, lambda: False)
    assert resumed.transcription_complete
    assert len(resumed.segments) == 2
    assert count == 3
    assert resumed.segments[1].start == 1
    assert resumed.segments[0].speaker != resumed.segments[1].speaker
    for saved in (tmp_path / "data").rglob("*.json"):
        assert key not in saved.read_text(encoding="utf-8")


def test_invalid_summary_references_are_rejected():
    p = Project()
    p.add_chunk({"segments":[{"start":0,"end":1,"speaker":"A","text":"我完成了測試。"}]},0,0)
    with pytest.raises(ValueError):
        p.validate_minutes(Minutes(summary=[Evidence(text="虛構決議",sources=["missing"])]))
    p.speakers["c0:B"] = "B"
    with pytest.raises(ValueError):
        p.validate_minutes(Minutes(people=[PersonHighlights(speaker="c0:B", points=[Evidence(text="完成了測試",sources=["s0-0"])])]))


def test_errors_do_not_echo_key_or_raw_server_body():
    assert "sk-secret" not in friendly_error(RuntimeError("bad api_key sk-secret"))


def test_summary_uses_corrected_text_and_structured_response(tmp_path):
    p = Project()
    p.add_chunk({"segments":[{"start":0,"end":1,"speaker":"A","text":"舊文字"}]},0,0)
    p.edit_segment("s0-0", "我會完成測試。")
    p.rename_speaker("c0:A", "小王")
    minutes = Minutes(summary=[Evidence(text="小王會完成測試", sources=["s0-0"])])

    def parse(**kwargs):
        assert kwargs["store"] is False
        assert kwargs["response_format"] is Minutes
        assert "我會完成測試。" in kwargs["messages"][1]["content"]
        assert "舊文字" not in kwargs["messages"][1]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=minutes, refusal=None))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    service = MeetingService("test", root=tmp_path, client=client)
    assert service.summarize(p, lambda *_: None, lambda: False) == minutes


def test_real_openai_sdk_request_and_response_contract_offline(tmp_path):
    import json
    import httpx2
    from openai import OpenAI
    seen = []

    def handle(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/audio/transcriptions"):
            body = request.read()
            assert b"gpt-4o-transcribe-diarize" in body
            assert b"diarized_json" in body
            return httpx2.Response(200, json={"task":"transcribe", "duration":2,
                "text":"我會整理報告。", "segments":[{"id":"seg_0", "type":"transcript.text.segment",
                "start":0, "end":2, "speaker":"A", "text":"我會整理報告。"}]})
        body = json.loads(request.read())
        assert body["store"] is False
        schema = body["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert '"default"' not in json.dumps(schema)
        content = Minutes(summary=[Evidence(text="將整理報告",sources=["s0-0"])]).model_dump_json()
        return httpx2.Response(200,json={"id":"mock", "object":"chat.completion", "created":0,
            "model":"gpt-4.1-mini", "choices":[{"index":0,"finish_reason":"stop",
            "message":{"role":"assistant","content":content,"refusal":None}}]})

    client = OpenAI(api_key="offline-test", http_client=httpx2.Client(transport=httpx2.MockTransport(handle)))
    service = MeetingService("offline-test",root=tmp_path / "data",client=client)
    p = Project()
    service.transcribe(make_wav(tmp_path / "input.wav"), p, lambda *_:None, lambda:False)
    result = service.summarize(p, lambda *_:None, lambda:False)
    service.close()
    assert p.segments[0].text == "我會整理報告。"
    assert result.summary[0].sources == ["s0-0"]
    assert seen == ["/v1/audio/transcriptions", "/v1/chat/completions"]
