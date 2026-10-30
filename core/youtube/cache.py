"""
24-Hour Cache for YouTube Discovery.

Features:
- Dual-layer caching: Fast in-memory dict + persistent disk storage.
- Search Query Cache: Keyed by SHA-256 hash of normalized query.
- Video Details Cache: Keyed by YouTube video ID to prevent repeated videos.list calls.
- Configurable TTL: Defaults to 24 hours (86,400 seconds).
- Thread-safe dictionary access.
"""

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger

logger = get_logger("core.youtube.cache")

_search_memory_cache: Dict[str, Dict[str, Any]] = {}
_videos_memory_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _get_search_cache_dir() -> Path:
    settings = get_settings()
    path = Path(settings.DATA_DIR) / "cache" / "youtube" / "search"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_videos_cache_dir() -> Path:
    settings = get_settings()
    path = Path(settings.DATA_DIR) / "cache" / "youtube" / "videos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_query_hash(query: str) -> str:
    """Normalize query text and compute SHA-256 hash."""
    normalized = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_cached_search(query: str) -> Optional[List[Dict[str, Any]]]:
    """Retrieve cached search results if within TTL."""
    settings = get_settings()
    ttl = settings.YOUTUBE_CACHE_TTL_HOURS * 3600
    now = time.time()
    q_hash = compute_query_hash(query)

    with _cache_lock:
        # 1. Check in-memory cache
        if q_hash in _search_memory_cache:
            entry = _search_memory_cache[q_hash]
            if now - entry.get("timestamp", 0) < ttl:
                logger.info(f"Serving YouTube search from in-memory cache for query: {query}")
                return entry.get("results")
            else:
                del _search_memory_cache[q_hash]

    # 2. Check disk cache
    try:
        cache_file = _get_search_cache_dir() / f"{q_hash}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if now - data.get("timestamp", 0) < ttl:
                results = data.get("results", [])
                with _cache_lock:
                    _search_memory_cache[q_hash] = {
                        "timestamp": data.get("timestamp", 0),
                        "results": results,
                    }
                logger.info(f"Serving YouTube search from disk cache for query: {query}")
                return results
            else:
                try:
                    cache_file.unlink(missing_ok=True)
                except OSError:
                    pass
    except Exception as exc:
        logger.warning(f"Error reading YouTube search disk cache: {exc}")

    return None


def set_cached_search(query: str, results: List[Dict[str, Any]]) -> None:
    """Store search results in both in-memory and disk cache."""
    now = time.time()
    q_hash = compute_query_hash(query)

    with _cache_lock:
        _search_memory_cache[q_hash] = {
            "timestamp": now,
            "results": results,
        }

    try:
        cache_file = _get_search_cache_dir() / f"{q_hash}.json"
        payload = {
            "timestamp": now,
            "query": query.strip(),
            "results": results,
        }
        cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Error writing YouTube search disk cache: {exc}")


def get_cached_video_details(video_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached video details if within TTL."""
    settings = get_settings()
    ttl = settings.YOUTUBE_CACHE_TTL_HOURS * 3600
    now = time.time()

    with _cache_lock:
        if video_id in _videos_memory_cache:
            entry = _videos_memory_cache[video_id]
            if now - entry.get("timestamp", 0) < ttl:
                return entry.get("details")
            else:
                del _videos_memory_cache[video_id]

    try:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", video_id)
        cache_file = _get_videos_cache_dir() / f"{safe_id}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if now - data.get("timestamp", 0) < ttl:
                details = data.get("details", {})
                with _cache_lock:
                    _videos_memory_cache[video_id] = {
                        "timestamp": data.get("timestamp", 0),
                        "details": details,
                    }
                return details
            else:
                try:
                    cache_file.unlink(missing_ok=True)
                except OSError:
                    pass
    except Exception as exc:
        logger.warning(f"Error reading YouTube video details disk cache: {exc}")

    return None


def set_cached_video_details(video_id: str, details: Dict[str, Any]) -> None:
    """Store video details in both in-memory and disk cache."""
    now = time.time()

    with _cache_lock:
        _videos_memory_cache[video_id] = {
            "timestamp": now,
            "details": details,
        }

    try:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", video_id)
        cache_file = _get_videos_cache_dir() / f"{safe_id}.json"
        payload = {
            "timestamp": now,
            "video_id": video_id,
            "details": details,
        }
        cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Error writing YouTube video details disk cache: {exc}")


def get_batch_cached_details(video_ids: List[str]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """
    Split a list of video IDs into already-cached details and uncached IDs.
    Prevents repeated calls to videos.list for already known video IDs.
    """
    cached: Dict[str, Dict[str, Any]] = {}
    uncached: List[str] = []

    for vid in video_ids:
        details = get_cached_video_details(vid)
        if details is not None:
            cached[vid] = details
        else:
            uncached.append(vid)

    return cached, uncached


def clear_cache() -> None:
    """Clear memory and disk caches for testing."""
    with _cache_lock:
        _search_memory_cache.clear()
        _videos_memory_cache.clear()

    try:
        for f in _get_search_cache_dir().glob("*.json"):
            f.unlink(missing_ok=True)
        for f in _get_videos_cache_dir().glob("*.json"):
            f.unlink(missing_ok=True)
    except Exception:
        pass
