# REST API Specification & Endpoint Contracts
> Purpose: Complete reference of all HTTP REST endpoints, request/response models, authentication schemes, and status codes.
> Last updated: 2026-10-29 | Status: Current
> Derived from: `apps/api/app/routes/`, `apps/api/app/schemas/`, `apps/api/app/errors.py`, `spec/API.md`

## 1. Authentication & Common Conventions

### Authentication Headers
All protected endpoints require a signed JSON Web Token passed in the standard `Authorization` header:
```http
Authorization: Bearer <access_token>
```

### Stream Token Authentication
For media streaming elements (HTML5 `<video>` tags), authentication can also be provided as a URL query parameter:
```http
GET /api/v1/videos/{video_id}/stream?token=<signed_token>
```

### Standard Error Schema `[VERIFIED: apps/api/app/errors.py]`
Every 4xx and 5xx error response returns a structured JSON payload:
```json
{
  "code": "UNAUTHORIZED | NOT_FOUND | VALIDATION_ERROR | FORBIDDEN | RATE_LIMITED | INTERNAL_ERROR",
  "message": "Human readable explanation of the failure",
  "hint": "Optional actionable advice on how to fix or avoid the error",
  "request_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
}
```

---

## 2. Implemented Endpoints

### A. Authentication

#### `POST /api/v1/auth/login`
Authenticates a user and issues a bearer access token.
- **Auth required:** No
- **Request Body:**
  ```json
  {
    "email": "demo@askquiz.iq",
    "password": "demo12345"
  }
  ```
- **Responses:**
  - `200 OK`:
    ```json
    {
      "access_token": "eyJhbGciOi...",
      "token_type": "bearer",
      "user": {
        "id": "e2c6cd67-45b8-4253-b51f-8e7752f2cefb",
        "email": "demo@askquiz.iq",
        "full_name": "Demo User",
        "is_active": true
      }
    }
    ```
  - `401 Unauthorized`: Invalid password or inactive account.

---

### B. Health & Diagnostics

#### `GET /api/v1/health`
Zero-model lightweight health check for load balancers and cloud monitors.
- **Auth required:** No
- **Responses:**
  - `200 OK`:
    ```json
    {
      "status": "ok",
      "database": true,
      "embedding_backend": "fts"
    }
    ```
  - `503 Service Unavailable`: Database unreachable.

#### `GET /api/v1/diagnostics`
Detailed environment checks (ffmpeg, ffprobe, tesseract, database, data directory, Gemini key).
- **Auth required:** No
- **Responses:**
  - `200 OK` / `503 Service Unavailable`:
    ```json
    {
      "status": "ok",
      "checks": {
        "ffmpeg": {"ok": true, "detail": "ffmpeg version 6.1.1"},
        "ffprobe": {"ok": true, "detail": "ffprobe version 6.1.1"},
        "tesseract": {"ok": true, "langs": ["eng", "hin"]},
        "database": {"ok": true},
        "data_dir": {"ok": true, "path": "/app/data"},
        "gemini_key": {"ok": true, "detail": "configured"},
        "embed_model": {"ok": true, "backend": "fts", "model": "none"}
      }
    }
    ```

#### `GET /health` and `GET /`
Root level fast health pings for cloud platforms (e.g. Render port detectors).
- **Auth required:** No
- **Response:** `{"status": "ok"}`

---

### C. Videos & Media Ingestion

#### `POST /api/v1/videos/upload`
Uploads a local media file (MP4, MKV, WebM) and initiates background ingestion.
- **Auth required:** Yes (Bearer)
- **Content-Type:** `multipart/form-data`
- **Form Parameters:**
  - `file`: Binary file upload (max `MAX_UPLOAD_MB` = 2048 MB).
  - `title` *(optional)*: Display title.
- **Responses:**
  - `200 OK`: `VideoOut` schema (status `'queued'`).
  - `422 Unprocessable Entity`: Exceeds file size or duration limit.

#### `POST /api/v1/videos`
Registers a video via external URL (YouTube).
- **Auth required:** Yes (Bearer)
- **Request Body:**
  ```json
  {
    "url": "https://www.youtube.com/watch?v=kCc8FmEb1nY",
    "title": "Machine Learning Overview"
  }
  ```
- **Responses:**
  - `200 OK`: `VideoOut` schema.

#### `GET /api/v1/videos`
Lists all video lectures belonging to the authenticated user.
- **Auth required:** Yes (Bearer)
- **Responses:**
  - `200 OK`:
    ```json
    {
      "items": [
        {
          "id": "1ba5b57f-4aad-489d-9948-3d6ab873055e",
          "user_id": "e2c6cd67-45b8-4253-b51f-8e7752f2cefb",
          "title": "Talking Teacher - Machine Learning Intro",
          "url": null,
          "duration_s": 240.5,
          "status": "ready_text",
          "visual_unavailable": false,
          "stream_url": "/api/v1/videos/1ba5b57f.../stream?token=...",
          "is_ready_text": true,
          "is_ready_full": false,
          "created_at": "2026-10-22T01:27:00Z"
        }
      ],
      "total": 1
    }
    ```

#### `GET /api/v1/videos/{video_id}`
Retrieves metadata and processing state of a specific video.
- **Auth required:** Yes (Bearer)
- **Responses:** `200 OK` (`VideoOut`) or `404 Not Found`.

#### `GET /api/v1/videos/{video_id}/stream`
Streams media asset using HTTP 206 Partial Content byte ranges.
- **Auth required:** Bearer token or `?token=<stream_token>` query parameter.
- **Headers Sent:** `Range: bytes=0-1048575`
- **Responses:**
  - `206 Partial Content`: Stream binary chunk with headers:
    - `Content-Range: bytes 0-1048575/52428800`
    - `Accept-Ranges: bytes`
    - `Content-Type: video/mp4`
  - `403 Forbidden`: Invalid or missing stream token.
  - `404 Not Found`: Media not yet generated.

#### `GET /api/v1/videos/{video_id}/captions`
Returns subtitles in WebVTT format for browser closed captions.
- **Auth required:** No
- **Responses:**
  - `200 OK`: `text/vtt` payload.
  - Generates dynamically from PostgreSQL speech chunks if no physical `.vtt` file exists on disk.

---

### D. Temporal Question Answering

#### `POST /api/v1/videos/{video_id}/ask`
Core Pause & Ask endpoint. Submits a user query under strict TAC temporal boundary.
- **Auth required:** Yes (Bearer)
- **Request Body:**
  ```json
  {
    "query": "What is supervised learning?",
    "pause_t": 120.0,
    "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
  }
  ```
- **Responses:**
  - `200 OK`:
    ```json
    {
      "answer": "Supervised learning uses labeled training datasets to learn mapping functions from inputs to outputs.",
      "citations": [
        {
          "chunk_id": "7f8b3c2d-1111-2222-3333-444455556666",
          "text": "Supervised learning requires labeled training data...",
          "source_ref": {
            "source_type": "speech",
            "chunk_id": "7f8b3c2d-1111-2222-3333-444455556666",
            "timestamp_s": 15.2,
            "timestamp_formatted": "00:15",
            "page_number": null,
            "slide_number": null,
            "label": "Video 00:15-00:32"
          }
        }
      ],
      "used_pause_frame": false,
      "confidence": "high",
      "refusal": false,
      "notes": "",
      "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "pause_t": 120.0
    }
    ```
  - `200 OK` (Refusal):
    ```json
    {
      "answer": "This isn't covered in the material up to 00:10.",
      "citations": [],
      "used_pause_frame": false,
      "confidence": "high",
      "refusal": true,
      "session_id": "...",
      "pause_t": 10.0
    }
    ```
  - `404 Not Found`: Video not found.
  - `422 Unprocessable Entity`: Empty query string.

---

## 3. Planned / Unimplemented Endpoints `[PLANNED: spec/API.md]`

The following endpoints are defined in `spec/API.md` and have stubs or milestone specifications, but are not yet fully implemented:

| Method | Endpoint | Milestone | Purpose | Status |
|---|---|---|---|---|
| `POST` | `/api/v1/videos/{id}/documents` | M6 (`spec/P4.md`) | Ingest PDF/PPT lecture notes aligned to timeline | `[PLANNED: routes/documents.py]` |
| `POST` | `/api/v1/videos/{id}/quiz` | M7 (`spec/P7.md`) | Generate dynamic grounded quizzes based on progress | `[PLANNED: routes/quiz.py]` |
| `GET` | `/api/v1/videos/{id}/summary?t=` | M7 (`spec/P5.md`) | Retrieve TAC-safe progressive lecture summary | `[PLANNED: routes/summary.py]` |
| `POST` | `/api/v1/interviews` | M8 (`spec/P11.md`) | Initialize adaptive mock interview based on watched content | `[PLANNED: routes/interviews.py]` |
| `POST` | `/api/v1/interviews/{id}/answer` | M8 (`spec/P11.md`) | Submit candidate response and receive turn feedback | `[PLANNED: routes/interviews.py]` |
| `POST` | `/api/v1/interviews/{id}/finish` | M8 (`spec/P11.md`) | Conclude interview and compute explained scorecard | `[PLANNED: routes/interviews.py]` |
| `GET` | `/api/v1/interviews/estimate?minutes=` | M8 (`spec/P11.md`) | Estimate LLM token pricing for interview duration | `[PLANNED: routes/interviews.py]` |
