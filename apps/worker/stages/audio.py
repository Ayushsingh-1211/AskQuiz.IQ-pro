import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple
from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger
from apps.api.app.storage import get_audio_path, get_proxy_path

logger = get_logger("apps.worker.audio")
settings = get_settings()


def process_audio_and_proxy(video_id: str, input_path: Path) -> Tuple[Path, Path, float]:
    """
    Extracts 16 kHz mono WAV for Whisper ASR and generates a 720p faststart proxy MP4.
    Returns (audio_path, proxy_path, duration_s).
    """
    ffmpeg_cmd = settings.resolved_ffmpeg_cmd()
    ffprobe_cmd = settings.resolved_ffprobe_cmd()

    audio_out = get_audio_path(video_id)
    proxy_out = get_proxy_path(video_id)

    # 1. Extract 16 kHz mono WAV
    logger.info(f"Extracting 16 kHz WAV audio for video {video_id}...")
    cmd_audio = [
        ffmpeg_cmd,
        "-y",
        "-i", str(input_path),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(audio_out),
    ]
    res_audio = subprocess.run(cmd_audio, capture_output=True, text=True, timeout=180)
    if res_audio.returncode != 0:
        logger.warning(f"Audio extraction failed ({res_audio.stderr[:150]}). Checking if video has no audio track...")
        has_audio = False
        try:
            probe_cmd = [ffprobe_cmd, "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(input_path)]
            p_res = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=15)
            has_audio = bool(p_res.stdout.strip())
        except Exception:
            pass

        if not has_audio:
            logger.info(f"Video {video_id} has no audio stream. Creating silent audio track.")
            dur_cmd = [ffprobe_cmd, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(input_path)]
            dur_res = subprocess.run(dur_cmd, capture_output=True, text=True, timeout=15)
            v_dur = float(dur_res.stdout.strip()) if dur_res.stdout.strip() else 1.0
            silent_cmd = [
                ffmpeg_cmd, "-y",
                "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
                "-t", str(v_dur),
                "-c:a", "pcm_s16le",
                str(audio_out),
            ]
            subprocess.run(silent_cmd, capture_output=True, timeout=30)
        else:
            logger.error(f"Failed to extract audio: {res_audio.stderr[:300]}")
            raise RuntimeError(f"Audio extraction failed: {res_audio.stderr[:200]}")

    # 2. Generate 720p faststart proxy MP4
    logger.info(f"Generating 720p faststart proxy MP4 for video {video_id}...")
    cmd_proxy = [
        ffmpeg_cmd,
        "-y",
        "-i", str(input_path),
        "-vf", r"scale=-2:min(720\,ih)",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(proxy_out),
    ]
    res_proxy = subprocess.run(cmd_proxy, capture_output=True, text=True, timeout=300)
    if res_proxy.returncode != 0:
        # Fallback if transcoding failed: copy video if already mp4, or re-encode without scaling
        logger.warning(f"Proxy generation failed with scaling, attempting copy/fallback: {res_proxy.stderr[:200]}")
        if input_path.suffix.lower() == ".mp4":
            import shutil
            shutil.copyfile(str(input_path), str(proxy_out))
        else:
            cmd_fallback = [ffmpeg_cmd, "-y", "-i", str(input_path), "-movflags", "+faststart", str(proxy_out)]
            subprocess.run(cmd_fallback, capture_output=True, timeout=120)

    # 3. Determine duration
    duration_s = 0.0
    try:
        cmd_probe = [
            ffprobe_cmd,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(proxy_out if proxy_out.exists() else input_path),
        ]
        res_probe = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=10)
        data = json.loads(res_probe.stdout)
        duration_s = float(data.get("format", {}).get("duration", 0.0))
    except Exception as exc:
        logger.warning(f"Could not probe duration: {exc}")

    return audio_out, proxy_out, duration_s
