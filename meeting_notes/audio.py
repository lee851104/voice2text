from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av

# Application upload policy: keep long meetings in manageable requests.
UPLOAD_CHUNK_SECONDS = 20 * 60


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    offset: float
    duration: float


def check_cancel(cancelled):
    if cancelled():
        raise Cancelled("已取消，已完成的轉錄仍會保留。")


def prepare_audio(source: Path, folder: Path, progress, cancelled, chunk_seconds=UPLOAD_CHUNK_SECONDS) -> list[AudioChunk]:
    """Stream-decode; memory usage is independent of recording duration."""
    check_cancel(cancelled)
    source, folder = Path(source), Path(folder)
    if not source.is_file():
        raise ValueError("找不到錄音檔，請重新選擇")
    if chunk_seconds <= 0:
        raise ValueError("分段長度必須大於零")
    folder.mkdir(parents=True, exist_ok=True)
    result = []
    rate, total_samples, local_samples = 16000, 0, 0
    output = stream = None
    last_percent = -1
    output_path = None

    def finish():
        nonlocal output, local_samples
        if output is None:
            return
        for packet in stream.encode(None):
            output.mux(packet)
        output.close()
        output = None
        if output_path.stat().st_size >= 25_000_000:
            raise ValueError("轉換後音檔超過上傳限制，請縮短錄音後重試")
        result.append(AudioChunk(output_path, (total_samples - local_samples) / rate, local_samples / rate))
        local_samples = 0

    def consume(frame):
        nonlocal output, stream, total_samples, local_samples, last_percent, output_path
        check_cancel(cancelled)
        if output is not None and local_samples >= chunk_seconds * rate:
            finish()
        if output is None:
            output_path = folder / f"audio-{len(result):04}.mp3"
            output = av.open(str(output_path), "w", format="mp3")
            stream = output.add_stream("libmp3lame", rate=rate)
            stream.bit_rate = 32000
            stream.layout = "mono"
        frame.pts = local_samples
        frame.time_base = Fraction(1, rate)
        for packet in stream.encode(frame):
            output.mux(packet)
        local_samples += frame.samples
        total_samples += frame.samples
        percent = min(99, int(total_samples / rate / duration * 100)) if duration else -1
        if percent != last_percent:
            progress(f"準備音檔　{percent}%" if percent >= 0 else "準備音檔", percent)
            last_percent = percent

    try:
        with av.open(str(source)) as container:
            if not container.streams.audio:
                raise ValueError("檔案中沒有音軌")
            duration = (container.duration or 0) / av.time_base
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
            for decoded in container.decode(audio=0):
                check_cancel(cancelled)
                decoded.pts = None
                for frame in resampler.resample(decoded):
                    consume(frame)
            for frame in resampler.resample(None):
                consume(frame)
            finish()
    finally:
        if output is not None:
            output.close()
    if not result:
        raise ValueError("錄音檔沒有可處理的音訊")
    progress("音檔準備完成", 100)
    return result
