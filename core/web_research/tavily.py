import urllib.parse
from typing import Any, Dict, List
import httpx
from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger
from core.web_research.errors import (
    TavilySearchError,
    TavilyTimeoutError,
    WebResearchDisabledError,
)

logger = get_logger("core.web_research.tavily")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def is_valid_url(url: str) -> bool:
    """Validate that the URL is a genuine http/https web URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc) and "." in parsed.netloc
    except Exception:
        return False


def filter_valid_results(raw_results: List[Dict[str, Any]], max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Filter invalid, malformed, or duplicate search results.
    Guarantees no unauthorized webpage scraping: only uses snippets provided by Tavily.
    """
    seen_urls = set()
    valid_results: List[Dict[str, Any]] = []

    for item in raw_results:
        if not isinstance(item, dict):
            continue

        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()

        # Validate URL scheme and domain
        if not is_valid_url(url):
            continue

        # Check for non-empty title and content
        if not title or not content:
            continue

        # Normalize URL to prevent duplicates
        norm_url = url.split("#")[0].rstrip("/")
        if norm_url in seen_urls:
            continue
        seen_urls.add(norm_url)

        valid_results.append({
            "url": url,
            "title": title,
            "content": content,
            "score": float(item.get("score", 0.0)) if item.get("score") is not None else 0.0,
        })

        if len(valid_results) >= max_results:
            break

    return valid_results


def search_tavily(query: str) -> List[Dict[str, Any]]:
    """
    Execute a basic Tavily search and return filtered, verified search results.
    Does NOT scrape raw external web pages.
    """
    settings = get_settings()
    api_key = settings.TAVILY_API_KEY
    if not api_key or not api_key.strip():
        raise WebResearchDisabledError("Tavily API key is not configured.")

    max_results = min(max(1, settings.TAVILY_MAX_RESULTS), 5)

    payload = {
        "api_key": api_key,
        "query": query.strip(),
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,  # Strict: no raw page scraping
    }

    try:
        with httpx.Client(timeout=settings.TAVILY_TIMEOUT_S) as client:
            resp = client.post(TAVILY_SEARCH_URL, json=payload)

        if resp.status_code == 429:
            raise TavilySearchError("Tavily rate limit exceeded.")
        if resp.status_code != 200:
            raise TavilySearchError(f"Tavily search returned status {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        raw_results = data.get("results", [])
        return filter_valid_results(raw_results, max_results=max_results)

    except httpx.TimeoutException as exc:
        logger.error(f"Tavily search timed out for query '{query}': {exc}")
        raise TavilyTimeoutError(f"Tavily search request timed out after {settings.TAVILY_TIMEOUT_S}s.") from exc
    except (TavilySearchError, WebResearchDisabledError):
        raise
    except Exception as exc:
        logger.error(f"Tavily search failed: {exc}")
        raise TavilySearchError(f"Failed to perform web search: {exc}") from exc
