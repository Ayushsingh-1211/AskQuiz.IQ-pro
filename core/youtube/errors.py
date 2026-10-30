"""
Exceptions for YouTube Discovery module.
"""


class YouTubeError(Exception):
    """Base exception for all YouTube Discovery errors."""
    pass


class YouTubeDisabledError(YouTubeError):
    """Raised when YouTube Discovery feature is disabled or API key is not configured."""
    pass


class YouTubeValidationError(YouTubeError):
    """Raised when YouTube search query or parameter validation fails."""
    pass


class YouTubeQuotaError(YouTubeError):
    """Base exception for quota issues."""
    pass


class YouTubeSearchQuotaError(YouTubeQuotaError):
    """
    Raised when the daily fresh search.list quota limit (default 70 calls) is reached.
    Quota Bucket 1.
    """
    pass


class YouTubeVideosQuotaError(YouTubeQuotaError):
    """
    Raised when the daily videos.list quota budget (default 7000 units) is reached.
    Quota Bucket 2.
    """
    pass


class YouTubeAPIError(YouTubeError):
    """Raised when the YouTube Data API returns an error response."""
    pass


class YouTubeRateLimitError(YouTubeAPIError):
    """Raised when the YouTube Data API rate limit is exceeded (HTTP 429)."""
    pass


class YouTubeTimeoutError(YouTubeAPIError):
    """Raised when a request to YouTube Data API times out."""
    pass


class YouTubeNotFoundError(YouTubeError):
    """Raised when a specific YouTube video ID is not found, private, or removed."""
    pass
