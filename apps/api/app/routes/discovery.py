"""
YouTube Discovery API Routes.

Endpoints:
- GET  /api/v1/discovery/search: Search educational videos.
- GET  /api/v1/discovery/preview/{video_id}: Preview metadata, embeddability & captions.
- POST /api/v1/discovery/import: Validate, deduplicate, and enqueue for existing pipeline ingestion.
- GET  /api/v1/discovery/quota: Inspect remaining daily quota calls and reset time.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional
import psycopg
from fastapi import APIRouter, Depends, Query, Response, status

from apps.api.app.config import get_settings
from apps.api.app.db.session import get_db
from apps.api.app.deps import get_current_user, get_current_user_id
from apps.api.app.errors import (
    AppException,
    ConflictError,
    DegradedServiceError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from apps.api.app.logging import get_logger
from apps.api.app.routes.videos import build_video_out
from apps.api.app.schemas.discovery import (
    YouTubeImportRequest,
    YouTubePreviewOut,
    YouTubeQuotaStatusOut,
    YouTubeSearchResponse,
    YouTubeSearchResultItem,
)
from apps.api.app.schemas.video import VideoOut
from core.youtube import (
    YouTubeAPIError,
    YouTubeDisabledError,
    YouTubeNotFoundError,
    YouTubeRateLimitError,
    YouTubeSearchQuotaError,
    YouTubeTimeoutError,
    YouTubeValidationError,
    YouTubeVideosQuotaError,
    extract_youtube_id,
    get_video_preview,
    quota_manager,
    search_youtube,
    validate_video_id,
)

logger = get_logger("apps.api.discovery")
router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])


@router.get("/search", response_model=YouTubeSearchResponse)
def search_discovery(
    q: str = Query(..., min_length=1, description="Educational topic or question"),
    max_results: Optional[int] = Query(None, ge=1, le=20, description="Max results (1-20, default 10)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> YouTubeSearchResponse:
    """
    Search educational YouTube videos using YouTube Data API v3.
    Respects 24-hour search cache and Bucket 1 daily search call limits (70 calls/day).
    """
    settings = get_settings()
    if not settings.FEATURE_YOUTUBE_DISCOVERY:
        raise DegradedServiceError(
            message="YouTube Discovery feature is currently disabled.",
            hint="Set FEATURE_YOUTUBE_DISCOVERY=true in server configuration.",
        )

    try:
        raw_items = search_youtube(query=q, max_results=max_results)
    except YouTubeValidationError as exc:
        raise ValidationError(message=str(exc))
    except YouTubeDisabledError as exc:
        raise DegradedServiceError(message=str(exc), hint="Configure YOUTUBE_API_KEY on the server.")
    except YouTubeSearchQuotaError as exc:
        raise RateLimitError(
            message=str(exc),
            hint="Daily search quota limit reached. Quotas reset at midnight Pacific Time.",
        )
    except YouTubeVideosQuotaError as exc:
        raise RateLimitError(
            message=str(exc),
            hint="Daily video details quota budget reached. Quotas reset at midnight Pacific Time.",
        )
    except YouTubeRateLimitError as exc:
        raise RateLimitError(message=str(exc))
    except YouTubeTimeoutError as exc:
        raise AppException(code="YOUTUBE_TIMEOUT", message=str(exc), status_code=504)
    except YouTubeAPIError as exc:
        raise AppException(code="YOUTUBE_API_ERROR", message=str(exc), status_code=502)

    items = [YouTubeSearchResultItem(**item) for item in raw_items]
    return YouTubeSearchResponse(query=q.strip(), items=items, total=len(items))


@router.get("/preview/{video_id}", response_model=YouTubePreviewOut)
def preview_discovery(
    video_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> YouTubePreviewOut:
    """
    Retrieve preview metadata, embeddability status, and caption availability for a video.
    Note: Caption availability reflects YouTube metadata only; actual transcript extraction
    occurs during ingestion.
    """
    settings = get_settings()
    if not settings.FEATURE_YOUTUBE_DISCOVERY:
        raise DegradedServiceError(message="YouTube Discovery feature is currently disabled.")

    try:
        preview = get_video_preview(video_id)
    except YouTubeValidationError as exc:
        raise ValidationError(message=str(exc))
    except YouTubeNotFoundError as exc:
        raise NotFoundError(message=str(exc))
    except YouTubeDisabledError as exc:
        raise DegradedServiceError(message=str(exc))
    except YouTubeVideosQuotaError as exc:
        raise RateLimitError(message=str(exc))
    except YouTubeRateLimitError as exc:
        raise RateLimitError(message=str(exc))
    except YouTubeTimeoutError as exc:
        raise AppException(code="YOUTUBE_TIMEOUT", message=str(exc), status_code=504)
    except YouTubeAPIError as exc:
        raise AppException(code="YOUTUBE_API_ERROR", message=str(exc), status_code=502)

    return YouTubePreviewOut(**preview)


@router.post("/import", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
def import_discovery_video(
    req: YouTubeImportRequest,
    response: Response,
    user_id: str = Depends(get_current_user_id),
    db: psycopg.Connection = Depends(get_db),
) -> VideoOut:
    """
    Import a discovered YouTube video into the user's video library and enqueue ingestion.
    - Validates embeddability.
    - Deduplicates against the user's existing library.
    - Enqueues standard video_pipeline background job for Whisper transcription/chunking.
    """
    settings = get_settings()
    if not settings.FEATURE_YOUTUBE_DISCOVERY:
        raise DegradedServiceError(message="YouTube Discovery feature is currently disabled.")

    vid = extract_youtube_id(req.video_id)
    if not vid:
        raise ValidationError(message=f"Could not parse a valid YouTube video ID from '{req.video_id}'.")

    canonical_url = f"https://www.youtube.com/watch?v={vid}"

    # 1. Deduplication check: Has this user already imported this video?
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM videos
            WHERE user_id = %s
              AND (url = %s OR url LIKE %s OR metadata->>'youtube_id' = %s)
            LIMIT 1
            """,
            (user_id, canonical_url, f"%{vid}%", vid),
        )
        existing = cur.fetchone()
        if existing:
            response.status_code = status.HTTP_200_OK
            logger.info(f"Video {vid} already in library for user {user_id}; returning existing record.")
            return build_video_out(existing)

    # 2. Fetch and validate preview metadata
    try:
        preview = get_video_preview(vid)
    except YouTubeValidationError as exc:
        raise ValidationError(message=str(exc))
    except YouTubeNotFoundError as exc:
        raise NotFoundError(message=str(exc))
    except YouTubeDisabledError as exc:
        raise DegradedServiceError(message=str(exc))
    except (YouTubeVideosQuotaError, YouTubeRateLimitError) as exc:
        raise RateLimitError(message=str(exc))
    except YouTubeTimeoutError as exc:
        raise AppException(code="YOUTUBE_TIMEOUT", message=str(exc), status_code=504)
    except YouTubeAPIError as exc:
        raise AppException(code="YOUTUBE_API_ERROR", message=str(exc), status_code=502)

    # 3. Guard against un-embeddable videos
    if not preview.get("is_embeddable", True):
        raise ValidationError(
            message="This video cannot be imported because the creator has disabled third-party embedding."
        )

    # 4. Insert video record into videos table
    title = req.title.strip() if req.title and req.title.strip() else preview.get("title", f"YouTube Video {vid}")
    duration_s = float(preview.get("duration_s", 0)) or None

    meta = {
        "youtube_id": vid,
        "channel_title": preview.get("channel_title", ""),
        "description": preview.get("description", ""),
        "thumbnail_url": preview.get("thumbnail_url", ""),
        "duration_formatted": preview.get("duration_formatted", "0:00"),
        "is_embeddable": preview.get("is_embeddable", True),
        "has_captions": preview.get("has_captions", False),
        "published_at": preview.get("published_at", ""),
        "caption_notice": preview.get("caption_notice", ""),
        "source": "youtube_discovery",
    }

    # Generate advisory transaction lock key for (user_id, vid) to serialize concurrent duplicate imports
    lock_key = int.from_bytes(hashlib.sha256(f"{user_id}:{vid}".encode()).digest()[:8], "big", signed=True)

    with db.transaction():
        with db.cursor() as cur:
            # 1. Acquire transaction-level advisory lock
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

            # 2. Re-check deduplication under the lock
            cur.execute(
                """
                SELECT * FROM videos
                WHERE user_id = %s
                  AND (url = %s OR url LIKE %s OR metadata->>'youtube_id' = %s)
                LIMIT 1
                """,
                (user_id, canonical_url, f"%{vid}%", vid),
            )
            existing = cur.fetchone()
            if existing:
                response.status_code = status.HTTP_200_OK
                logger.info(f"Video {vid} already in library for user {user_id}; returning existing record.")
                return build_video_out(existing)

            # 3. Atomically insert video
            cur.execute(
                """
                INSERT INTO videos (user_id, title, url, duration_s, status, metadata)
                VALUES (%s, %s, %s, %s, 'queued', %s)
                RETURNING *
                """,
                (user_id, title, canonical_url, duration_s, json.dumps(meta)),
            )
            video_row = cur.fetchone()
            created_vid = str(video_row["id"])

            # 4. Atomically enqueue background ingestion job
            cur.execute(
                """
                INSERT INTO jobs (job_type, status, payload)
                VALUES ('video_pipeline', 'queued', %s)
                """,
                (json.dumps({"video_id": created_vid, "url": canonical_url}),),
            )

    logger.info(f"Successfully imported discovered YouTube video {vid} (ID: {created_vid}) for user {user_id}")
    return build_video_out(video_row)


@router.get("/quota", response_model=YouTubeQuotaStatusOut)
def get_discovery_quota(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> YouTubeQuotaStatusOut:
    """Return current YouTube Data API quota utilization and Pacific rollover reset time."""
    status_dict = quota_manager.get_quota_status()
    return YouTubeQuotaStatusOut(**status_dict)
