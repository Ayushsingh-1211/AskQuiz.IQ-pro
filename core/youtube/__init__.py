"""
YouTube Discovery package for AskQuiz.IQ-Pro.
"""

from core.youtube.cache import (
    clear_cache,
    compute_query_hash,
    get_batch_cached_details,
    get_cached_search,
    get_cached_video_details,
    set_cached_search,
    set_cached_video_details,
)
from core.youtube.client import (
    YouTubeVideoCard,
    extract_youtube_id,
    get_video_preview,
    parse_iso_duration,
    search_youtube,
    validate_query,
    validate_video_id,
)
from core.youtube.errors import (
    YouTubeAPIError,
    YouTubeDisabledError,
    YouTubeError,
    YouTubeNotFoundError,
    YouTubeQuotaError,
    YouTubeRateLimitError,
    YouTubeSearchQuotaError,
    YouTubeTimeoutError,
    YouTubeValidationError,
    YouTubeVideosQuotaError,
)
from core.youtube.quota import (
    PACIFIC_TZ,
    YouTubeQuotaManager,
    calculate_next_reset,
    get_pacific_now,
    quota_manager,
)

__all__ = [
    "search_youtube",
    "get_video_preview",
    "validate_query",
    "validate_video_id",
    "extract_youtube_id",
    "parse_iso_duration",
    "YouTubeVideoCard",
    "YouTubeQuotaManager",
    "quota_manager",
    "PACIFIC_TZ",
    "calculate_next_reset",
    "get_pacific_now",
    "YouTubeError",
    "YouTubeDisabledError",
    "YouTubeNotFoundError",
    "YouTubeValidationError",
    "YouTubeQuotaError",
    "YouTubeSearchQuotaError",
    "YouTubeVideosQuotaError",
    "YouTubeAPIError",
    "YouTubeRateLimitError",
    "YouTubeTimeoutError",
    "get_cached_search",
    "set_cached_search",
    "get_cached_video_details",
    "set_cached_video_details",
    "get_batch_cached_details",
    "clear_cache",
    "compute_query_hash",
]
