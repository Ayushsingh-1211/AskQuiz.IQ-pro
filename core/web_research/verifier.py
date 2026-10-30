from typing import Any, Dict, List, Optional
from apps.api.app.logging import get_logger
from apps.api.app.schemas.common import Citation, SourceRef

logger = get_logger("core.web_research.verifier")


def verify_and_build_web_citations(
    raw_citations: List[Dict[str, Any]],
    sources_by_id: Dict[str, Dict[str, Any]],
) -> List[Citation]:
    """
    Verify citations against genuine supplied web sources.
    - Only accepts genuine supplied source IDs.
    - Rejects fabricated citation IDs.
    - Attaches actual titles and URLs from verified search results.
    - Never fabricates citations.
    """
    verified: List[Citation] = []
    seen_ids = set()

    for item in raw_citations:
        if not isinstance(item, dict):
            continue

        # Extract citation source ID (support source_id or chunk_id)
        raw_id = item.get("source_id") or item.get("chunk_id")
        if not raw_id:
            continue

        raw_id = str(raw_id).strip()

        # Reject fabricated citation IDs not present in supplied sources
        if raw_id not in sources_by_id:
            logger.warning(f"Rejecting fabricated or unknown source ID: '{raw_id}'")
            continue

        if raw_id in seen_ids:
            continue
        seen_ids.add(raw_id)

        source_info = sources_by_id[raw_id]
        title = source_info.get("title", "Web Source")
        url = source_info.get("url", "")
        quote = item.get("quote") or source_info.get("content", "")[:150]

        source_ref = SourceRef(
            source_type="web",
            chunk_id=raw_id,
            label=title,
            metadata={
                "url": url,
                "title": title,
                "quote": quote,
            },
        )

        verified.append(
            Citation(
                chunk_id=raw_id,
                text=quote,
                source_ref=source_ref,
            )
        )

    return verified
