"""
YouTube Data API v3 Quota Management.

Maintains two independent quota buckets:
1. Bucket 1: search.list fresh calls (application-level limit: 70 calls/day, leaving 30 as reserve).
2. Bucket 2: videos.list units (application-level budget: 7,000 units/day).

Features:
- Timezone: Daily rollover reset is pegged to midnight Pacific Time (America/Los_Angeles),
  matching Google's YouTube Data API quota reset schedule, with full IANA daylight saving (PST/PDT) support.
- Cross-process concurrency safety: OS-level file lock (msvcrt on Windows, fcntl on POSIX)
  coupled with in-process thread locking and atomic file writes (os.replace).
- Independent quota accounting: search and videos buckets are tracked and checked separately.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger
from core.youtube.errors import YouTubeSearchQuotaError, YouTubeVideosQuotaError

logger = get_logger("core.youtube.quota")

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


@contextmanager
def _interprocess_lock(lock_file: Path):
    """
    Cross-platform inter-process file lock without external dependencies.
    Uses msvcrt on Windows and fcntl on Unix.
    """
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_file, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            f.close()
        except Exception:
            pass


def get_pacific_now() -> datetime:
    """Return the current datetime localized in America/Los_Angeles."""
    return datetime.now(PACIFIC_TZ)


def calculate_next_reset(dt_pt: Optional[datetime] = None) -> Tuple[datetime, datetime, int]:
    """
    Calculate the next Pacific midnight reset given a Pacific datetime.
    Returns:
        - reset_pt: datetime at 00:00:00 Pacific Time of the next calendar day
        - reset_utc: equivalent datetime in UTC
        - seconds_remaining: physical elapsed seconds until reset
    Handles PST/PDT daylight saving transitions accurately.
    """
    if dt_pt is None:
        dt_pt = get_pacific_now()
    elif dt_pt.tzinfo is None:
        dt_pt = dt_pt.replace(tzinfo=PACIFIC_TZ)

    tomorrow = dt_pt.date() + timedelta(days=1)
    reset_pt = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=PACIFIC_TZ)
    reset_utc = reset_pt.astimezone(timezone.utc)
    dt_utc = dt_pt.astimezone(timezone.utc)
    seconds_remaining = max(0, int((reset_utc - dt_utc).total_seconds()))
    return reset_pt, reset_utc, seconds_remaining


class YouTubeQuotaManager:
    """
    Thread-safe and process-safe dual-bucket quota manager for YouTube Data API v3.
    """

    def __init__(self, quota_file: Optional[Path] = None):
        self._thread_lock = threading.Lock()
        self._quota_file = quota_file
        self._search_calls = 0
        self._videos_units = 0
        self._date = get_pacific_now().strftime("%Y-%m-%d")
        with self._thread_lock, self._file_lock_context():
            self._load_from_disk_unlocked()

    def _get_quota_file(self) -> Path:
        if self._quota_file is not None:
            return self._quota_file
        settings = get_settings()
        cache_dir = Path(settings.DATA_DIR) / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "youtube_quota.json"

    def _get_lock_file(self) -> Path:
        return self._get_quota_file().with_suffix(".lock")

    def _file_lock_context(self):
        return _interprocess_lock(self._get_lock_file())

    def _load_from_disk_unlocked(self, current_pt_dt: Optional[datetime] = None) -> None:
        """Read state from disk, applying Pacific rollover if date changed."""
        path = self._get_quota_file()
        pt_now = current_pt_dt or get_pacific_now()
        today_pt = pt_now.strftime("%Y-%m-%d")

        if path.exists():
            for _ in range(5):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    file_date = data.get("date")
                    if file_date == today_pt:
                        self._date = today_pt
                        self._search_calls = int(data.get("search_calls", 0))
                        self._videos_units = int(data.get("videos_units", 0))
                        return
                    elif file_date:
                        # File is from an older Pacific date -> reset for today_pt
                        self._date = today_pt
                        self._search_calls = 0
                        self._videos_units = 0
                        self._persist_to_disk_unlocked(pt_now)
                        return
                except (OSError, json.JSONDecodeError):
                    import time
                    time.sleep(0.01)

        # If date is different or file did not exist, rollover if needed
        if today_pt != self._date:
            self._date = today_pt
            self._search_calls = 0
            self._videos_units = 0
            self._persist_to_disk_unlocked(pt_now)

    def _persist_to_disk_unlocked(self, current_pt_dt: Optional[datetime] = None) -> None:
        """Persist state to disk safely under the acquired lock."""
        path = self._get_quota_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        pt_now = current_pt_dt or get_pacific_now()
        reset_pt, reset_utc, _ = calculate_next_reset(pt_now)

        data = {
            "date": self._date,
            "timezone": "America/Los_Angeles",
            "search_calls": self._search_calls,
            "videos_units": self._videos_units,
            "next_reset_pt": reset_pt.isoformat(),
            "next_reset_utc": reset_utc.isoformat(),
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        content = json.dumps(data, indent=2).encode("utf-8")
        for _ in range(5):
            try:
                path.write_bytes(content)
                break
            except OSError:
                import time
                time.sleep(0.01)

    def _sync_under_lock(self, current_pt_dt: Optional[datetime] = None) -> None:
        """Reload latest disk state to ensure cross-process visibility and check rollover."""
        self._load_from_disk_unlocked(current_pt_dt)

    # Bucket 1: search.list
    def check_search_quota(self, current_pt_dt: Optional[datetime] = None) -> None:
        """
        Verify search.list daily quota limit (70 calls/day) has not been reached.
        Raises YouTubeSearchQuotaError if at or over limit.
        """
        settings = get_settings()
        limit = settings.YOUTUBE_SEARCH_DAILY_LIMIT

        with self._thread_lock, self._file_lock_context():
            self._sync_under_lock(current_pt_dt)
            if self._search_calls >= limit:
                reset_pt, _, remaining_s = calculate_next_reset(current_pt_dt or get_pacific_now())
                hours_rem = remaining_s / 3600.0
                raise YouTubeSearchQuotaError(
                    f"YouTube search daily limit reached: {self._search_calls}/{limit} calls "
                    f"used for Pacific date {self._date}. Next reset at midnight PT "
                    f"({reset_pt.strftime('%Y-%m-%d %H:%M %Z')}, in {hours_rem:.1f}h). "
                    f"Reserve of 30 calls preserved."
                )

    def record_search_call(self, current_pt_dt: Optional[datetime] = None) -> int:
        """
        Atomically increment the search.list call counter and persist.
        Returns the updated call count for today.
        """
        with self._thread_lock, self._file_lock_context():
            self._sync_under_lock(current_pt_dt)
            self._search_calls += 1
            self._persist_to_disk_unlocked(current_pt_dt)
            logger.info(
                f"YouTube search.list call recorded. Today's Pacific usage ({self._date}): "
                f"{self._search_calls}/{get_settings().YOUTUBE_SEARCH_DAILY_LIMIT}"
            )
            return self._search_calls

    # Bucket 2: videos.list
    def check_videos_quota(self, units: int = 1, current_pt_dt: Optional[datetime] = None) -> None:
        """
        Verify videos.list daily units budget (7,000 units/day) has not been exhausted.
        Raises YouTubeVideosQuotaError if requested units exceed budget.
        """
        settings = get_settings()
        budget = settings.YOUTUBE_VIDEOS_DAILY_BUDGET

        with self._thread_lock, self._file_lock_context():
            self._sync_under_lock(current_pt_dt)
            if self._videos_units + units > budget:
                reset_pt, _, remaining_s = calculate_next_reset(current_pt_dt or get_pacific_now())
                hours_rem = remaining_s / 3600.0
                raise YouTubeVideosQuotaError(
                    f"YouTube videos daily budget reached: {self._videos_units}/{budget} units "
                    f"used for Pacific date {self._date}. Cannot allocate {units} more unit(s). "
                    f"Next reset at midnight PT ({reset_pt.strftime('%Y-%m-%d %H:%M %Z')}, in {hours_rem:.1f}h)."
                )

    def record_videos_call(self, units: int = 1, current_pt_dt: Optional[datetime] = None) -> int:
        """
        Atomically increment the videos.list units counter and persist.
        Returns the updated units count for today.
        """
        with self._thread_lock, self._file_lock_context():
            self._sync_under_lock(current_pt_dt)
            self._videos_units += units
            self._persist_to_disk_unlocked(current_pt_dt)
            logger.info(
                f"YouTube videos.list units ({units}) recorded. Today's Pacific usage ({self._date}): "
                f"{self._videos_units}/{get_settings().YOUTUBE_VIDEOS_DAILY_BUDGET}"
            )
            return self._videos_units

    def get_quota_status(self, current_pt_dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Return current quota utilization status for both buckets."""
        settings = get_settings()
        pt_now = current_pt_dt or get_pacific_now()
        with self._thread_lock, self._file_lock_context():
            self._sync_under_lock(pt_now)
            search_limit = settings.YOUTUBE_SEARCH_DAILY_LIMIT
            videos_budget = settings.YOUTUBE_VIDEOS_DAILY_BUDGET
            reset_pt, reset_utc, seconds_remaining = calculate_next_reset(pt_now)

            return {
                "date_pacific": self._date,
                "timezone": "America/Los_Angeles",
                "next_reset_pt": reset_pt.isoformat(),
                "next_reset_utc": reset_utc.isoformat(),
                "seconds_until_reset": seconds_remaining,
                "search_calls_used": self._search_calls,
                "search_calls_limit": search_limit,
                "search_calls_remaining": max(0, search_limit - self._search_calls),
                "videos_units_used": self._videos_units,
                "videos_units_budget": videos_budget,
                "videos_units_remaining": max(0, videos_budget - self._videos_units),
            }

    def reset_for_testing(self) -> None:
        """Reset counters and remove persisted test files (for automated tests)."""
        with self._thread_lock, self._file_lock_context():
            self._search_calls = 0
            self._videos_units = 0
            self._date = get_pacific_now().strftime("%Y-%m-%d")
            try:
                path = self._get_quota_file()
                if path.exists():
                    path.unlink(missing_ok=True)
            except Exception:
                pass


# Global singleton instance
quota_manager = YouTubeQuotaManager()
