"""
Pydantic schemas for YouTube Discovery endpoints.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class YouTubeSearchResultItem(BaseModel):
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


class YouTubeSearchResponse(BaseModel):
    query: str
    items: List[YouTubeSearchResultItem]
    total: int


class YouTubePreviewOut(BaseModel):
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
    importable: bool = True
    import_notice: Optional[str] = None
    caption_notice: Optional[str] = None


class YouTubeImportRequest(BaseModel):
    video_id: str = Field(..., description="11-character YouTube video ID or full YouTube URL")
    title: Optional[str] = Field(None, description="Optional custom title for the video")


class YouTubeQuotaStatusOut(BaseModel):
    date_pacific: str
    timezone: str
    next_reset_pt: str
    next_reset_utc: str
    seconds_until_reset: int
    search_calls_used: int
    search_calls_limit: int
    search_calls_remaining: int
    videos_units_used: int
    videos_units_budget: int
    videos_units_remaining: int
