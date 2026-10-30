from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from apps.api.app.schemas.common import Citation


class AskRequest(BaseModel):
    query: str = Field(..., description="The user question at this moment")
    pause_t: float = Field(..., description="Current video pause timestamp in seconds")
    session_id: Optional[str] = Field(None, description="Optional chat session ID")
    mode: Optional[str] = Field("video", description="Answer mode: 'video' (default) or 'web'")


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    used_pause_frame: bool = False
    confidence: str = "high"
    refusal: bool = False
    notes: Optional[str] = None
    session_id: str
    pause_t: float
    mode: str = "video"
