"""
YouTube Data API v3 Client for Educational Video Discovery.

Features:
- Securely reads API key from apps.api.app.config.Settings (root .env).
- Query sanitization and input validation.
- ISO 8601 duration parser (PT#H#M#S -> seconds and formatted duration string).
- Two independent quota buckets:
    Bucket 1: search.list (app limit: 70 fresh calls/day)
    Bucket 2: videos.list (app budget: 7000 units/day)
- 24-hour caching for search queries and video details.
- Avoids repeated details calls via per-video caching.
- Avoids unnecessary pagination (single targeted query).
- Comprehensive error mapping (quotaExceeded, rate limits, timeouts, disabled).
"""

import html
import re
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pydantic import BaseModel, Field

from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger
from core.youtube.cache import (
    get_batch_cached_details,
    get_cached_search,
    get_cached_video_details,
    set_cached_search,
    set_cached_video_details,
)
from core.youtube.errors import (
    YouTubeAPIError,
    YouTubeDisabledError,
    YouTubeNotFoundError,
    YouTubeQuotaError,
    YouTubeRateLimitError,
    YouTubeSearchQuotaError,
    YouTubeTimeoutError,
    YouTubeValidationError,
    YouTubeVideosQuotaError,
)
from core.youtube.quota import quota_manager

logger = get_logger("core.youtube.client")

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

DURATION_REGEX = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


class YouTubeVideoCard(BaseModel):
    """Normalized video metadata card for discovery UI."""
    video_id: str
    title: str
    channel_title: str
    description: str = ""
    thumbnail_url: str = ""
    published_at: str = ""
    duration_s: int = 0
    duration_formatted: str = "0:00"
    is_embeddable: bool = True
    has_captions: bool = False
    url: str


def validate_query(query: str) -> str:
    """
    Validate and sanitize user search input.
    - Non-empty string
    - Minimum 2 characters, maximum 100 characters
    - Strips dangerous HTML/script tags and unescapes entities
    """
    if not query or not isinstance(query, str) or not query.strip():
        raise YouTubeValidationError("Search query must be a non-empty string.")

    cleaned = query.strip()

    # Strip script and style blocks including their contents
    cleaned = re.sub(r"<script[^>]*>.*?</script>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<style[^>]*>.*?</style>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Strip remaining HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned).strip()

    if not cleaned:
        raise YouTubeValidationError("Search query contains no valid characters.")

    if len(cleaned) < 2:
        raise YouTubeValidationError("Search query must be at least 2 characters long.")
    if len(cleaned) > 100:
        raise YouTubeValidationError("Search query must not exceed 100 characters.")

    # Unescape HTML entities if any
    return html.unescape(cleaned)


def parse_iso_duration(duration_str: str) -> Tuple[int, str]:
    """
    Parse an ISO 8601 duration string into total seconds and a human-readable string.
    Examples:
        'PT15M33S' -> (933, '15:33')
        'PT1H2M10S' -> (3730, '1:02:10')
        'PT45S' -> (45, '0:45')
        'PT2H' -> (7200, '2:00:00')
    """
    if not duration_str or not isinstance(duration_str, str):
        return 0, "0:00"

    match = DURATION_REGEX.match(duration_str.strip())
    if not match:
        return 0, "0:00"

    parts = match.groupdict()
    days = int(parts.get("days") or 0)
    hours = int(parts.get("hours") or 0) + (days * 24)
    minutes = int(parts.get("minutes") or 0)
    seconds = int(parts.get("seconds") or 0)

    total_seconds = hours * 3600 + minutes * 60 + seconds

    if hours > 0:
        formatted = f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        formatted = f"{minutes}:{seconds:02d}"

    return total_seconds, formatted


def _check_api_configuration() -> str:
    """Verify feature flag and API key presence without exposing the key."""
    settings = get_settings()
    if not settings.FEATURE_YOUTUBE_DISCOVERY:
        raise YouTubeDisabledError("YouTube Discovery feature is disabled.")

    api_key = settings.YOUTUBE_API_KEY
    if not api_key or not api_key.strip():
        raise YouTubeDisabledError("YouTube API key is not configured.")

    return api_key.strip()


def _handle_google_api_error(resp: httpx.Response, endpoint_name: str) -> None:
    """Parse Google API error response safely without leaking credentials."""
    status_code = resp.status_code
    reason = ""
    message = ""

    try:
        data = resp.json()
        error_obj = data.get("error", {})
        message = error_obj.get("message", "")
        errors = error_obj.get("errors", [])
        if errors and isinstance(errors, list):
            reason = errors[0].get("reason", "")
    except Exception:
        message = resp.text[:200]

    # Quota exhaustion checks
    if reason in ("quotaExceeded", "dailyLimitExceeded") or "quota" in message.lower():
        if endpoint_name == "search.list":
            raise YouTubeSearchQuotaError(f"YouTube search quota exceeded: {message}")
        else:
            raise YouTubeVideosQuotaError(f"YouTube videos quota exceeded: {message}")

    # Rate limiting
    if status_code == 429 or reason == "rateLimitExceeded":
        raise YouTubeRateLimitError(f"YouTube API rate limit reached: {message}")

    # Invalid / unauthorized key
    if reason in ("keyInvalid", "accessNotConfigured", "forbidden") or status_code in (401, 403):
        raise YouTubeDisabledError(f"YouTube API authorization failed: {message}")

    raise YouTubeAPIError(f"YouTube API {endpoint_name} failed with status {status_code}: {message}")


def search_youtube(
    query: str,
    max_results: Optional[int] = None,
    client: Optional[httpx.Client] = None,
) -> List[Dict[str, Any]]:
    """
    Search YouTube for educational videos matching the query.

    Workflow:
    1. Input validation & sanitization.
    2. Check 24-hour search cache (returns immediately if hit, 0 quota units).
    3. Check Bucket 1 quota (search.list cap: 70 calls/day).
    4. Call search.list (1 call / unit).
    5. Check Bucket 2 video details cache to find any uncached IDs.
    6. If uncached IDs exist, check Bucket 2 quota (videos.list budget: 7000 units).
    7. Call videos.list once for the batch of uncached IDs.
    8. Merge details, update caches, and return normalized video cards.
    """
    sanitized_query = validate_query(query)
    api_key = _check_api_configuration()
    settings = get_settings()

    # 1. Check 24h Search Cache
    cached_results = get_cached_search(sanitized_query)
    if cached_results is not None:
        logger.info(f"Returning {len(cached_results)} cached YouTube search results for query: {sanitized_query}")
        return cached_results

    # 2. Check Quota Bucket 1 (search.list)
    quota_manager.check_search_quota()

    # Determine limit
    limit = min(max_results or settings.YOUTUBE_SEARCH_MAX_RESULTS, 20)

    # 3. Call search.list
    search_params = {
        "part": "snippet",
        "type": "video",
        "q": sanitized_query,
        "maxResults": limit,
        "relevanceLanguage": "en",
        "safeSearch": "moderate",
        "key": api_key,
    }

    own_client = False
    if client is None:
        client = httpx.Client(timeout=settings.YOUTUBE_TIMEOUT_S)
        own_client = True

    try:
        try:
            logger.info(f"Executing YouTube search.list for query: {sanitized_query}")
            resp = client.get(YOUTUBE_SEARCH_URL, params=search_params)
        except httpx.TimeoutException as exc:
            raise YouTubeTimeoutError(f"YouTube search request timed out after {settings.YOUTUBE_TIMEOUT_S}s.") from exc
        except httpx.RequestError as exc:
            raise YouTubeAPIError(f"Network error contacting YouTube API: {exc}") from exc

        if resp.status_code != 200:
            _handle_google_api_error(resp, "search.list")

        # Record quota consumption for Bucket 1 upon successful search call
        quota_manager.record_search_call()

        search_data = resp.json()
        items = search_data.get("items", [])
        if not items:
            set_cached_search(sanitized_query, [])
            return []

        # Extract video IDs
        snippets_by_id: Dict[str, Dict[str, Any]] = {}
        ordered_ids: List[str] = []

        for item in items:
            vid = item.get("id", {}).get("videoId")
            if vid and item.get("id", {}).get("kind") == "youtube#video":
                ordered_ids.append(vid)
                snippets_by_id[vid] = item.get("snippet", {})

        if not ordered_ids:
            set_cached_search(sanitized_query, [])
            return []

        # 4. Check cached video details (Bucket 2 details cache)
        cached_details, uncached_ids = get_batch_cached_details(ordered_ids)

        # 5. Fetch details for uncached IDs in a single batch request
        if uncached_ids:
            # Check Quota Bucket 2 (videos.list)
            quota_manager.check_videos_quota(units=1)

            videos_params = {
                "part": "contentDetails,status,snippet",
                "id": ",".join(uncached_ids),
                "key": api_key,
            }

            try:
                logger.info(f"Executing YouTube videos.list for {len(uncached_ids)} video(s)")
                v_resp = client.get(YOUTUBE_VIDEOS_URL, params=videos_params)
            except httpx.TimeoutException as exc:
                raise YouTubeTimeoutError(f"YouTube videos.list request timed out after {settings.YOUTUBE_TIMEOUT_S}s.") from exc
            except httpx.RequestError as exc:
                raise YouTubeAPIError(f"Network error contacting YouTube videos API: {exc}") from exc

            if v_resp.status_code != 200:
                _handle_google_api_error(v_resp, "videos.list")

            # Record quota consumption for Bucket 2
            quota_manager.record_videos_call(units=1)

            videos_data = v_resp.json()
            for v_item in videos_data.get("items", []):
                vid = v_item.get("id")
                if not vid:
                    continue

                content_details = v_item.get("contentDetails", {})
                status_obj = v_item.get("status", {})
                duration_iso = content_details.get("duration", "")
                duration_s, duration_formatted = parse_iso_duration(duration_iso)
                is_embeddable = bool(status_obj.get("embeddable", True))
                has_captions = content_details.get("caption") == "true"

                v_info = {
                    "duration_s": duration_s,
                    "duration_formatted": duration_formatted,
                    "is_embeddable": is_embeddable,
                    "has_captions": has_captions,
                }
                cached_details[vid] = v_info
                set_cached_video_details(vid, v_info)

        # 6. Merge snippets and video details
        results: List[Dict[str, Any]] = []
        for vid in ordered_ids:
            snip = snippets_by_id.get(vid, {})
            details = cached_details.get(vid, {
                "duration_s": 0,
                "duration_formatted": "0:00",
                "is_embeddable": True,
                "has_captions": False,
            })

            thumbnails = snip.get("thumbnails", {})
            thumb_url = (
                thumbnails.get("high", {}).get("url")
                or thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url")
                or ""
            )

            title = html.unescape(snip.get("title", ""))
            channel_title = html.unescape(snip.get("channelTitle", ""))
            description = html.unescape(snip.get("description", ""))

            card = YouTubeVideoCard(
                video_id=vid,
                title=title,
                channel_title=channel_title,
                description=description,
                thumbnail_url=thumb_url,
                published_at=snip.get("publishedAt", ""),
                duration_s=details.get("duration_s", 0),
                duration_formatted=details.get("duration_formatted", "0:00"),
                is_embeddable=details.get("is_embeddable", True),
                has_captions=details.get("has_captions", False),
                url=f"https://www.youtube.com/watch?v={vid}",
            )
            results.append(card.model_dump())

        # 7. Store in 24h search cache
        set_cached_search(sanitized_query, results)
        return results

    finally:
        if own_client:
            client.close()


def validate_video_id(video_id: str) -> str:
    """Validate YouTube 11-character video ID."""
    if not video_id or not isinstance(video_id, str):
        raise YouTubeValidationError("YouTube video ID must be a non-empty string.")
    cleaned = video_id.strip()
    if not re.match(r"^[a-zA-Z0-9_-]{11}$", cleaned):
        raise YouTubeValidationError(
            f"Invalid YouTube video ID format: '{cleaned}'. Expected 11 alphanumeric characters."
        )
    return cleaned


def extract_youtube_id(url_or_id: str) -> Optional[str]:
    """Extract an 11-character video ID from a bare ID or any standard YouTube URL."""
    if not url_or_id or not isinstance(url_or_id, str):
        return None
    raw = url_or_id.strip()
    if re.match(r"^[a-zA-Z0-9_-]{11}$", raw):
        return raw
    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})",
        r"(?:[?&]v=)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            return match.group(1)
    return None


def get_video_preview(
    video_id_or_url: str,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """
    Validate and retrieve rich metadata preview for a single YouTube video.
    Checks embeddability and caption availability.
    Costs 1 videos.list quota unit (or 0 if cached within 24h).
    """
    vid = extract_youtube_id(video_id_or_url)
    if not vid:
        raise YouTubeValidationError(
            f"Could not extract a valid YouTube video ID from '{video_id_or_url}'."
        )

    vid = validate_video_id(vid)
    api_key = _check_api_configuration()
    settings = get_settings()

    # Check 24-hour cache
    cached = get_cached_video_details(vid)
    if cached and "title" in cached:
        logger.info(f"Serving YouTube video preview from cache for ID: {vid}")
        return cached

    # Check Quota Bucket 2 (videos.list)
    quota_manager.check_videos_quota(units=1)

    own_client = False
    if client is None:
        client = httpx.Client(timeout=settings.YOUTUBE_TIMEOUT_S)
        own_client = True

    try:
        videos_params = {
            "part": "contentDetails,status,snippet",
            "id": vid,
            "key": api_key,
        }
        try:
            logger.info(f"Executing YouTube videos.list preview for video ID: {vid}")
            resp = client.get(YOUTUBE_VIDEOS_URL, params=videos_params)
        except httpx.TimeoutException as exc:
            raise YouTubeTimeoutError(f"YouTube request timed out after {settings.YOUTUBE_TIMEOUT_S}s.") from exc
        except httpx.RequestError as exc:
            raise YouTubeAPIError(f"Network error contacting YouTube API: {exc}") from exc

        if resp.status_code != 200:
            _handle_google_api_error(resp, "videos.list")

        quota_manager.record_videos_call(units=1)

        data = resp.json()
        items = data.get("items", [])
        if not items:
            raise YouTubeNotFoundError(f"YouTube video '{vid}' not found, removed, or private.")

        v_item = items[0]
        snippet = v_item.get("snippet", {})
        content_details = v_item.get("contentDetails", {})
        status_obj = v_item.get("status", {})

        duration_iso = content_details.get("duration", "")
        duration_s, duration_formatted = parse_iso_duration(duration_iso)
        is_embeddable = bool(status_obj.get("embeddable", True))
        has_captions = content_details.get("caption") == "true"

        thumbnails = snippet.get("thumbnails", {})
        thumb_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
            or ""
        )

        title = html.unescape(snippet.get("title", ""))
        channel_title = html.unescape(snippet.get("channelTitle", ""))
        description = html.unescape(snippet.get("description", ""))

        importable = is_embeddable
        import_notice = (
            None
            if is_embeddable
            else "This video cannot be imported into AskQuiz.IQ because the creator disabled embedding."
        )
        caption_notice = (
            "Captions metadata found in YouTube (subject to extraction during ingestion)."
            if has_captions
            else "No caption tracks detected in YouTube metadata; audio will be transcribed using Whisper."
        )

        preview = {
            "video_id": vid,
            "title": title,
            "channel_title": channel_title,
            "description": description,
            "thumbnail_url": thumb_url,
            "published_at": snippet.get("publishedAt", ""),
            "duration_s": duration_s,
            "duration_formatted": duration_formatted,
            "is_embeddable": is_embeddable,
            "has_captions": has_captions,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "importable": importable,
            "import_notice": import_notice,
            "caption_notice": caption_notice,
        }

        # Cache preview
        set_cached_video_details(vid, preview)
        return preview

    finally:
        if own_client:
            client.close()
