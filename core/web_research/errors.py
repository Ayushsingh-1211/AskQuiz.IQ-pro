"""
Errors for the Web Research pipeline.
"""


class WebResearchError(Exception):
    """Base exception for web research errors."""
    pass


class WebResearchDisabledError(WebResearchError):
    """Raised when web research mode is disabled or unconfigured."""
    pass


class TavilySearchError(WebResearchError):
    """Raised when Tavily search API fails."""
    pass


class TavilyTimeoutError(TavilySearchError):
    """Raised when Tavily search times out."""
    pass


class GroqAPIError(WebResearchError):
    """Raised when Groq API call fails."""
    pass


class GroqRateLimitError(GroqAPIError):
    """Raised when Groq rate limit is exceeded."""
    pass


class GroqQuotaError(GroqAPIError):
    """Raised when Groq quota is exhausted."""
    pass


class GroqTimeoutError(GroqAPIError):
    """Raised when Groq API times out."""
    pass


class WebCitationError(WebResearchError):
    """Raised when citation verification encounters an error."""
    pass
