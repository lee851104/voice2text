from __future__ import annotations

import math
import re
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Model):
    text: str
    sources: list[str]


class Action(Model):
    task: str
    owner: str
    deadline: str
    sources: list[str]


class Topic(Model):
    title: str
    points: list[Evidence]


class PersonHighlights(Model):
    speaker: str
    points: list[Evidence]


class Minutes(Model):
    summary: list[Evidence] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)
    people: list[PersonHighlights] = Field(default_factory=list)
    decisions: list[Evidence] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)


class Segment(Model):
    id: str
    start: float
    end: float
    speaker: str
    text: str
    original_text: str
    original_speaker: str

    @model_validator(mode="after")
    def valid_time(self):
        if not (math.isfinite(self.start) and math.isfinite(self.end)) or self.start < 0 or self.end < self.start:
            raise ValueError("無效的錄音時間")
        return self


class Project(Model):
    version: int = 1
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = "未命名會議"
    date: str = ""
    source_path: str = ""
    audio_hash: str = ""
    transcription_chunk_seconds: int | None = Field(default=None, ge=1, le=5400)
    speakers: dict[str, str] = Field(default_factory=dict)
    segments: list[Segment] = Field(default_factory=list)
    completed_chunks: list[int] = Field(default_factory=list)
    total_chunks: int = 0
    transcription_complete: bool = False
    minutes: Minutes | None = None

    @model_validator(mode="after")
    def validate_project(self):
        if self.version != 1:
            raise ValueError("不支援此版本的會議專案")
        if not re.fullmatch(r"[0-9a-f]{32}", self.session_id):
            raise ValueError("無效的會議識別碼")
        if self.audio_hash and not re.fullmatch(r"[0-9a-f]{64}", self.audio_hash):
            raise ValueError("無效的音檔指紋")
        ids = [s.id for s in self.segments]
        if len(set(ids)) != len(ids) or any(s.speaker not in self.speakers for s in self.segments):
            raise ValueError("逐字稿包含重複段落或不存在的說話者")
        if self.minutes:
            self.validate_minutes(self.minutes)
        return self

    def add_chunk(self, payload: dict, index: int, offset: float):
        if index in self.completed_chunks:
            return
        incoming = payload.get("segments")
        if not isinstance(incoming, list):
            raise ValueError("回應缺少說話者段落，請重試轉錄")
        segments, names = [], {}
        for number, raw in enumerate(incoming):
            speaker = str(raw.get("speaker") or "未知")
            key = f"c{index}:{speaker}"
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            names[key] = f"第 {index + 1} 段 · 說話者 {speaker}"
            segments.append(Segment(id=f"s{index}-{number}", start=float(raw["start"]) + offset,
                end=float(raw["end"]) + offset, speaker=key, text=text,
                original_text=text, original_speaker=key))
        self.speakers.update(names)
        self.segments.extend(segments)
        self.segments.sort(key=lambda s: s.start)
        self.completed_chunks.append(index)
        self.minutes = None

    def rename_speaker(self, key: str, name: str):
        name = name.strip()
        if key not in self.speakers or not name:
            raise ValueError("請輸入說話者姓名")
        if self.speakers[key] != name:
            self.speakers[key] = name
            self.minutes = None

    def merge_speakers(self, source: str, target: str):
        if source == target:
            return
        if source not in self.speakers or target not in self.speakers:
            raise ValueError("找不到說話者")
        for segment in self.segments:
            if segment.speaker == source:
                segment.speaker = target
        del self.speakers[source]
        self.minutes = None

    def reassign_segment(self, segment_id: str, speaker: str):
        if speaker not in self.speakers:
            raise ValueError("找不到說話者")
        segment = next(s for s in self.segments if s.id == segment_id)
        if segment.speaker != speaker:
            segment.speaker = speaker
            self.minutes = None

    def edit_segment(self, segment_id: str, text: str):
        segment = next(s for s in self.segments if s.id == segment_id)
        if segment.text != text:
            segment.text = text
            self.minutes = None

    def validate_minutes(self, minutes: Minutes):
        segments = {s.id: s for s in self.segments}
        entries = list(minutes.summary) + list(minutes.decisions) + list(minutes.actions)
        for topic in minutes.topics:
            entries.extend(topic.points)
        for person in minutes.people:
            if person.speaker not in self.speakers:
                raise ValueError("摘要引用不存在的說話者，請重新整理")
            for point in person.points:
                if any(source not in segments or segments[source].speaker != person.speaker for source in point.sources):
                    raise ValueError("個人摘要的來源與說話者不符，請重新整理")
            entries.extend(person.points)
        for entry in entries:
            if not entry.sources or any(source not in segments for source in entry.sources):
                raise ValueError("摘要引用不存在的段落，請重新整理")


def timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02}:{total % 3600 // 60:02}:{total % 60:02}"
