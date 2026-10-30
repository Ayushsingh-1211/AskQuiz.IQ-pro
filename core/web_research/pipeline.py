from typing import Any, Dict, List, Optional
from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger
from apps.api.app.schemas.common import Citation
from core.web_research.cache import get_cached_search, set_cached_search
from core.web_research.errors import (
    GroqAPIError,
    GroqQuotaError,
    GroqRateLimitError,
    GroqTimeoutError,
    TavilySearchError,
    TavilyTimeoutError,
    WebResearchDisabledError,
)
from core.web_research.groq import call_groq_research
from core.web_research.tavily import search_tavily
from core.web_research.verifier import verify_and_build_web_citations

logger = get_logger("core.web_research.pipeline")


def run_web_research_pipeline(query: str) -> Dict[str, Any]:
    """
    Executes the independent Web Research answer pipeline:
    Question -> cache -> Tavily -> source filtering -> Groq -> JSON validation -> citation verification -> answer with clickable sources.

    Strictly independent from the video/TAC retrieval pipeline.
    Never silently falls back to video mode.
    """
    settings = get_settings()

    # 1. Feature flag and credential validation
    if not settings.FEATURE_WEB_MODE:
        raise WebResearchDisabledError("Web Research mode is disabled.")
    if not settings.TAVILY_API_KEY or not settings.TAVILY_API_KEY.strip():
        raise WebResearchDisabledError("Tavily API key is not configured for Web Research.")
    if not settings.GROQ_API_KEY or not settings.GROQ_API_KEY.strip():
        raise WebResearchDisabledError("Groq API key is not configured for Web Research.")

    # 2. Check 24-hour search cache
    raw_results = get_cached_search(query)
    if raw_results is None:
        logger.info(f"Tavily cache miss for query: '{query}'")
        raw_results = search_tavily(query)
        if raw_results:
            set_cached_search(query, raw_results)
    else:
        logger.info(f"Tavily cache hit for query: '{query}'")

    # 3. Source filtering & insufficient sources check
    if not raw_results:
        logger.warning(f"No valid web sources found for query: '{query}'")
        return {
            "answer": "Insufficient web sources found to answer this question accurately.",
            "citations": [],
            "confidence": "low",
            "refusal": True,
            "notes": "No valid search results found on the web.",
            "mode": "web",
        }

    # Map sources to short IDs: s1, s2, ...
    annotated_sources: List[Dict[str, Any]] = []
    sources_by_id: Dict[str, Dict[str, Any]] = {}
    for idx, res in enumerate(raw_results, 1):
        sid = f"s{idx}"
        item = {
            "id": sid,
            "url": res["url"],
            "title": res["title"],
            "content": res["content"],
        }
        annotated_sources.append(item)
        sources_by_id[sid] = item

    # 4. Call Groq with configured RESEARCH_MODEL and structured JSON
    llm_output = call_groq_research(query, annotated_sources)

    raw_answer = str(llm_output.get("answer", "")).strip()
    raw_citations = llm_output.get("citations", [])
    if not isinstance(raw_citations, list):
        raw_citations = []
    is_refusal = bool(llm_output.get("refusal", False))
    confidence = str(llm_output.get("confidence", "high"))

    # 5. Citation verification: verify against genuine supplied source IDs
    verified_citations = verify_and_build_web_citations(raw_citations, sources_by_id)

    # 6. Honest handling of insufficient grounded support
    if not is_refusal and not verified_citations and len(annotated_sources) == 0:
        is_refusal = True
        confidence = "low"

    return {
        "answer": raw_answer or "Unable to generate an answer from the retrieved sources.",
        "citations": [c.model_dump() for c in verified_citations],
        "confidence": confidence,
        "refusal": is_refusal,
        "notes": llm_output.get("notes"),
        "mode": "web",
    }
