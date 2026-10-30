import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger

# Compatibility fix for PyAV where metadata_errors was removed from av.open
try:
    import av
    _orig_av_open = av.open

    def _safe_av_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)

    av.open = _safe_av_open
except Exception:
    pass

logger = get_logger("apps.worker.asr")
settings = get_settings()


def parse_srt_to_words(srt_path: Path) -> List[Dict[str, Any]]:
    """
    Parses an SRT subtitle file and interpolates word timestamps across each cue duration.
    """
    content = srt_path.read_text(encoding="utf-8", errors="replace")
    cue_pattern = re.compile(
        r"(?:^\d+\s*\r?\n)?((?:\d{1,2}:)?\d{2}:\d{2}[,\.]\d{3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[,\.]\d{3})[^\r\n]*\r?\n(.*?)(?=\r?\n\r?\n|\Z)",
        re.DOTALL | re.MULTILINE,
    )

    def parse_time(ts_str: str) -> float:
        ts_str = ts_str.replace(",", ".")
        parts = ts_str.split(":")
        if len(parts) == 3:
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m = float(parts[0])
            s = float(parts[1])
            return m * 60 + s
        return float(parts[0])

    words: List[Dict[str, Any]] = []
    for match in cue_pattern.finditer(content):
        start_t = parse_time(match.group(2))
        end_t = parse_time(match.group(3))
        text = match.group(4).strip()
        # Clean html/formatting tags
        text = re.sub(r"<[^>]+>", "", text)
        cue_words = text.split()
        if not cue_words:
            continue

        cue_duration = max(0.1, end_t - start_t)
        word_duration = cue_duration / len(cue_words)

        for i, w in enumerate(cue_words):
            w_start = round(start_t + (i * word_duration), 3)
            w_end = round(start_t + ((i + 1) * word_duration), 3)
            words.append({"word": w, "start": w_start, "end": w_end})

    return words


def format_srt_time(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def words_to_srt(words: List[Dict[str, Any]]) -> str:
    """
    Converts word timestamp dicts into clean SRT format subtitle cues.
    """
    if not words:
        return ""
    cues: List[List[Dict[str, Any]]] = []
    current_cue: List[Dict[str, Any]] = []
    for w in words:
        current_cue.append(w)
        if len(current_cue) >= 8 or (current_cue[-1]["end"] - current_cue[0]["start"]) >= 4.0 or w["word"].endswith((".", "?", "!")):
            cues.append(current_cue)
            current_cue = []
    if current_cue:
        cues.append(current_cue)

    lines: List[str] = []
    for idx, cue in enumerate(cues, start=1):
        s_t = cue[0]["start"]
        e_t = max(cue[-1]["end"], s_t + 0.5)
        text = " ".join(w["word"] for w in cue)
        lines.append(f"{idx}\n{format_srt_time(s_t)} --> {format_srt_time(e_t)}\n{text}\n")
    return "\n".join(lines)


def transcribe_audio(audio_path: Path, language: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Transcribes audio using faster-whisper with word-level timestamps.
    Falls back to tiny/base on OOM or error.
    """
    from faster_whisper import WhisperModel

    model_size = settings.WHISPER_MODEL
    compute_type = settings.WHISPER_COMPUTE

    try:
        logger.info(f"Loading Whisper model ({model_size}, {compute_type})...")
        model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
        segments, info = model.transcribe(
            str(audio_path),
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            language=language,
        )
        words: List[Dict[str, Any]] = []
        for segment in segments:
            if segment.words:
                for w in segment.words:
                    words.append({"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})
            else:
                seg_words = segment.text.split()
                if seg_words:
                    dur = max(0.1, segment.end - segment.start) / len(seg_words)
                    for i, w in enumerate(seg_words):
                        words.append({
                            "word": w,
                            "start": round(segment.start + (i * dur), 3),
                            "end": round(segment.start + ((i + 1) * dur), 3),
                        })
        return words

    except Exception as exc:
        logger.warning(f"Whisper transcription failed with {model_size}: {exc}. Retrying with tiny model...")
        try:
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(audio_path), word_timestamps=True)
            words = []
            for segment in segments:
                if segment.words:
                    for w in segment.words:
                        words.append({"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})
            return words
        except Exception as fallback_exc:
            logger.error(f"Fallback transcription also failed: {fallback_exc}")
            raise
