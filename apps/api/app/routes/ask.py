import json
from typing import Any, Dict, Optional
import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from apps.api.app.config import get_settings
from apps.api.app.db.session import get_db
from apps.api.app.deps import get_current_user_id
from apps.api.app.errors import NotFoundError, ValidationError
from apps.api.app.logging import get_logger
from apps.api.app.schemas.ask import AskRequest, AskResponse
from core.answer import generate_answer
from core.web_research.errors import (
    GroqAPIError,
    GroqQuotaError,
    GroqRateLimitError,
    GroqTimeoutError,
    TavilySearchError,
    TavilyTimeoutError,
    WebResearchDisabledError,
)
from core.web_research.pipeline import run_web_research_pipeline

logger = get_logger("apps.api.ask")
router = APIRouter(prefix="/api/v1/videos", tags=["ask"])
settings = get_settings()

_has_mode_column_cached: Optional[bool] = None


def check_messages_mode_column(conn: psycopg.Connection) -> bool:
    global _has_mode_column_cached
    if _has_mode_column_cached is not None:
        return _has_mode_column_cached
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'messages' AND column_name = 'mode'
                """
            )
            _has_mode_column_cached = cur.fetchone() is not None
    except Exception:
        _has_mode_column_cached = False
    return _has_mode_column_cached


@router.post("/{video_id}/ask", response_model=AskResponse)
def ask_question(
    video_id: str,
    req: AskRequest,
    user_id: str = Depends(get_current_user_id),
    db: psycopg.Connection = Depends(get_db),
) -> AskResponse:
    settings = get_settings()
    if not req.query or not req.query.strip():
        raise ValidationError(message="Question query cannot be empty")

    pause_t = max(0.0, float(req.pause_t))

    # Resolve and validate answer mode
    mode = (req.mode or "video").strip().lower()
    if mode not in ("video", "web"):
        raise ValidationError(message=f"Invalid mode '{mode}'. Supported modes: 'video', 'web'")

    with db.cursor() as cur:
        # Verify video exists
        cur.execute("SELECT id FROM videos WHERE id = %s", (video_id,))
        if not cur.fetchone():
            raise NotFoundError(message=f"Video {video_id} not found")

        # 1. Resolve or create chat session
        session_id = req.session_id
        if session_id:
            cur.execute("SELECT id FROM chat_sessions WHERE id = %s AND user_id = %s", (session_id, user_id))
            if not cur.fetchone():
                session_id = None

        if not session_id:
            cur.execute(
                """
                INSERT INTO chat_sessions (user_id, video_id, title)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (user_id, video_id, f"Session at {pause_t:.1f}s"),
            )
            session_id = str(cur.fetchone()["id"])

        # 2. Fetch history up to pause_t
        has_mode_col = check_messages_mode_column(db)
        if has_mode_col:
            cur.execute(
                """
                SELECT role, content, pause_t, mode
                FROM messages
                WHERE session_id = %s AND (pause_t IS NULL OR pause_t <= %s)
                ORDER BY created_at ASC
                """,
                (session_id, pause_t),
            )
        else:
            cur.execute(
                """
                SELECT role, content, pause_t
                FROM messages
                WHERE session_id = %s AND (pause_t IS NULL OR pause_t <= %s)
                ORDER BY created_at ASC
                """,
                (session_id, pause_t),
            )
        history = cur.fetchall()

    # 3. Route to requested pipeline (Strict: Never silently fall back between modes)
    if mode == "web":
        if not settings.FEATURE_WEB_MODE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Web Research mode is disabled.",
            )
        if not settings.TAVILY_API_KEY or not settings.GROQ_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Web Research is currently unavailable because required credentials are not configured.",
            )

        try:
            answer_result = run_web_research_pipeline(query=req.query)
        except WebResearchDisabledError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
        except (GroqRateLimitError, GroqQuotaError) as exc:
            logger.warning(f"Groq quota/rate limit error: {exc}")
            answer_result = {
                "answer": "Web research quota or rate limit reached. Please try again shortly.",
                "citations": [],
                "confidence": "low",
                "refusal": True,
                "notes": "Groq quota / rate limit exceeded",
                "mode": "web",
            }
        except (TavilyTimeoutError, GroqTimeoutError) as exc:
            logger.warning(f"Web research timeout: {exc}")
            answer_result = {
                "answer": "Web research request timed out. Please try again.",
                "citations": [],
                "confidence": "low",
                "refusal": True,
                "notes": "Search or research timeout",
                "mode": "web",
            }
        except (TavilySearchError, GroqAPIError) as exc:
            logger.error(f"Web research provider error: {exc}")
            answer_result = {
                "answer": f"Web research error: {str(exc)}",
                "citations": [],
                "confidence": "low",
                "refusal": True,
                "notes": str(exc),
                "mode": "web",
            }
    else:
        # Default mode remains video under TAC (Hard Rule 1: SQL filter visible_from_s <= pause_t)
        answer_result = generate_answer(
            conn=db,
            video_id=video_id,
            query=req.query,
            pause_t=pause_t,
            chat_history=history,
        )
        answer_result["mode"] = "video"

    # 4. Save messages (store answer mode in AI conversation history)
    with db.cursor() as cur:
        has_mode = check_messages_mode_column(db)
        if has_mode:
            # Save user message
            cur.execute(
                """
                INSERT INTO messages (session_id, user_id, role, content, pause_t, mode)
                VALUES (%s, %s, 'user', %s, %s, %s)
                """,
                (session_id, user_id, req.query, pause_t, mode),
            )

            # Save assistant message
            cur.execute(
                """
                INSERT INTO messages (session_id, user_id, role, content, pause_t, citations, mode)
                VALUES (%s, %s, 'assistant', %s, %s, %s, %s)
                """,
                (
                    session_id,
                    user_id,
                    answer_result["answer"],
                    pause_t,
                    json.dumps(answer_result.get("citations", [])),
                    mode,
                ),
            )
        else:
            # Fallback when migration 004 has not yet been applied
            cur.execute(
                """
                INSERT INTO messages (session_id, user_id, role, content, pause_t)
                VALUES (%s, %s, 'user', %s, %s)
                """,
                (session_id, user_id, req.query, pause_t),
            )

            cur.execute(
                """
                INSERT INTO messages (session_id, user_id, role, content, pause_t, citations)
                VALUES (%s, %s, 'assistant', %s, %s, %s)
                """,
                (
                    session_id,
                    user_id,
                    answer_result["answer"],
                    pause_t,
                    json.dumps(answer_result.get("citations", [])),
                ),
            )
    db.commit()

    return AskResponse(
        answer=answer_result["answer"],
        citations=answer_result.get("citations", []),
        used_pause_frame=answer_result.get("used_pause_frame", False),
        confidence=answer_result.get("confidence", "high"),
        refusal=answer_result.get("refusal", False),
        notes=answer_result.get("notes"),
        session_id=session_id,
        pause_t=pause_t,
        mode=mode,
    )
