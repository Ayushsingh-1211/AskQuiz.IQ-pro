# Configuration & Environment Variables Matrix
> Purpose: Exhaustive reference of every configuration flag, environment variable, default value, and validation rule.
> Last updated: 2026-10-29 | Status: Current
> Derived from: `apps/api/app/config.py`, `infra/.env.example`, `render.yaml`, `apps/web/.env.example`

## 1. Backend Configuration Reference (`Settings` in `apps/api/app/config.py`)

All backend configurations are managed by Pydantic Settings (`BaseSettings`), loading from `.env` and `infra/.env` with strict type validation.

| Variable Name | Type | Default Value | Where Used | Description & Operational Impact | Confidence |
|---|---|---|---|---|---|
| `LLM_PROVIDER` | `str` | `"gemini"` | `core/llm/` | Primary LLM provider identifier (`gemini` or `ollama`) | `[VERIFIED]` |
| `ANSWER_MODEL` | `str` | `""` (fallback `"gemini-2.5-flash"`) | `core/llm/gemini.py` | Model identifier used for text QA (e.g. `gemini-3.5-flash-lite`) | `[VERIFIED]` |
| `VISION_MODEL` | `str` | `""` | `core/llm/router.py` | Model identifier used for screen keyframe analysis | `[VERIFIED]` |
| `LLM_FALLBACK_CHAIN` | `str` | `""` | `core/llm/router.py` | Comma-separated list of models to try in sequence on failure or cap | `[VERIFIED]` |
| `GEMINI_API_KEY` | `str` | `""` | `core/llm/gemini.py` | Google AI Studio API key (never printed or exposed) | `[VERIFIED]` |
| `OLLAMA_URL` | `str` | `"http://localhost:11434"` | `core/llm/ollama.py` | Base endpoint URL for local Ollama daemon fallback | `[VERIFIED]` |
| `LLM_DAILY_CAP` | `int` | `0` | `core/llm/router.py` | Daily generation calls cap per model (`0` = no client cap) | `[VERIFIED]` |
| `DATABASE_URL` | `str` | `"postgresql://pause:pause@localhost:5432/pause"` | `apps/api/app/db/session.py` | PostgreSQL connection DSN (supports `sslmode=require` for Neon) | `[VERIFIED]` |
| `DATA_DIR` | `str` | `"./data"` | Storage, worker, API | Root directory on disk for video files, audio, subtitles, and caches | `[VERIFIED]` |
| `EMBEDDED_WORKER` | `bool` | `True` | `apps/api/app/main.py` | Runs background pipeline as a daemon thread inside API process | `[VERIFIED]` |
| `AUTO_SEED_DEMO` | `bool` | `True` | `apps/api/app/main.py` | Pre-seeds demo video and 25 chunks idempotently on boot | `[VERIFIED]` |
| `JWT_SECRET` | `str` | `"change-me"` | `apps/api/app/auth.py` | Secret key used for signing HS256 authentication tokens | `[VERIFIED]` |
| `JWT_ALGORITHM` | `str` | `"HS256"` | `apps/api/app/auth.py` | Cryptographic algorithm for JWT encoding/decoding | `[VERIFIED]` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `int` | `10080` (7 days) | `apps/api/app/auth.py` | Expiration lifetime for issued JWT access tokens | `[VERIFIED]` |
| `ALLOWED_ORIGINS` | `str` | `"http://localhost:5173"` | `apps/api/app/main.py` | Comma-separated CORS allowed origins | `[VERIFIED]` |
| `PUBLIC_API_URL` | `str` | `"http://localhost:8000"` | Logging, startup | Public facing base URL of the API service | `[VERIFIED]` |
| `FFMPEG_PATH` | `str` | `"ffmpeg"` | `videos.py`, `audio.py` | Path or binary name for FFmpeg executable | `[VERIFIED]` |
| `FFPROBE_PATH` | `str` | `"ffprobe"` | `videos.py` | Path or binary name for FFprobe media analyzer | `[VERIFIED]` |
| `TESSERACT_CMD` | `str` | `"tesseract"` | `health.py`, OCR | Command or absolute path to Tesseract OCR engine | `[VERIFIED]` |
| `WHISPER_MODEL` | `str` | `"small"` | `apps/worker/stages/asr.py` | Faster-Whisper model size (`small`, `tiny`, `base`) | `[VERIFIED]` |
| `WHISPER_COMPUTE` | `str` | `"int8"` | `apps/worker/stages/asr.py` | CTranslate2 computation precision (`int8`, `float16`, `float32`) | `[VERIFIED]` |
| `EMBEDDING_BACKEND` | `str` | `"local"` | `core/retrieval.py` | Retrieval engine: `"local"` (vector+FTS) or `"fts"` (cloud-safe FTS) | `[VERIFIED]` |
| `EMBED_MODEL` | `str` | `"intfloat/multilingual-e5-small"` | `core/embeddings.py` | HuggingFace model tag for dense text embeddings | `[VERIFIED]` |
| `RERANK_ENABLED` | `bool` | `False` | `core/retrieval.py` | Enables optional second-stage cross-encoder reranking | `[VERIFIED]` |
| `TOPK` | `int` | `8` | `core/context.py` | Maximum number of chunks passed to LLM context pack | `[VERIFIED]` |
| `CONTEXT_TOKEN_CAP` | `int` | `3500` | `core/context.py` | Upper token limit for prompt context (prevents context blowout) | `[VERIFIED]` |
| `RECENT_WINDOW_S` | `int` | `60` | `core/tac.py` | Standard recent speech window in seconds prior to `pause_t` | `[VERIFIED]` |
| `RECENT_WINDOW_WIDE_S` | `int` | `180` | `core/tac.py` | Expanded recent speech window if fewer than `min_words` found | `[VERIFIED]` |
| `RECENT_MIN_WORDS` | `int` | `20` | `core/tac.py` | Minimum spoken words required to avoid window widening | `[VERIFIED]` |
| `REFUSAL_SCORE_THRESHOLD` | `Optional[float]` | `0.5` | `core/answer.py` | Minimum retrieval score threshold before triggering refusal | `[VERIFIED]` |
| `ALIGN_TAU` | `Optional[float]` | `0.5` | `apps/worker/stages/align.py` | Document-to-video alignment cosine similarity threshold | `[VERIFIED]` |
| `VISION_CALLS_PER_VIDEO_CAP` | `int` | `100` | Screen processing | Hard ceiling on small-model vision calls per video | `[VERIFIED]` |
| `MAX_VIDEO_HOURS` | `int` | `3` | `videos.py` | Maximum acceptable video lecture length | `[VERIFIED]` |
| `MAX_UPLOAD_MB` | `int` | `2048` (2 GB) | `videos.py` | Maximum file upload size in megabytes | `[VERIFIED]` |
| `RATE_LIMIT_PER_MIN` | `int` | `30` | Rate limiter | Permitted API requests per minute per IP | `[VERIFIED]` |
| `YT_COOKIES_FILE` | `str` | `""` | `apps/worker/stages/fetch.py` | Path to Netscape cookies file for authenticated YouTube access | `[VERIFIED]` |
| `INTERVIEW_MAX_MINUTES` | `int` | `10` | Interview planner | Maximum duration for mock interview sessions | `[VERIFIED]` |
| `INTERVIEW_MAX_TURNS` | `int` | `8` | Interview planner | Maximum turns per mock interview in free tier | `[VERIFIED]` |
| `INTERVIEW_WEIGHTS` | `str` | `"technical:0.4,..."` | Interview scorecard | Weighted scorecard distribution for candidate answers | `[VERIFIED]` |

---

## 2. Frontend Configuration Reference (`apps/web/.env`)

Vite reads frontend environment variables prefixed with `VITE_`:

| Variable Name | Default Value | Where Used | Description | Confidence |
|---|---|---|---|---|
| `VITE_API_URL` | `""` (empty = relative `/`) | `apps/web/src/api/client.ts` | Target API backend URL (e.g. `https://askquiz-api.onrender.com`). No trailing slash. | `[VERIFIED]` |

---

## 3. Recommended Profiles

### Local Workstation Development (Laptop + Docker)
```env
LLM_PROVIDER=gemini
ANSWER_MODEL=gemini-3.5-flash-lite
VISION_MODEL=gemini-3.5-flash-lite
LLM_FALLBACK_CHAIN=gemini-3.5-flash-lite,gemini-3.5-flash,ollama
DATABASE_URL=postgresql://pause:pause@localhost:5432/pause
DATA_DIR=./data
EMBEDDING_BACKEND=local
EMBEDDED_WORKER=true
AUTO_SEED_DEMO=true
ALLOWED_ORIGINS=http://localhost:5173
```

### Zero-Cost Cloud Deployment (Render Free + Neon)
```env
DATABASE_URL=postgresql://neondb_owner:***@ep-xyz.aws.neon.tech/neondb?sslmode=require
EMBEDDING_BACKEND=fts
EMBEDDED_WORKER=false
AUTO_SEED_DEMO=true
WEB_CONCURRENCY=1
ALLOWED_ORIGINS=https://askquiz-iq.vercel.app,http://localhost:5173
ANSWER_MODEL=gemini-3.5-flash-lite
VISION_MODEL=gemini-3.5-flash-lite
LLM_FALLBACK_CHAIN=gemini-3.5-flash-lite,gemini-3.5-flash
DATA_DIR=/app/data
```
