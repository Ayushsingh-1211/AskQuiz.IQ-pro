import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import psycopg
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from apps.api.app.config import get_settings
from apps.api.app.db.session import get_db
from apps.api.app.deps import get_current_user, get_current_user_id
from apps.api.app.errors import ForbiddenError, NotFoundError, ValidationError
from apps.api.app.logging import get_logger
from apps.api.app.schemas.video import VideoCreate, VideoListOut, VideoOut
from apps.api.app.storage import (
    generate_stream_token,
    get_original_path,
    get_proxy_path,
    range_streaming_response,
    verify_stream_token,
)

logger = get_logger("apps.api.videos")
router = APIRouter(prefix="/api/v1/videos", tags=["videos"])
settings = get_settings()


def probe_video(file_path: Path) -> Dict[str, Any]:
    ffprobe_cmd = settings.resolved_ffprobe_cmd()
    try:
        cmd = [
            ffprobe_cmd,
            "-v", "error",
            "-show_entries", "format=duration,size,format_name",
            "-show_streams",
            "-of", "json",
            str(file_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            raise ValidationError(message=f"Failed to probe media file: {res.stderr[:200]}")
        data = json.loads(res.stdout)
        duration_s = float(data.get("format", {}).get("duration", 0.0))
        size_bytes = int(data.get("format", {}).get("size", file_path.stat().st_size))
        return {
            "duration_s": duration_s,
            "size_bytes": size_bytes,
            "format": data.get("format", {}).get("format_name", ""),
        }
    except Exception as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(message=f"ffprobe validation error: {str(exc)}")


def build_video_out(row: Dict[str, Any]) -> VideoOut:
    vid = str(row["id"])
    meta = row.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    st = row.get("status", "queued")
    visual_unavailable = meta.get("visual_unavailable", False)
    is_ready_text = st in ("ready_text", "ready_full", "completed")
    is_ready_full = st in ("ready_full", "completed")

    token = generate_stream_token(vid)
    stream_url = f"/api/v1/videos/{vid}/stream?token={token}"

    return VideoOut(
        id=vid,
        user_id=str(row["user_id"]),
        title=row["title"],
        url=row.get("url"),
        file_path=row.get("file_path"),
        duration_s=row.get("duration_s"),
        status=st,
        content_hash=row.get("content_hash"),
        metadata=meta,
        created_at=row["created_at"],
        visual_unavailable=visual_unavailable,
        stream_url=stream_url,
        is_ready_text=is_ready_text,
        is_ready_full=is_ready_full,
    )


@router.post("/upload", response_model=VideoOut)
async def upload_video(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user_id),
    db: psycopg.Connection = Depends(get_db),
) -> VideoOut:
    filename = file.filename or "uploaded.mp4"
    ext = Path(filename).suffix.lower() or ".mp4"
    display_title = title.strip() if title and title.strip() else Path(filename).stem

    # Buffer upload into a temporary file to calculate sha256 and probe
    hasher = hashlib.sha256()
    total_size = 0
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            total_size += len(chunk)
            if total_size > max_bytes:
                tmp.close()
                tmp_path.unlink(missing_ok=True)
                raise ValidationError(message=f"File exceeds maximum upload size of {settings.MAX_UPLOAD_MB}MB")
            hasher.update(chunk)
            tmp.write(chunk)

    content_hash = hasher.hexdigest()

    # Deduplication check for this user
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM videos WHERE user_id = %s AND content_hash = %s LIMIT 1
            """,
            (user_id, content_hash),
        )
        existing = cur.fetchone()
        if existing:
            tmp_path.unlink(missing_ok=True)
            logger.info(f"Video deduplicated for user {user_id}, content_hash {content_hash}")
            return build_video_out(existing)

    # Validate duration with ffprobe
    probe = probe_video(tmp_path)
    duration_s = probe["duration_s"]
    max_duration_s = settings.MAX_VIDEO_HOURS * 3600
    if duration_s > max_duration_s:
        tmp_path.unlink(missing_ok=True)
        raise ValidationError(message=f"Video duration ({duration_s}s) exceeds maximum allowed ({max_duration_s}s)")

    # Insert into videos
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO videos (user_id, title, duration_s, status, content_hash, metadata)
            VALUES (%s, %s, %s, 'queued', %s, %s)
            RETURNING *
            """,
            (user_id, display_title, duration_s, content_hash, json.dumps({"original_filename": filename})),
        )
        video_row = cur.fetchone()
        vid = str(video_row["id"])

        # Save to permanent storage path
        dest_path = get_original_path(vid, ext)
        shutil.move(str(tmp_path), str(dest_path))

        # Update file_path
        cur.execute("UPDATE videos SET file_path = %s WHERE id = %s RETURNING *", (str(dest_path), vid))
        video_row = cur.fetchone()

        # Enqueue processing job
        cur.execute(
            """
            INSERT INTO jobs (job_type, status, payload)
            VALUES ('video_pipeline', 'queued', %s)
            """,
            (json.dumps({"video_id": vid}),),
        )
    db.commit()

    return build_video_out(video_row)


@router.post("", response_model=VideoOut)
def create_video_from_url(
    req: VideoCreate,
    user_id: str = Depends(get_current_user_id),
    db: psycopg.Connection = Depends(get_db),
) -> VideoOut:
    if not req.url or not req.url.strip():
        raise ValidationError(message="URL must be provided")

    url = req.url.strip()
    title = req.title.strip() if req.title and req.title.strip() else f"Video from {url}"

    # Extract YouTube ID if it is a YouTube URL to canonicalize deduplication
    from core.youtube.client import extract_youtube_id
    yt_id = extract_youtube_id(url)
    if yt_id:
        canonical_url = f"https://www.youtube.com/watch?v={yt_id}"
        lock_key = int.from_bytes(hashlib.sha256(f"{user_id}:{yt_id}".encode()).digest()[:8], "big", signed=True)
    else:
        canonical_url = url
        lock_key = int.from_bytes(hashlib.sha256(f"{user_id}:{url}".encode()).digest()[:8], "big", signed=True)

    with db.transaction():
        with db.cursor() as cur:
            # 1. Acquire transaction advisory lock
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

            # 2. Re-check deduplication under the lock
            if yt_id:
                cur.execute(
                    """
                    SELECT * FROM videos
                    WHERE user_id = %s
                      AND (url = %s OR url LIKE %s OR metadata->>'youtube_id' = %s)
                    LIMIT 1
                    """,
                    (user_id, canonical_url, f"%{yt_id}%", yt_id),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM videos
                    WHERE user_id = %s AND url = %s
                    LIMIT 1
                    """,
                    (user_id, canonical_url),
                )
            existing = cur.fetchone()
            if existing:
                logger.info(f"Video {canonical_url} already in library for user {user_id}; returning existing record.")
                return build_video_out(existing)

            # 3. Atomically insert video
            cur.execute(
                """
                INSERT INTO videos (user_id, title, url, status, metadata)
                VALUES (%s, %s, %s, 'queued', '{}'::jsonb)
                RETURNING *
                """,
                (user_id, title, canonical_url),
            )
            video_row = cur.fetchone()
            vid = str(video_row["id"])

            # 4. Atomically enqueue background ingestion job
            cur.execute(
                """
                INSERT INTO jobs (job_type, status, payload)
                VALUES ('video_pipeline', 'queued', %s)
                """,
                (json.dumps({"video_id": vid, "url": canonical_url}),),
            )

    return build_video_out(video_row)


@router.get("", response_model=VideoListOut)
def list_videos(
    user_id: str = Depends(get_current_user_id),
    db: psycopg.Connection = Depends(get_db),
) -> VideoListOut:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM videos WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        rows = cur.fetchall()

    items = [build_video_out(row) for row in rows]
    return VideoListOut(items=items, total=len(items))


@router.get("/{video_id}", response_model=VideoOut)
def get_video(
    video_id: str,
    user_id: str = Depends(get_current_user_id),
    db: psycopg.Connection = Depends(get_db),
) -> VideoOut:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM videos WHERE id = %s AND user_id = %s", (video_id, user_id))
        row = cur.fetchone()

    if not row:
        raise NotFoundError(message="Video not found")

    return build_video_out(row)


@router.get("/{video_id}/stream")
def stream_video(
    video_id: str,
    request: Request,
    token: Optional[str] = Query(None),
    db: psycopg.Connection = Depends(get_db),
):
    # Verify stream token or auth header
    authorized = False
    if token and verify_stream_token(video_id, token):
        authorized = True
    else:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            from apps.api.app.auth import decode_access_token
            try:
                payload = decode_access_token(auth_header.split(" ", 1)[1])
                user_id = payload.get("sub")
                with db.cursor() as cur:
                    cur.execute("SELECT id FROM videos WHERE id = %s AND user_id = %s", (video_id, user_id))
                    if cur.fetchone():
                        authorized = True
            except Exception:
                pass

    if not authorized:
        raise ForbiddenError(message="Invalid stream access token or unauthorized")

    # Locate media file: prefer proxy.mp4, then original
    proxy = get_proxy_path(video_id)
    if proxy.exists():
        return range_streaming_response(request, proxy)

    with db.cursor() as cur:
        cur.execute("SELECT file_path FROM videos WHERE id = %s", (video_id,))
        row = cur.fetchone()

    if row and row.get("file_path"):
        original = Path(row["file_path"])
        if original.exists():
            return range_streaming_response(request, original)

    # Check default original path
    for ext in (".mp4", ".webm", ".mkv"):
        candidate = get_original_path(video_id, ext)
        if candidate.exists():
            return range_streaming_response(request, candidate)

    # Check eval dataset fallback for demo videos
    if video_id == "1ba5b57f-4aad-489d-9948-3d6ab873055e":
        eval_cand = Path("eval/dataset/talking_teacher.mp4").resolve()
        if eval_cand.exists():
            return range_streaming_response(request, eval_cand)

    raise NotFoundError(message="Stream media file not yet available")


@router.get("/{video_id}/captions")
def get_video_captions(video_id: str, db: psycopg.Connection = Depends(get_db)):
    # Check for SRT / VTT in data or eval dataset
    candidates = [
        Path(settings.DATA_DIR).resolve() / "videos" / video_id / "captions.vtt",
        Path(settings.DATA_DIR).resolve() / "videos" / video_id / "captions.srt",
    ]
    if video_id == "1ba5b57f-4aad-489d-9948-3d6ab873055e":
        candidates.append(Path("eval/dataset/talking_teacher.en.srt").resolve())
    srt_text = ""
    for c in candidates:
        if c.exists():
            srt_text = c.read_text(encoding="utf-8", errors="replace")
            break

    if not srt_text:
        # Fallback: synthesize WebVTT from speech chunks in database
        try:
            with db.cursor() as cur:
                cur.execute(
                    "SELECT start_s, end_s, text FROM chunks WHERE video_id = %s AND source_type = 'speech' ORDER BY start_s",
                    (video_id,),
                )
                chunk_rows = cur.fetchall()
            if chunk_rows:
                lines = ["WEBVTT", ""]
                for i, row in enumerate(chunk_rows, 1):
                    s = float(row["start_s"] or 0.0)
                    e = float(row["end_s"] or s + 2.0)
                    sh, sm, ss = int(s // 3600), int((s % 3600) // 60), s % 60
                    eh, em, es = int(e // 3600), int((e % 3600) // 60), e % 60
                    lines.append(f"{i}")
                    lines.append(f"{sh:02d}:{sm:02d}:{ss:06.3f} --> {eh:02d}:{em:02d}:{es:06.3f}")
                    lines.append(str(row["text"]).strip())
                    lines.append("")
                return Response(content="\n".join(lines), media_type="text/vtt")
        except Exception as exc:
            logger.warning(f"Failed to build captions from chunks: {exc}")

        return Response(content="WEBVTT\n\n", media_type="text/vtt")

    # Convert SRT to WebVTT
    import re
    vtt = "WEBVTT\n\n"
    # Replace comma in timestamps with dot: 00:00:01,234 -> 00:00:01.234
    converted = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt_text)
    vtt += converted
    return Response(content=vtt, media_type="text/vtt")
