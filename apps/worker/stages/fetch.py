import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger
from apps.api.app.storage import get_original_path

logger = get_logger("apps.worker.fetch")
settings = get_settings()


def fetch_video(video_id: str, url: Optional[str], file_path: Optional[str]) -> Tuple[Optional[Path], Dict[str, Any]]:
    """
    Fetches the video via yt-dlp if URL is provided, or verifies existing local file.
    If yt-dlp fails after 3 retries, marks visual_unavailable=true and continues in captions-only mode.
    """
    meta_updates: Dict[str, Any] = {}

    if file_path and Path(file_path).exists():
        return Path(file_path), meta_updates

    if not url:
        # Check standard storage location
        for ext in (".mp4", ".webm", ".mkv"):
            candidate = get_original_path(video_id, ext)
            if candidate.exists():
                return candidate, meta_updates
        raise FileNotFoundError(f"No media found for video {video_id}")

    # It's a URL, use yt-dlp
    output_template = str(get_original_path(video_id, ".%(ext)s"))
    cmd = [
        *settings.resolved_ytdlp_cmd(),
        "--no-playlist",
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
    ]

    if settings.YT_COOKIES_FILE and os.path.isfile(settings.YT_COOKIES_FILE):
        cmd.extend(["--cookies", settings.YT_COOKIES_FILE])

    cmd.append(url)

    max_retries = 3
    success = False
    last_error = ""

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Downloading video {video_id} (attempt {attempt}/{max_retries}): {url}")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                success = True
                break
            last_error = res.stderr or res.stdout
            time.sleep(2 * attempt)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2 * attempt)

    if success:
        # Find the downloaded file
        for ext in (".mp4", ".mkv", ".webm"):
            candidate = get_original_path(video_id, ext)
            if candidate.exists():
                return candidate, meta_updates

    # If yt-dlp download failed, set visual_unavailable fallback
    logger.warning(f"Failed to download video from URL {url}: {last_error}. Falling back to captions-only.")
    meta_updates["visual_unavailable"] = True
    meta_updates["fallback_notice"] = "Upload the video file to enable screen understanding"

    # Try downloading subtitles only with yt-dlp
    sub_cmd = [
        *settings.resolved_ytdlp_cmd(),
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-lang", "en,hi",
        "--convert-subs", "srt",
        "-o", output_template,
        url,
    ]
    try:
        subprocess.run(sub_cmd, capture_output=True, text=True, timeout=30)
    except Exception:
        pass

    return None, meta_updates
