"""
Comprehensive API integration tests for YouTube Discovery and Ingestion Handoff.

Covers:
1. Successful educational search.
2. Empty and invalid search queries.
3. Authentication failures.
4. Feature disabled.
5. Quota exhaustion (search and videos buckets).
6. YouTube API errors and timeouts.
7. Video preview and validation.
8. Successful ingestion handoff.
9. Duplicate video import deduplication.
10. User ownership / security isolation.
11. Regression compatibility with existing video ingestion.
"""

import concurrent.futures
import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import httpx
import pytest

from apps.api.app.auth import create_access_token, hash_password
from apps.api.app.config import get_settings
from apps.api.app.db.session import get_db_context
from core.youtube.cache import clear_cache
from core.youtube.errors import (
    YouTubeAPIError,
    YouTubeSearchQuotaError,
    YouTubeTimeoutError,
    YouTubeVideosQuotaError,
)
from core.youtube.quota import quota_manager


@pytest.fixture(autouse=True)
def setup_teardown_discovery():
    """Reset caches, quota counters, and test video rows before each test."""
    clear_cache()
    quota_manager.reset_for_testing()
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM jobs WHERE job_type = 'video_pipeline' AND (payload->>'url' LIKE '%vid_%' OR payload->>'url' LIKE '%test_vid%' OR payload->>'url' LIKE '%dQw4w9WgXcQ%')")
            cur.execute("DELETE FROM videos WHERE url LIKE '%vid_%' OR url LIKE '%test_vid%' OR metadata->>'youtube_id' LIKE '%test_vid%' OR url LIKE '%dQw4w9WgXcQ%'")
        conn.commit()
    yield
    clear_cache()
    quota_manager.reset_for_testing()


@pytest.fixture
def other_user():
    """Create a distinct second user to test ownership and isolation."""
    email = "other_learner@askquiz.iq"
    pwd = "other_password123"
    hashed = hash_password(pwd)
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, hashed_password, full_name, is_active)
                VALUES (%s, %s, %s, true)
                ON CONFLICT (email) DO UPDATE SET hashed_password = EXCLUDED.hashed_password
                RETURNING id, email, full_name, is_active
                """,
                (email, hashed, "Other Learner"),
            )
            user = cur.fetchone()
        conn.commit()
    token = create_access_token({"sub": str(user["id"]), "email": user["email"]})
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


MOCK_PREVIEW_ITEM = {
    "video_id": "test_vid101",
    "title": "Quantum Physics 101",
    "channel_title": "MIT OpenCourseWare",
    "description": "Introduction to Quantum Physics.",
    "thumbnail_url": "https://img.youtube.com/vi/test_vid101/hqdefault.jpg",
    "published_at": "2024-03-01T12:00:00Z",
    "duration_s": 3600,
    "duration_formatted": "1:00:00",
    "is_embeddable": True,
    "has_captions": True,
    "url": "https://www.youtube.com/watch?v=test_vid101",
    "importable": True,
    "import_notice": None,
    "caption_notice": "Captions available from YouTube metadata (subject to extraction during ingestion).",
}

MOCK_SEARCH_ITEMS = [
    {
        "video_id": "test_vid101",
        "title": "Quantum Physics 101",
        "channel_title": "MIT OpenCourseWare",
        "description": "Introduction to Quantum Physics.",
        "thumbnail_url": "https://img.youtube.com/vi/test_vid101/hqdefault.jpg",
        "published_at": "2024-03-01T12:00:00Z",
        "duration_s": 3600,
        "duration_formatted": "1:00:00",
        "is_embeddable": True,
        "has_captions": True,
        "url": "https://www.youtube.com/watch?v=test_vid101",
    },
    {
        "video_id": "test_vid102",
        "title": "Schrödinger Equation",
        "channel_title": "Stanford",
        "description": "Derivation of the wave equation.",
        "thumbnail_url": "https://img.youtube.com/vi/test_vid102/hqdefault.jpg",
        "published_at": "2024-03-02T12:00:00Z",
        "duration_s": 2700,
        "duration_formatted": "45:00",
        "is_embeddable": False,
        "has_captions": False,
        "url": "https://www.youtube.com/watch?v=test_vid102",
    },
]


# ============================================================================
# 1. Successful Educational Search
# ============================================================================

def test_api_discovery_search_success(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    with patch("apps.api.app.routes.discovery.search_youtube", return_value=MOCK_SEARCH_ITEMS) as mock_search:
        resp = client.get(
            "/api/v1/discovery/search?q=Quantum+Mechanics",
            headers=test_user["headers"],
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["query"] == "Quantum Mechanics"
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Check first item fields
    item1 = data["items"][0]
    assert item1["video_id"] == "test_vid101"
    assert item1["title"] == "Quantum Physics 101"
    assert item1["channel_title"] == "MIT OpenCourseWare"
    assert item1["duration_s"] == 3600
    assert item1["duration_formatted"] == "1:00:00"
    assert item1["is_embeddable"] is True
    assert item1["has_captions"] is True
    assert item1["url"] == "https://www.youtube.com/watch?v=test_vid101"

    # Check second item fields (non-embeddable)
    item2 = data["items"][1]
    assert item2["video_id"] == "test_vid102"
    assert item2["is_embeddable"] is False
    assert item2["has_captions"] is False


# ============================================================================
# 2. Empty and Invalid Search Queries
# ============================================================================

def test_api_discovery_search_invalid_queries(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    # Missing query param
    resp1 = client.get("/api/v1/discovery/search", headers=test_user["headers"])
    assert resp1.status_code in (400, 422)

    # Empty string
    resp2 = client.get("/api/v1/discovery/search?q=", headers=test_user["headers"])
    assert resp2.status_code in (400, 422)

    # Whitespace only
    resp3 = client.get("/api/v1/discovery/search?q=%20%20%20", headers=test_user["headers"])
    assert resp3.status_code in (400, 422)

    # Too short (< 2 chars after strip)
    resp4 = client.get("/api/v1/discovery/search?q=a", headers=test_user["headers"])
    assert resp4.status_code in (400, 422)

    # Invalid max_results (< 1 or > 20)
    resp5 = client.get("/api/v1/discovery/search?q=Calculus&max_results=0", headers=test_user["headers"])
    assert resp5.status_code in (400, 422)

    resp6 = client.get("/api/v1/discovery/search?q=Calculus&max_results=25", headers=test_user["headers"])
    assert resp6.status_code in (400, 422)


# ============================================================================
# 3. Authentication Failures
# ============================================================================

def test_api_discovery_auth_failures(client: TestClient):
    # Search without token
    r1 = client.get("/api/v1/discovery/search?q=Linear+Algebra")
    assert r1.status_code == 401

    # Preview without token
    r2 = client.get("/api/v1/discovery/preview/test_vid101")
    assert r2.status_code == 401

    # Import without token
    r3 = client.post("/api/v1/discovery/import", json={"video_id": "test_vid101"})
    assert r3.status_code == 401

    # Quota endpoint without token
    r4 = client.get("/api/v1/discovery/quota")
    assert r4.status_code == 401


# ============================================================================
# 4. Feature Disabled Flag
# ============================================================================

def test_api_discovery_feature_disabled(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", False)

    # Search should return 503
    r1 = client.get("/api/v1/discovery/search?q=Physics", headers=test_user["headers"])
    assert r1.status_code == 503
    assert "disabled" in r1.json()["message"].lower()

    # Preview should return 503
    r2 = client.get("/api/v1/discovery/preview/test_vid101", headers=test_user["headers"])
    assert r2.status_code == 503

    # Import should return 503
    r3 = client.post("/api/v1/discovery/import", headers=test_user["headers"], json={"video_id": "test_vid101"})
    assert r3.status_code == 503


# ============================================================================
# 5. Quota Exhaustion (Search & Videos Buckets)
# ============================================================================

def test_api_discovery_search_quota_exhausted(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    with patch(
        "apps.api.app.routes.discovery.search_youtube",
        side_effect=YouTubeSearchQuotaError("Search quota exceeded for today."),
    ):
        resp = client.get("/api/v1/discovery/search?q=Calculus", headers=test_user["headers"])

    assert resp.status_code == 429
    data = resp.json()
    assert "quota" in data["message"].lower()


def test_api_discovery_videos_quota_exhausted(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    with patch(
        "apps.api.app.routes.discovery.get_video_preview",
        side_effect=YouTubeVideosQuotaError("Videos details quota budget exhausted."),
    ):
        resp = client.get("/api/v1/discovery/preview/test_vid101", headers=test_user["headers"])

    assert resp.status_code == 429
    assert "budget" in resp.json()["message"].lower() or "quota" in resp.json()["message"].lower()


# ============================================================================
# 6. YouTube API Errors & Timeout
# ============================================================================

def test_api_discovery_timeout_handling(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    with patch(
        "apps.api.app.routes.discovery.search_youtube",
        side_effect=YouTubeTimeoutError("YouTube search timed out after 15s."),
    ):
        resp = client.get("/api/v1/discovery/search?q=TimeoutTest", headers=test_user["headers"])

    assert resp.status_code == 504
    assert resp.json()["code"] == "YOUTUBE_TIMEOUT"


def test_api_discovery_api_error_handling(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    with patch(
        "apps.api.app.routes.discovery.search_youtube",
        side_effect=YouTubeAPIError("Google API returned internal error 500."),
    ):
        resp = client.get("/api/v1/discovery/search?q=ErrorTest", headers=test_user["headers"])

    assert resp.status_code == 502
    assert resp.json()["code"] == "YOUTUBE_API_ERROR"


# ============================================================================
# 7. Video Preview and Validation
# ============================================================================

def test_api_discovery_preview_success(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    with patch("apps.api.app.routes.discovery.get_video_preview", return_value=MOCK_PREVIEW_ITEM):
        resp = client.get("/api/v1/discovery/preview/test_vid101", headers=test_user["headers"])

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["video_id"] == "test_vid101"
    assert data["title"] == "Quantum Physics 101"
    assert data["importable"] is True
    assert data["has_captions"] is True
    assert "Captions available" in data["caption_notice"]


def test_api_discovery_preview_not_found(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    from core.youtube.errors import YouTubeNotFoundError

    with patch(
        "apps.api.app.routes.discovery.get_video_preview",
        side_effect=YouTubeNotFoundError("YouTube video 'nonexistent1' not found."),
    ):
        resp = client.get("/api/v1/discovery/preview/nonexistent1", headers=test_user["headers"])

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ============================================================================
# 8. Successful Ingestion Handoff
# ============================================================================

def test_api_discovery_import_success(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    with patch("apps.api.app.routes.discovery.get_video_preview", return_value=MOCK_PREVIEW_ITEM):
        resp = client.post(
            "/api/v1/discovery/import",
            headers=test_user["headers"],
            json={"video_id": "test_vid101", "title": "My Quantum Physics Study"},
        )

    assert resp.status_code == 201, resp.text
    video_data = resp.json()

    assert video_data["title"] == "My Quantum Physics Study"
    assert video_data["url"] == "https://www.youtube.com/watch?v=test_vid101"
    assert video_data["status"] in ("queued", "fetching")
    assert video_data["user_id"] == test_user["id"]
    assert video_data["metadata"]["youtube_id"] == "test_vid101"
    assert video_data["metadata"]["channel_title"] == "MIT OpenCourseWare"

    # Verify standard ingestion job was enqueued in jobs table
    created_vid = video_data["id"]
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM jobs WHERE job_type = 'video_pipeline' AND payload->>'video_id' = %s", (created_vid,))
            job = cur.fetchone()

    assert job is not None
    assert job["status"] == "queued"
    assert json.loads(job["payload"] if isinstance(job["payload"], str) else json.dumps(job["payload"]))["video_id"] == created_vid


def test_import_unmocked_get_video_preview_via_cache(client: TestClient, test_user, monkeypatch):
    """
    Regression test: Ensure import_discovery_video calls real get_video_preview
    and resolves cached video details without raising NameError or 500 error.
    """
    from core.youtube.cache import set_cached_video_details

    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    vid = "test_vid505"
    preview_data = {
        "video_id": vid,
        "title": "Unmocked Import Test Video",
        "channel_title": "MIT OpenCourseWare",
        "description": "Integration test description.",
        "thumbnail_url": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
        "published_at": "2024-03-01T12:00:00Z",
        "duration_s": 1800,
        "duration_formatted": "30:00",
        "is_embeddable": True,
        "has_captions": True,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "importable": True,
        "import_notice": None,
        "caption_notice": "Captions available.",
    }
    set_cached_video_details(vid, preview_data)

    # Execute import with REAL get_video_preview (no patch on get_video_preview)
    resp = client.post(
        "/api/v1/discovery/import",
        headers=test_user["headers"],
        json={"video_id": vid},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "Unmocked Import Test Video"
    assert data["url"] == f"https://www.youtube.com/watch?v={vid}"
    assert data["status"] in ("queued", "fetching", "processing", "ready_text")


# ============================================================================
# 9. Duplicate Video Import Deduplication
# ============================================================================

def test_api_discovery_import_deduplication(client: TestClient, test_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    with patch("apps.api.app.routes.discovery.get_video_preview", return_value=MOCK_PREVIEW_ITEM):
        # 1. First import
        r1 = client.post(
            "/api/v1/discovery/import",
            headers=test_user["headers"],
            json={"video_id": "test_vid101"},
        )
        assert r1.status_code == 201
        vid1 = r1.json()["id"]

        # 2. Second import of same video by same user
        r2 = client.post(
            "/api/v1/discovery/import",
            headers=test_user["headers"],
            json={"video_id": "https://www.youtube.com/watch?v=test_vid101"},
        )
        assert r2.status_code in (200, 201)
        vid2 = r2.json()["id"]

        # Deduplication must return the existing record ID
        assert vid1 == vid2

    # Verify exactly one video record exists for this user and video
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM videos WHERE user_id = %s AND metadata->>'youtube_id' = 'test_vid101'", (test_user["id"],))
            row = cur.fetchone()
    assert row["count"] == 1


# ============================================================================
# 9b. Concurrent Duplicate Import Serialization & Atomic Rollback
# ============================================================================

def test_concurrent_duplicate_discovery_imports(test_user, monkeypatch):
    """
    CHECK 1: Test that concurrent duplicate import requests from the same user
    for the same YouTube video ID serialize correctly via PostgreSQL advisory locks.
    Exactly one video record is created, exactly one job is queued, and both requests
    receive consistent responses (201 Created / 200 OK).
    """
    from apps.api.app.main import app
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    video_id = "test_vid202"
    preview_data = dict(MOCK_PREVIEW_ITEM)
    preview_data["video_id"] = video_id
    preview_data["url"] = f"https://www.youtube.com/watch?v={video_id}"

    def run_import():
        thread_client = TestClient(app)
        return thread_client.post(
            "/api/v1/discovery/import",
            headers=test_user["headers"],
            json={"video_id": video_id},
        )

    with patch("apps.api.app.routes.discovery.get_video_preview", return_value=preview_data):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(run_import)
            f2 = executor.submit(run_import)
            res1 = f1.result()
            res2 = f2.result()

    assert res1.status_code in (200, 201), res1.text
    assert res2.status_code in (200, 201), res2.text

    id1 = res1.json()["id"]
    id2 = res2.json()["id"]
    assert id1 == id2, f"Expected identical video IDs, got {id1} and {id2}"

    # Verify database state: exactly one video row and one job row
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS count FROM videos WHERE user_id = %s AND (url LIKE %s OR metadata->>'youtube_id' = %s)",
                (test_user["id"], f"%{video_id}%", video_id),
            )
            v_count = cur.fetchone()["count"]

            cur.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE payload->>'video_id' = %s",
                (id1,),
            )
            j_count = cur.fetchone()["count"]

    assert v_count == 1, f"Expected exactly 1 video record, found {v_count}"
    assert j_count == 1, f"Expected exactly 1 job record, found {j_count}"


def test_atomic_video_and_job_creation_rollback(client: TestClient, test_user, monkeypatch):
    """
    CHECK 2: Test that if background job creation fails during import,
    the transaction is rolled back completely. No orphaned video record remains.
    """
    import psycopg
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    video_id = "test_vid203"
    preview_data = dict(MOCK_PREVIEW_ITEM)
    preview_data["video_id"] = video_id
    preview_data["url"] = f"https://www.youtube.com/watch?v={video_id}"

    original_execute = psycopg.Cursor.execute

    def fail_on_job_insert(self, query, params=None):
        if "INSERT INTO jobs" in str(query):
            raise psycopg.DatabaseError("Simulated failure inserting job into jobs table")
        return original_execute(self, query, params)

    with patch("apps.api.app.routes.discovery.get_video_preview", return_value=preview_data):
        with patch.object(psycopg.Cursor, "execute", fail_on_job_insert):
            with pytest.raises(Exception):
                client.post(
                    "/api/v1/discovery/import",
                    headers=test_user["headers"],
                    json={"video_id": video_id},
                )

    # Verify in DB: transaction rollback left ZERO video rows and ZERO job rows
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS count FROM videos WHERE user_id = %s AND (url LIKE %s OR metadata->>'youtube_id' = %s)",
                (test_user["id"], f"%{video_id}%", video_id),
            )
            v_count = cur.fetchone()["count"]

            cur.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE payload->>'url' LIKE %s",
                (f"%{video_id}%",),
            )
            j_count = cur.fetchone()["count"]

    assert v_count == 0, f"Atomicity violation: orphaned video record was found in DB ({v_count} rows)"
    assert j_count == 0, f"Orphaned job record was found in DB ({j_count} rows)"


# ============================================================================
# 10. User Ownership and Security Isolation
# ============================================================================

def test_api_discovery_user_ownership_isolation(client: TestClient, test_user, other_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    # 1. User A imports the video
    with patch("apps.api.app.routes.discovery.get_video_preview", return_value=MOCK_PREVIEW_ITEM):
        r_user_a = client.post(
            "/api/v1/discovery/import",
            headers=test_user["headers"],
            json={"video_id": "test_vid101"},
        )
    assert r_user_a.status_code == 201
    vid_user_a = r_user_a.json()["id"]

    # 2. User B CANNOT access User A's video record
    r_forbidden = client.get(f"/api/v1/videos/{vid_user_a}", headers=other_user["headers"])
    assert r_forbidden.status_code == 404

    # 3. User B imports the same YouTube video -> gets their own video record
    with patch("apps.api.app.routes.discovery.get_video_preview", return_value=MOCK_PREVIEW_ITEM):
        r_user_b = client.post(
            "/api/v1/discovery/import",
            headers=other_user["headers"],
            json={"video_id": "test_vid101"},
        )
    assert r_user_b.status_code == 201
    vid_user_b = r_user_b.json()["id"]

    # Separate records with separate IDs
    assert vid_user_a != vid_user_b
    assert r_user_a.json()["user_id"] == test_user["id"]
    assert r_user_b.json()["user_id"] == other_user["id"]


# ============================================================================
# 11. Regression Compatibility with Existing Video Ingestion
# ============================================================================

def test_existing_video_url_ingestion_and_deduplication(client: TestClient, test_user):
    """
    Ensure existing POST /api/v1/videos endpoint remains 100% functional
    and properly deduplicates URLs.
    """
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # First call: creates video
    r1 = client.post(
        "/api/v1/videos",
        headers=test_user["headers"],
        json={"url": url, "title": "Never Gonna Give You Up"},
    )
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert data1["url"] == url
    assert data1["status"] in ("queued", "fetching", "processing", "ready_text")
    id1 = data1["id"]

    # Second call: deduplicates
    r2 = client.post(
        "/api/v1/videos",
        headers=test_user["headers"],
        json={"url": url, "title": "Never Gonna Give You Up Duplicate"},
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["id"] == id1


def test_concurrent_duplicate_url_imports(test_user):
    """
    Ensure concurrent URL import requests to POST /api/v1/videos serialize
    properly and create only 1 video record and 1 job.
    """
    from apps.api.app.main import app
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def run_url_import():
        thread_client = TestClient(app)
        return thread_client.post(
            "/api/v1/videos",
            headers=test_user["headers"],
            json={"url": url, "title": "Never Gonna Give You Up Concurrent"},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_url_import)
        f2 = executor.submit(run_url_import)
        res1 = f1.result()
        res2 = f2.result()

    assert res1.status_code == 200, res1.text
    assert res2.status_code == 200, res2.text

    id1 = res1.json()["id"]
    id2 = res2.json()["id"]
    assert id1 == id2

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS count FROM videos WHERE user_id = %s AND (url LIKE %s OR metadata->>'youtube_id' = 'dQw4w9WgXcQ')",
                (test_user["id"], "%dQw4w9WgXcQ%"),
            )
            v_count = cur.fetchone()["count"]

            cur.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE payload->>'video_id' = %s",
                (id1,),
            )
            j_count = cur.fetchone()["count"]

    assert v_count == 1
    assert j_count == 1


# ============================================================================
# 12. Quota Status API Endpoint
# ============================================================================

def test_api_discovery_quota_status(client: TestClient, test_user):
    resp = client.get("/api/v1/discovery/quota", headers=test_user["headers"])
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["timezone"] == "America/Los_Angeles"
    assert "date_pacific" in data
    assert "next_reset_pt" in data
    assert "search_calls_limit" in data
    assert data["search_calls_limit"] == 70
    assert data["videos_units_budget"] == 7000
