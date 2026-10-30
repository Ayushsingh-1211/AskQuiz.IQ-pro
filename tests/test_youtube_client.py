"""
Unit tests for YouTube Discovery backend client, quota manager, and caching.
"""

import json
import threading
from unittest.mock import MagicMock, patch
import httpx
import pytest

from apps.api.app.config import get_settings
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
    parse_iso_duration,
    search_youtube,
    validate_query,
)
from core.youtube.errors import (
    YouTubeAPIError,
    YouTubeDisabledError,
    YouTubeRateLimitError,
    YouTubeSearchQuotaError,
    YouTubeTimeoutError,
    YouTubeValidationError,
    YouTubeVideosQuotaError,
)
from core.youtube.quota import YouTubeQuotaManager, quota_manager


@pytest.fixture(autouse=True)
def setup_teardown_youtube():
    """Reset caches and quota counters before each test."""
    clear_cache()
    quota_manager.reset_for_testing()
    yield
    clear_cache()
    quota_manager.reset_for_testing()


# ============================================================================
# 1. Input Validation Tests
# ============================================================================

def test_validate_query_valid():
    assert validate_query("Linear Algebra") == "Linear Algebra"
    assert validate_query("  Python Tutorial  ") == "Python Tutorial"
    assert validate_query("C++ Programming & Data Structures") == "C++ Programming & Data Structures"


def test_validate_query_too_short():
    with pytest.raises(YouTubeValidationError, match="at least 2 characters"):
        validate_query("a")
    with pytest.raises(YouTubeValidationError, match="non-empty string"):
        validate_query("   ")


def test_validate_query_too_long():
    long_q = "x" * 105
    with pytest.raises(YouTubeValidationError, match="must not exceed 100 characters"):
        validate_query(long_q)


def test_validate_query_html_stripping():
    cleaned = validate_query("<script>alert(1)</script>Quantum Computing")
    assert cleaned == "Quantum Computing"

    with pytest.raises(YouTubeValidationError, match="no valid characters"):
        validate_query("<script></script>")


# ============================================================================
# 2. ISO 8601 Duration Parser Tests
# ============================================================================

def test_parse_iso_duration():
    # Minutes and seconds
    s, formatted = parse_iso_duration("PT15M33S")
    assert s == 933
    assert formatted == "15:33"

    # Hours, minutes, seconds
    s, formatted = parse_iso_duration("PT1H2M10S")
    assert s == 3730
    assert formatted == "1:02:10"

    # Seconds only
    s, formatted = parse_iso_duration("PT45S")
    assert s == 45
    assert formatted == "0:45"

    # Hours only
    s, formatted = parse_iso_duration("PT2H")
    assert s == 7200
    assert formatted == "2:00:00"

    # Zero seconds
    s, formatted = parse_iso_duration("PT0S")
    assert s == 0
    assert formatted == "0:00"

    # Invalid or empty
    assert parse_iso_duration("") == (0, "0:00")
    assert parse_iso_duration("invalid") == (0, "0:00")


# ============================================================================
# 3. Secure Configuration Tests
# ============================================================================

def test_missing_api_key_raises_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    with pytest.raises(YouTubeDisabledError, match="API key is not configured"):
        search_youtube("Calculus")


def test_disabled_feature_flag_raises_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "dummy_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", False)

    with pytest.raises(YouTubeDisabledError, match="feature is disabled"):
        search_youtube("Calculus")


# ============================================================================
# 4. Mocked Search Workflow & Video Cards
# ============================================================================

MOCK_SEARCH_RESPONSE = {
    "kind": "youtube#searchListResponse",
    "items": [
        {
            "id": {"kind": "youtube#video", "videoId": "vid_alg_101"},
            "snippet": {
                "publishedAt": "2024-01-01T00:00:00Z",
                "title": "Linear Algebra Basics &amp; Vectors",
                "description": "Learn vectors &amp; matrices.",
                "thumbnails": {
                    "high": {"url": "https://img.youtube.com/vi/vid_alg_101/hqdefault.jpg"},
                    "medium": {"url": "https://img.youtube.com/vi/vid_alg_101/mqdefault.jpg"},
                },
                "channelTitle": "3Blue1Brown",
            },
        },
        {
            "id": {"kind": "youtube#video", "videoId": "vid_alg_102"},
            "snippet": {
                "publishedAt": "2024-02-01T00:00:00Z",
                "title": "Matrix Transformations",
                "description": "Visual linear transformations.",
                "thumbnails": {
                    "high": {"url": "https://img.youtube.com/vi/vid_alg_102/hqdefault.jpg"},
                },
                "channelTitle": "Khan Academy",
            },
        },
    ],
}

MOCK_VIDEOS_RESPONSE = {
    "kind": "youtube#videoListResponse",
    "items": [
        {
            "id": "vid_alg_101",
            "contentDetails": {
                "duration": "PT15M30S",
                "caption": "true",
            },
            "status": {
                "embeddable": True,
            },
        },
        {
            "id": "vid_alg_102",
            "contentDetails": {
                "duration": "PT1H0M0S",
                "caption": "false",
            },
            "status": {
                "embeddable": False,
            },
        },
    ],
}


def test_search_youtube_success_mocked(monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "test_mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    def mock_get(url, params, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        if "search" in url:
            resp.json.return_value = MOCK_SEARCH_RESPONSE
        elif "videos" in url:
            resp.json.return_value = MOCK_VIDEOS_RESPONSE
        return resp

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = mock_get

    results = search_youtube("Linear Algebra", client=mock_client)

    assert len(results) == 2

    # Card 1: Embeddable with captions
    c1 = results[0]
    assert c1["video_id"] == "vid_alg_101"
    assert c1["title"] == "Linear Algebra Basics & Vectors"
    assert c1["channel_title"] == "3Blue1Brown"
    assert c1["duration_s"] == 930
    assert c1["duration_formatted"] == "15:30"
    assert c1["is_embeddable"] is True
    assert c1["has_captions"] is True
    assert c1["url"] == "https://www.youtube.com/watch?v=vid_alg_101"

    # Card 2: Non-embeddable without captions
    c2 = results[1]
    assert c2["video_id"] == "vid_alg_102"
    assert c2["title"] == "Matrix Transformations"
    assert c2["duration_s"] == 3600
    assert c2["duration_formatted"] == "1:00:00"
    assert c2["is_embeddable"] is False
    assert c2["has_captions"] is False


# ============================================================================
# 5. 24-Hour Caching Tests
# ============================================================================

def test_search_24h_caching_avoids_api_calls(monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "test_mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    call_count = {"search": 0, "videos": 0}

    def mock_get(url, params, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        if "search" in url:
            call_count["search"] += 1
            resp.json.return_value = MOCK_SEARCH_RESPONSE
        elif "videos" in url:
            call_count["videos"] += 1
            resp.json.return_value = MOCK_VIDEOS_RESPONSE
        return resp

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = mock_get

    # 1. First call: Cache miss, hits API
    res1 = search_youtube("Calculus Intro", client=mock_client)
    assert len(res1) == 2
    assert call_count["search"] == 1
    assert call_count["videos"] == 1

    # 2. Second call (identical query with different casing/spacing): Cache HIT
    res2 = search_youtube("   calculus   intro   ", client=mock_client)
    assert len(res2) == 2
    # Verify no additional API calls were made
    assert call_count["search"] == 1
    assert call_count["videos"] == 1


def test_video_details_cache_avoids_repeated_videos_calls(monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "test_mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    # Pre-populate details cache for vid_alg_101
    set_cached_video_details("vid_alg_101", {
        "duration_s": 930,
        "duration_formatted": "15:30",
        "is_embeddable": True,
        "has_captions": True,
    })

    videos_called_with_ids = []

    def mock_get(url, params, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        if "search" in url:
            resp.json.return_value = MOCK_SEARCH_RESPONSE
        elif "videos" in url:
            videos_called_with_ids.append(params["id"])
            resp.json.return_value = {
                "kind": "youtube#videoListResponse",
                "items": [
                    {
                        "id": "vid_alg_102",
                        "contentDetails": {"duration": "PT45M", "caption": "true"},
                        "status": {"embeddable": True},
                    }
                ],
            }
        return resp

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = mock_get

    results = search_youtube("Linear Algebra", client=mock_client)
    assert len(results) == 2

    # videos.list should only have been requested for vid_alg_102, not the cached vid_alg_101
    assert len(videos_called_with_ids) == 1
    assert videos_called_with_ids[0] == "vid_alg_102"


# ============================================================================
# 6. Quota Bucket Accounting & Limit Tests
# ============================================================================

def test_search_quota_bucket_limit_enforced(monkeypatch):
    """Bucket 1: 70 search calls per day limit."""
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "test_mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)
    monkeypatch.setattr(get_settings(), "YOUTUBE_SEARCH_DAILY_LIMIT", 3)

    # Simulate 3 search calls
    quota_manager.record_search_call()
    quota_manager.record_search_call()
    quota_manager.record_search_call()

    # 4th call must raise YouTubeSearchQuotaError
    with pytest.raises(YouTubeSearchQuotaError, match="YouTube search daily limit reached"):
        search_youtube("World History")


def test_videos_quota_budget_enforced(monkeypatch):
    """Bucket 2: 7,000 units budget."""
    monkeypatch.setattr(get_settings(), "YOUTUBE_VIDEOS_DAILY_BUDGET", 5)

    quota_manager.record_videos_call(units=5)

    with pytest.raises(YouTubeVideosQuotaError, match="YouTube videos daily budget reached"):
        quota_manager.check_videos_quota(units=1)


def test_quota_buckets_are_completely_independent(monkeypatch):
    """Confirm search calls do not deplete the videos budget and vice-versa."""
    monkeypatch.setattr(get_settings(), "YOUTUBE_SEARCH_DAILY_LIMIT", 70)
    monkeypatch.setattr(get_settings(), "YOUTUBE_VIDEOS_DAILY_BUDGET", 7000)

    # Record 70 searches
    for _ in range(70):
        quota_manager.record_search_call()

    status = quota_manager.get_quota_status()
    assert status["search_calls_used"] == 70
    assert status["search_calls_remaining"] == 0
    # Videos budget remains untouched
    assert status["videos_units_used"] == 0
    assert status["videos_units_remaining"] == 7000

    # Search raises quota error, but videos budget check passes
    with pytest.raises(YouTubeSearchQuotaError):
        quota_manager.check_search_quota()

    quota_manager.check_videos_quota(units=1)  # should not raise


def test_quota_pacific_rollover():
    """Verify that Pacific midnight date rollover automatically resets usage."""
    from datetime import datetime
    from core.youtube.quota import PACIFIC_TZ

    d1 = datetime(2024, 5, 10, 23, 0, 0, tzinfo=PACIFIC_TZ)
    quota_manager.record_search_call(current_pt_dt=d1)
    quota_manager.record_videos_call(10, current_pt_dt=d1)

    status1 = quota_manager.get_quota_status(current_pt_dt=d1)
    assert status1["search_calls_used"] == 1
    assert status1["videos_units_used"] == 10
    assert status1["date_pacific"] == "2024-05-10"

    # Simulate next day midnight PT (2024-05-11 00:00:00)
    d2 = datetime(2024, 5, 11, 0, 0, 0, tzinfo=PACIFIC_TZ)
    status2 = quota_manager.get_quota_status(current_pt_dt=d2)
    assert status2["search_calls_used"] == 0
    assert status2["videos_units_used"] == 0
    assert status2["date_pacific"] == "2024-05-11"
    assert status2["timezone"] == "America/Los_Angeles"


def test_dst_spring_forward_transition():
    """
    Daylight Saving Time transition: Spring Forward (PST -> PDT).
    On 2024-03-10, the day has 23 hours in America/Los_Angeles.
    Verifies that next reset is exactly 2024-03-11 00:00:00 PDT (23.0 elapsed hours).
    """
    from zoneinfo import ZoneInfo
    from datetime import datetime
    from core.youtube.quota import PACIFIC_TZ, calculate_next_reset

    # 1. Start of spring-forward day (midnight PST)
    d_spring_start = datetime(2024, 3, 10, 0, 0, 0, tzinfo=PACIFIC_TZ)
    reset_pt, reset_utc, seconds_remaining = calculate_next_reset(d_spring_start)

    assert reset_pt.strftime("%Y-%m-%d %H:%M:%S") == "2024-03-11 00:00:00"
    assert reset_pt.tzname() == "PDT"
    assert reset_utc.strftime("%Y-%m-%d %H:%M:%S") == "2024-03-11 07:00:00"
    # Physical elapsed time must be exactly 23 hours
    assert seconds_remaining == 23 * 3600

    # 2. End of spring-forward day (23:59:59 PDT)
    d_spring_end = datetime(2024, 3, 10, 23, 59, 59, tzinfo=PACIFIC_TZ)
    reset_pt, _, seconds_remaining = calculate_next_reset(d_spring_end)
    assert reset_pt.strftime("%Y-%m-%d %H:%M:%S") == "2024-03-11 00:00:00"
    assert seconds_remaining == 1

    # 3. Rollover simulation across spring-forward midnight
    quota_manager.record_search_call(current_pt_dt=d_spring_start)
    assert quota_manager.get_quota_status(current_pt_dt=d_spring_start)["search_calls_used"] == 1

    # Next day 00:00:00 PDT
    d_next_day = datetime(2024, 3, 11, 0, 0, 0, tzinfo=PACIFIC_TZ)
    status_next = quota_manager.get_quota_status(current_pt_dt=d_next_day)
    assert status_next["search_calls_used"] == 0
    assert status_next["date_pacific"] == "2024-03-11"


def test_dst_fall_back_transition():
    """
    Daylight Saving Time transition: Fall Back (PDT -> PST).
    On 2024-11-03, the day has 25 hours in America/Los_Angeles.
    Verifies that next reset is exactly 2024-11-04 00:00:00 PST (25.0 elapsed hours).
    """
    from zoneinfo import ZoneInfo
    from datetime import datetime
    from core.youtube.quota import PACIFIC_TZ, calculate_next_reset

    # 1. Start of fall-back day (midnight PDT)
    d_fall_start = datetime(2024, 11, 3, 0, 0, 0, tzinfo=PACIFIC_TZ)
    reset_pt, reset_utc, seconds_remaining = calculate_next_reset(d_fall_start)

    assert reset_pt.strftime("%Y-%m-%d %H:%M:%S") == "2024-11-04 00:00:00"
    assert reset_pt.tzname() == "PST"
    assert reset_utc.strftime("%Y-%m-%d %H:%M:%S") == "2024-11-04 08:00:00"
    # Physical elapsed time must be exactly 25 hours
    assert seconds_remaining == 25 * 3600

    # 2. End of fall-back day (23:59:59 PST)
    d_fall_end = datetime(2024, 11, 3, 23, 59, 59, tzinfo=PACIFIC_TZ)
    reset_pt, _, seconds_remaining = calculate_next_reset(d_fall_end)
    assert reset_pt.strftime("%Y-%m-%d %H:%M:%S") == "2024-11-04 00:00:00"
    assert seconds_remaining == 1

    # 3. Rollover simulation across fall-back midnight
    quota_manager.record_search_call(current_pt_dt=d_fall_start)
    assert quota_manager.get_quota_status(current_pt_dt=d_fall_start)["search_calls_used"] == 1

    # Next day 00:00:00 PST
    d_next_day = datetime(2024, 11, 4, 0, 0, 0, tzinfo=PACIFIC_TZ)
    status_next = quota_manager.get_quota_status(current_pt_dt=d_next_day)
    assert status_next["search_calls_used"] == 0
    assert status_next["date_pacific"] == "2024-11-04"


def test_quota_multi_process_persistence_and_locking(tmp_path):
    """
    Verify that multiple manager instances sharing the same quota file
    (simulating separate uvicorn worker processes) synchronize state via OS file locking.
    """
    quota_file = tmp_path / "proc_quota.json"
    mgr1 = YouTubeQuotaManager(quota_file=quota_file)
    mgr2 = YouTubeQuotaManager(quota_file=quota_file)

    # Process 1 records 5 searches
    for _ in range(5):
        mgr1.record_search_call()

    # Process 2 immediately reads disk under lock and sees 5 searches
    status2 = mgr2.get_quota_status()
    assert status2["search_calls_used"] == 5

    # Process 2 records 3 searches
    for _ in range(3):
        mgr2.record_search_call()

    # Process 1 immediately sees 8 searches
    status1 = mgr1.get_quota_status()
    assert status1["search_calls_used"] == 8


def test_quota_concurrent_multi_instance_locking(tmp_path):
    """
    Verify multi-threaded/multi-instance concurrent writes under OS file locking
    never drop updates or corrupt the JSON file.
    """
    quota_file = tmp_path / "concurrent_quota.json"

    def worker():
        local_mgr = YouTubeQuotaManager(quota_file=quota_file)
        for _ in range(10):
            local_mgr.record_search_call()
            local_mgr.record_videos_call(2)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final_mgr = YouTubeQuotaManager(quota_file=quota_file)
    status = final_mgr.get_quota_status()
    assert status["search_calls_used"] == 50
    assert status["videos_units_used"] == 100


def test_quota_real_subprocess_concurrency(tmp_path):
    """
    Launch genuine, independent OS processes using subprocess.Popen to verify that
    OS-level file locking (msvcrt on Windows, fcntl on POSIX) prevents race conditions
    and lost updates across true separate OS processes.
    """
    import subprocess
    import sys

    quota_file = tmp_path / "real_subprocess_quota.json"
    num_processes = 4
    iterations_per_process = 10

    worker_code = f"""
import sys
from pathlib import Path
from core.youtube.quota import YouTubeQuotaManager

mgr = YouTubeQuotaManager(quota_file=Path({repr(str(quota_file))}))
for _ in range({iterations_per_process}):
    mgr.record_search_call()
    mgr.record_videos_call(2)
"""

    processes = [
        subprocess.Popen(
            [sys.executable, "-c", worker_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(num_processes)
    ]

    for p in processes:
        stdout, stderr = p.communicate(timeout=20)
        assert p.returncode == 0, f"Subprocess failed with code {p.returncode}: {stderr.decode()}"

    final_mgr = YouTubeQuotaManager(quota_file=quota_file)
    status = final_mgr.get_quota_status()

    expected_searches = num_processes * iterations_per_process
    expected_video_units = num_processes * iterations_per_process * 2

    assert status["search_calls_used"] == expected_searches
    assert status["videos_units_used"] == expected_video_units


def test_quota_thread_safety():
    """Verify concurrency safety with multiple threads on a single manager."""
    def worker():
        for _ in range(10):
            quota_manager.record_search_call()
            quota_manager.record_videos_call(1)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    status = quota_manager.get_quota_status()
    assert status["search_calls_used"] == 50
    assert status["videos_units_used"] == 50


# ============================================================================
# 7. Error Mapping & Google API Errors
# ============================================================================

def test_google_quota_exceeded_error_mapping(monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "test_mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 403
    resp.json.return_value = {
        "error": {
            "code": 403,
            "message": "The request cannot be completed because you have exceeded your quota.",
            "errors": [{"reason": "quotaExceeded"}],
        }
    }

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = resp

    with pytest.raises(YouTubeSearchQuotaError, match="quota exceeded"):
        search_youtube("Physics", client=mock_client)


def test_rate_limit_error_mapping(monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "test_mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 429
    resp.json.return_value = {"error": {"message": "Rate limit exceeded."}}

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = resp

    with pytest.raises(YouTubeRateLimitError, match="rate limit"):
        search_youtube("Physics", client=mock_client)


def test_timeout_error_mapping(monkeypatch):
    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "test_mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = httpx.TimeoutException("Network timeout")

    with pytest.raises(YouTubeTimeoutError, match="timed out"):
        search_youtube("Physics", client=mock_client)


# ============================================================================
# 9. Single Video Preview and Cache Integration Tests
# ============================================================================

def test_get_video_preview_cache_and_unmocked_flow(monkeypatch):
    """
    Ensure get_video_preview correctly checks and updates cache via
    get_cached_video_details and set_cached_video_details without NameError.
    """
    from core.youtube.client import get_video_preview
    from core.youtube.cache import set_cached_video_details

    monkeypatch.setattr(get_settings(), "YOUTUBE_API_KEY", "test_mock_key")
    monkeypatch.setattr(get_settings(), "FEATURE_YOUTUBE_DISCOVERY", True)

    vid = "preview101a"

    cached_payload = {
        "video_id": vid,
        "title": "Quantum Mechanics in Depth",
        "channel_title": "MIT OpenCourseWare",
        "description": "Comprehensive course.",
        "thumbnail_url": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
        "published_at": "2024-03-01T12:00:00Z",
        "duration_s": 3600,
        "duration_formatted": "1:00:00",
        "is_embeddable": True,
        "has_captions": True,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "importable": True,
        "import_notice": None,
        "caption_notice": "Captions available.",
    }
    set_cached_video_details(vid, cached_payload)

    # Calling get_video_preview must retrieve from cache without NameError or HTTP call
    res = get_video_preview(vid)
    assert res["video_id"] == vid
    assert res["title"] == "Quantum Mechanics in Depth"
    assert res["is_embeddable"] is True
