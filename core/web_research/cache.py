import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger

logger = get_logger("core.web_research.cache")

_memory_cache: Dict[str, Dict[str, Any]] = {}


def _get_cache_dir() -> Path:
    settings = get_settings()
    cache_dir = Path(settings.DATA_DIR) / "cache" / "tavily"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def compute_query_hash(query: str) -> str:
    normalized = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_cached_search(query: str) -> Optional[List[Dict[str, Any]]]:
    """
    Retrieve cached search results if within 24-hour TTL.
    """
    settings = get_settings()
    ttl_seconds = settings.TAVILY_CACHE_TTL_HOURS * 3600
    now = time.time()
    q_hash = compute_query_hash(query)

    # 1. Check in-memory cache
    if q_hash in _memory_cache:
        entry = _memory_cache[q_hash]
        if now - entry.get("timestamp", 0) < ttl_seconds:
            logger.info("Serving Tavily search results from in-memory cache")
            return entry.get("results")
        else:
            del _memory_cache[q_hash]

    # 2. Check disk cache
    try:
        cache_file = _get_cache_dir() / f"{q_hash}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if now - data.get("timestamp", 0) < ttl_seconds:
                results = data.get("results", [])
                _memory_cache[q_hash] = {"timestamp": data.get("timestamp", 0), "results": results}
                logger.info("Serving Tavily search results from disk cache")
                return results
            else:
                try:
                    cache_file.unlink()
                except OSError:
                    pass
    except Exception as exc:
        logger.warning(f"Error reading Tavily disk cache: {exc}")

    return None


def set_cached_search(query: str, results: List[Dict[str, Any]]) -> None:
    """
    Store search results in cache with current timestamp.
    """
    now = time.time()
    q_hash = compute_query_hash(query)
    entry = {"timestamp": now, "query": query, "results": results}

    _memory_cache[q_hash] = entry

    try:
        cache_file = _get_cache_dir() / f"{q_hash}.json"
        cache_file.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Error writing Tavily disk cache: {exc}")


def clear_cache() -> None:
    """Clear in-memory and disk cache (primarily for tests)."""
    global _memory_cache
    _memory_cache.clear()
    try:
        cache_dir = _get_cache_dir()
        for f in cache_dir.glob("*.json"):
            try:
                f.unlink()
            except OSError:
                pass
    except Exception:
        pass
