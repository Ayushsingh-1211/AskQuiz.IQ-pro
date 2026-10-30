import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
import psycopg
from apps.api.app.config import get_settings
from apps.api.app.db.session import get_db_context
from apps.api.app.logging import get_logger
from apps.api.app.storage import get_video_dir
from apps.worker.stages.asr import parse_srt_to_words, transcribe_audio, words_to_srt
from apps.worker.stages.audio import process_audio_and_proxy
from apps.worker.stages.chunk import create_chunks_for_video
from apps.worker.stages.embed import embed_video_chunks
from apps.worker.stages.fetch import fetch_video

logger = get_logger("apps.worker.jobs")
settings = get_settings()

STAGES = [
    "queued",
    "fetching",
    "audio",
    "transcript",
    "frames",
    "ocr",
    "vision",
    "docs",
    "embed",
    "ready_text",
    "ready_full",
    "failed",
]


def update_video_stage(
    conn: psycopg.Connection,
    video_id: str,
    status: str,
    metadata_updates: Optional[Dict[str, Any]] = None,
    duration_s: Optional[float] = None,
    file_path: Optional[str] = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT metadata FROM videos WHERE id = %s", (video_id,))
        row = cur.fetchone()
        current_meta = row["metadata"] if row and row.get("metadata") else {}
        if isinstance(current_meta, str):
            try:
                current_meta = json.loads(current_meta)
            except Exception:
                current_meta = {}

        if metadata_updates:
            current_meta.update(metadata_updates)

        query = "UPDATE videos SET status = %s, metadata = %s"
        params = [status, json.dumps(current_meta)]

        if duration_s is not None and duration_s > 0:
            query += ", duration_s = %s"
            params.append(duration_s)
        if file_path is not None:
            query += ", file_path = %s"
            params.append(file_path)

        query += " WHERE id = %s"
        params.append(video_id)
        cur.execute(query, tuple(params))
    conn.commit()


def process_video_pipeline_job(job_id: str, payload: Dict[str, Any]) -> None:
    video_id = payload.get("video_id")
    if not video_id:
        raise ValueError("Missing video_id in job payload")

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, user_id, title, url, file_path, status, metadata FROM videos WHERE id = %s", (video_id,))
            video = cur.fetchone()

        if not video:
            logger.error(f"Video {video_id} not found in database")
            return

        # Stage 1: Fetching
        update_video_stage(conn, video_id, "fetching")
        media_path, fetch_meta = fetch_video(video_id, video.get("url"), video.get("file_path"))

        if fetch_meta:
            update_video_stage(conn, video_id, "fetching", metadata_updates=fetch_meta)

        if not media_path or not media_path.exists():
            if fetch_meta.get("visual_unavailable"):
                logger.info(f"Video {video_id} visual unavailable, attempting captions-only pipeline")
                video_dir = get_video_dir(video_id)
                srt_candidates = [
                    video_dir / "captions.srt",
                    video_dir / "captions.vtt",
                    Path(f"eval/dataset/{video_id}.en.srt"),
                    *list(video_dir.glob("*.srt")),
                    *list(video_dir.glob("*.vtt")),
                ]
                words = []
                for cand in srt_candidates:
                    if cand.exists():
                        logger.info(f"Found subtitle file for captions-only video {video_id}: {cand}")
                        words = parse_srt_to_words(cand)
                        if words:
                            break

                if words:
                    # Stage 4: Chunking
                    update_video_stage(conn, video_id, "chunk")
                    chunks = create_chunks_for_video(conn, video_id, words)
                    logger.info(f"Created {len(chunks)} chunks from captions for video {video_id}")

                    # Stage 5: Embeddings
                    update_video_stage(conn, video_id, "embed")
                    embedded_count = embed_video_chunks(conn, video_id)
                    logger.info(f"Embedded {embedded_count} chunks for video {video_id}")

                    # Stage 6: Mark ready_text
                    duration_s = words[-1]["end"] if words else (video.get("duration_s") or 0.0)
                    update_video_stage(
                        conn,
                        video_id,
                        "ready_text",
                        duration_s=duration_s,
                        metadata_updates={
                            "status_detail": "captions_only",
                            "chunks_count": len(chunks),
                            "words_count": len(words),
                        },
                    )
                    logger.info(f"Video {video_id} intake complete via captions-only: ready_text ({len(chunks)} chunks)")
                    return
                else:
                    logger.error(f"Video {video_id} visual unavailable and no captions found")
                    update_video_stage(conn, video_id, "failed", metadata_updates={"error": "Media and captions unavailable"})
                    raise RuntimeError(f"Could not fetch media or captions for video {video_id}")
            else:
                update_video_stage(conn, video_id, "failed", metadata_updates={"error": "Media fetch failed"})
                raise RuntimeError(f"Could not fetch media for video {video_id}")

        # Stage 2: Audio & Proxy transcoding
        update_video_stage(conn, video_id, "audio", file_path=str(media_path))
        audio_path, proxy_path, duration_s = process_audio_and_proxy(video_id, media_path)

        # Stage 3: ASR / Transcript / Captions
        update_video_stage(
            conn,
            video_id,
            "transcript",
            duration_s=duration_s,
            metadata_updates={"audio_path": str(audio_path), "proxy_path": str(proxy_path)},
        )
        video_dir = get_video_dir(video_id)
        srt_candidates = [
            video_dir / "captions.srt",
            video_dir / "captions.vtt",
            Path(f"eval/dataset/{video_id}.en.srt"),
            *list(video_dir.glob("*.srt")),
            *list(video_dir.glob("*.vtt")),
        ]
        words = []
        for cand in srt_candidates:
            if cand.exists():
                logger.info(f"Found existing subtitle file for video {video_id}: {cand}")
                words = parse_srt_to_words(cand)
                if words:
                    break

        if not words and audio_path and audio_path.exists():
            logger.info(f"Transcribing audio for video {video_id} with Whisper...")
            words = transcribe_audio(audio_path)
            if words:
                srt_content = words_to_srt(words)
                (video_dir / "captions.srt").write_text(srt_content, encoding="utf-8")
                logger.info(f"Saved captions.srt for video {video_id} ({len(words)} words)")

        # Stage 4: Chunking
        update_video_stage(conn, video_id, "chunk")
        chunks = []
        if words:
            chunks = create_chunks_for_video(conn, video_id, words)
            logger.info(f"Created {len(chunks)} chunks for video {video_id}")

        # Stage 5: Embeddings
        update_video_stage(conn, video_id, "embed")
        embedded_count = embed_video_chunks(conn, video_id)
        logger.info(f"Embedded {embedded_count} chunks for video {video_id}")

        # Stage 6: Mark ready_text / completed
        update_video_stage(
            conn,
            video_id,
            "ready_text",
            duration_s=duration_s,
            metadata_updates={
                "audio_path": str(audio_path),
                "proxy_path": str(proxy_path),
                "chunks_count": len(chunks),
                "words_count": len(words),
            },
        )
        logger.info(f"Video {video_id} intake complete: ready_text ({len(chunks)} chunks, duration: {duration_s:.1f}s)")


def claim_and_execute_next_job() -> bool:
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, job_type, payload, attempts
                FROM jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
            job = cur.fetchone()
            if not job:
                return False

            job_id = str(job["id"])
            job_type = job["job_type"]
            payload = job["payload"]
            attempts = job["attempts"] + 1

            cur.execute(
                """
                UPDATE jobs
                SET status = 'processing', attempts = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (attempts, job_id),
            )
        conn.commit()

    logger.info(f"Processing job {job_id} [{job_type}] (attempt {attempts})")

    try:
        if job_type == "video_pipeline":
            process_video_pipeline_job(job_id, payload)
        else:
            logger.warning(f"Unknown job type: {job_type}")

        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'completed', updated_at = NOW()
                    WHERE id = %s
                    """,
                    (job_id,),
                )
            conn.commit()
        return True

    except Exception as exc:
        logger.exception(f"Job {job_id} failed: {exc}")
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', error = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (str(exc), job_id),
                )
            conn.commit()
        return True
