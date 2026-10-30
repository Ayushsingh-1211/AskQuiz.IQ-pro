import io
import subprocess
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from apps.api.app.config import get_settings
from apps.api.app.main import app
from apps.worker.jobs import claim_and_execute_next_job
from apps.worker.stages.fetch import fetch_video

settings = get_settings()


@pytest.fixture(scope="session")
def sample_mp4(tmp_path_factory) -> Path:
    # Generate a tiny 1-second valid MP4 using ffmpeg
    out_dir = tmp_path_factory.mktemp("media")
    out_path = out_dir / "sample.mp4"
    cmd = [
        settings.resolved_ffmpeg_cmd(),
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=1",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(out_path),
    ]
    res = subprocess.run(cmd, capture_output=True, timeout=10)
    assert res.returncode == 0
    return out_path


def test_video_upload_and_dedupe(client: TestClient, test_user, sample_mp4: Path):
    headers = test_user["headers"]

    # 0. Clean up previous test lecture if present
    from apps.api.app.db.session import get_db_context
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM jobs WHERE job_type = 'video_pipeline' AND payload->>'video_id' IN (SELECT id::text FROM videos WHERE title LIKE 'Test Lecture%')")
            cur.execute("DELETE FROM videos WHERE title LIKE 'Test Lecture%'")
        conn.commit()

    # 1. Upload video
    with open(sample_mp4, "rb") as f:
        file_bytes = f.read()

    resp = client.post(
        "/api/v1/videos/upload",
        headers=headers,
        data={"title": "Test Lecture 1"},
        files={"file": ("test.mp4", io.BytesIO(file_bytes), "video/mp4")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    video_id = data["id"]
    assert data["title"] == "Test Lecture 1"
    assert data["status"] == "queued"
    assert data["stream_url"] is not None

    # 2. Upload same video -> Deduplication check
    resp_dup = client.post(
        "/api/v1/videos/upload",
        headers=headers,
        data={"title": "Duplicate Upload"},
        files={"file": ("test.mp4", io.BytesIO(file_bytes), "video/mp4")},
    )
    assert resp_dup.status_code == 200
    data_dup = resp_dup.json()
    assert data_dup["id"] == video_id  # Deduplicated to same video ID!

    # 3. Process the video with worker
    claimed = claim_and_execute_next_job()
    assert claimed is True

    # 4. Check video is now ready_text
    get_resp = client.get(f"/api/v1/videos/{video_id}", headers=headers)
    assert get_resp.status_code == 200
    vdata = get_resp.json()
    assert vdata["status"] == "ready_text"
    assert vdata["is_ready_text"] is True

    # 5. Test Range 206 streaming
    stream_url = vdata["stream_url"]
    range_resp = client.get(stream_url, headers={"Range": "bytes=0-99"})
    assert range_resp.status_code == 206
    assert range_resp.headers.get("Accept-Ranges") == "bytes"
    assert "bytes 0-99/" in range_resp.headers.get("Content-Range", "")
    assert len(range_resp.content) == 100


def test_blocked_youtube_fallback():
    # Test blocked / non-existent youtube URL triggers captions-only fallback
    dummy_url = "https://www.youtube.com/watch?v=non_existent_video_00000"
    path, meta = fetch_video("dummy_blocked_id", dummy_url, None)
    assert path is None
    assert meta.get("visual_unavailable") is True
    assert meta.get("fallback_notice") == "Upload the video file to enable screen understanding"
