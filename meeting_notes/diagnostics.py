"""Offline installation diagnosis; does not read credentials or contact a service."""
import json
import math
import os
from pathlib import Path
import struct
import wave

from .audio import prepare_audio
from .models import Project, Minutes, Evidence, Action, PersonHighlights, Topic
from .export import export_docx
from .storage import save_project, load_project


def diagnose(destination, app):
    from .ui import MainWindow
    from docx import Document
    import av
    import PySide6
    import openai
    from PySide6.QtGui import QFontDatabase, QFont, QRawFont

    # Qt's offscreen plugin does not enumerate Windows system fonts.
    if app.platformName() == "offscreen":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msjh.ttc", "msjhbd.ttc", "segoeui.ttf"):
            path = fonts / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
        app.setFont(QFont("Microsoft JhengHei", 10))
    assert QRawFont.fromFont(QFont("Microsoft JhengHei", 10)).supportsCharacter("會"), "Chinese font unavailable"
    client = openai.OpenAI(api_key="offline-installation-check", base_url="https://api.openai.com/v1")
    client.close()

    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = root / "diagnostic-tone.wav"
    with wave.open(str(source), "wb") as handle:
        handle.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        handle.writeframes(b"".join(struct.pack("<h", int(2000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000 * 8)))
    chunks = prepare_audio(source, root / "audio", lambda *_: None, lambda: False)
    with av.open(str(chunks[0].path)) as audio:
        assert sum(frame.samples for frame in audio.decode(audio=0)) > 0
    project = Project(title="產品進度週會（示範資料）", date="2026-10-12", source_path=str(source))
    entries = [
        ("A", "今天先確認測試進度，再討論下週的安排。"),
        ("B", "登入功能已經測試完成，還有兩項問題需要修正。"),
        ("C", "我會整理使用者回饋，明天下午提供給大家。"),
        ("A", "先完成問題修正，再確認是否可以發佈。"),
        ("B", "我負責修正登入問題，完成後會通知大家。"),
        ("C", "另外需要補上首次使用的操作說明。"),
        ("A", "操作說明的負責人與完成日期，下次再確認。"),
        ("B", "修正後我會重新跑測試，把結果記錄下來。"),
    ]
    project.add_chunk({"segments":[{"start":i,"end":i+1,"speaker":speaker,"text":text} for i,(speaker,text) in enumerate(entries)]},0,0)
    for key, name in zip(project.speakers, ("林怡君", "陳志明", "王雅婷")):
        project.rename_speaker(key, name)
    project.transcription_complete = True
    project.minutes = Minutes(
        summary=[Evidence(text="確認登入測試進度，並安排問題修正與使用者回饋整理。", sources=["s0-0","s0-1","s0-2"])],
        topics=[Topic(title="登入測試", points=[Evidence(text="測試已完成，仍有兩項問題待修正。", sources=["s0-1"])])],
        people=[PersonHighlights(speaker=f"c0:{speaker}", points=[Evidence(text=entries[i][1],sources=[f"s0-{i}"])]) for speaker,i in [("A",3),("B",4),("C",2)]],
        decisions=[Evidence(text="完成問題修正後，再確認是否發佈。", sources=["s0-3"])],
        actions=[Action(task="修正登入問題並重新測試",owner="陳志明",deadline="未指定",sources=["s0-4","s0-7"]),
            Action(task="整理使用者回饋",owner="王雅婷",deadline="明天下午",sources=["s0-2"])])
    save_project(project, root / "sample.meeting.json")
    restored = load_project(root / "sample.meeting.json")
    export_docx(restored, root / "sample.docx")
    text = "\n".join(p.text for p in Document(root / "sample.docx").paragraphs)
    assert "林怡君" in text and "操作說明的負責人" in text
    window = MainWindow(data_root=root / "local-data")
    window.set_project(restored)
    window.status.setText("示範資料 · 離線安裝檢查，不代表真實語音辨識結果。")
    window.show()
    app.processEvents()
    window.grab().save(str(root / "window.png"))
    window.tabs.setCurrentIndex(1)
    app.processEvents()
    window.grab().save(str(root / "preview.png"))
    window.close()
    report = {"status":"passed", "network_requests":0, "audio_decode_encode":True,
        "project_roundtrip":True, "word_export":True, "desktop_render":True,
        "versions":{"PySide6":PySide6.__version__,"av":av.__version__,"openai":openai.__version__}}
    (root / "diagnostic-report.json").write_text(json.dumps(report, indent=2),encoding="utf-8")
    return 0
