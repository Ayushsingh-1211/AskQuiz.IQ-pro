# Project Changelog & Milestone History
> Purpose: Chronological ledger of all completed implementation milestones, incidents, bug fixes, and cloud deployment releases.
> Last updated: 2026-10-29 | Status: Current
> Derived from: Git log history, commit messages, and `STATUS.md`

## 1. Commit Log Summary

| Commit | Date | Summary | Key Files Modified |
|---|---|---|---|
| `cbed4c4` | 2026-10-22 | Fix Render Free 512MB RAM OOM: zero-model health checks, cloud-safe FTS retrieval, and early port binding | `apps/api/app/routes/health.py`, `core/retrieval.py`, `infra/Dockerfile` |
| `9770eb8` | 2026-10-22 | Update STATUS.md with Cloud Deployment Config verification | `STATUS.md` |
| `a501d9b` | 2026-10-22 | Fix deployment configs: Neon SSL resilience, Docker context, safe CORS and embedded worker lifespan | `apps/api/app/db/session.py`, `apps/api/app/main.py`, `render.yaml` |
| `efcf8c5` | 2026-10-22 | Configure zero-cost cloud deployment for Vercel, Render, and Neon | `DEPLOYMENT_GUIDE.md`, `render.yaml`, `apps/web/vercel.json` |
| `0940650` | 2026-10-20 | Initial clean import of AskQuiz.IQ scaffolding and specifications | Whole repository |

---

## 2. Milestone Journal (`STATUS.md`)

### Milestone M0: Foundation & Environment Setup `[VERIFIED]`
- **Scope:** Base Python project structure, Pydantic settings loading `.env`, database connection pooling, initial migration (`001_init.sql`), JWT login authentication, health self-checks, and Docker Compose with `pgvector`.
- **Gate:** `make db-up && make test && python infra/scripts/preflight.py` green.

### Milestone M1: Video Intake & Range Streaming `[VERIFIED]`
- **Scope:** Direct file upload (`POST /videos/upload`) and YouTube URL ingestion (`POST /videos`), SHA256 content deduplication, ffprobe duration validation, background job creation in `jobs` table, and HTTP 206 Partial Content Range streaming proxy.
- **Gate:** Playback with random seeking; video streaming verified.

### Milestone M2: Speech ASR, Chunking & Embeddings `[VERIFIED]`
- **Scope:** Database migration `002_chunks.sql` with vector(384) and tsvector, Faster-Whisper ASR with word-level timestamps, 15–20s chunk aggregation with 3s overlap, `intfloat/multilingual-e5-small` embeddings, and exact-word cut trimming.
- **Gate:** TAC unit tests pass; exact-word cut verified (`tests/test_tac.py`, `tests/test_chunking.py`).

### Milestone M3: Temporal Retrieval & Question Answering `[VERIFIED]`
- **Scope:** Reciprocal Rank Fusion hybrid retrieval (vector top 20 + FTS top 20 under TAC), Google Gemini provider with JSON mode, router fallback chain and daily caps, context pack assembly with short IDs, citation verification, and standard refusal generation.
- **Gate:** 10-question evaluation passes with `spoiler_leak = 0.0` (`eval/run_eval.py`).

### Milestone M4: Interactive Web UI `[VERIFIED]`
- **Scope:** React 18 TypeScript single-page application (Vite), video library grid, upload modal, Watch workspace, custom HTML5/YouTube player controls, `UnlockBar` visual spoiler boundary, `AskBox` input with auto-pause on focus and timestamp locking, and clickable citation chips.
- **Gate:** AskBox vitest unit tests pass (`apps/web/src/__tests__/askbox.test.tsx`), Vite clean production build.

### Milestone H: Cloudflare Tunnel & Remote Access `[VERIFIED]`
- **Scope:** Integrated `cloudflared` CLI tunnel to expose local backend and frontend securely, public smoke test script (`infra/scripts/public_smoke.py`).
- **Gate:** Public smoke test against live tunnel green.

### Release: Zero-Cost ($0) Production Cloud Deployment `[VERIFIED]`
- **Scope:** Complete deployment architecture across Vercel (React frontend), Render Free (FastAPI backend in Docker), and Neon Free (PostgreSQL + pgvector).
- **Hardening Enhancements:**
  1. *Render Memory Optimization:* Added lightweight zero-model health checks (`/api/v1/health`), cloud-safe FTS retrieval mode (`EMBEDDING_BACKEND=fts`), and disabled embedded worker (`EMBEDDED_WORKER=false`) to stay under 120MB RAM and prevent 512MB OOM termination.
  2. *Neon SSL Resilience:* Configured TCP keep-alives and retry decorators in `apps/api/app/db/session.py` to handle serverless pool timeouts gracefully.
  3. *Demo Auth Resilience:* Added dual login alias allowing both `demo` and `demo12345` for `demo@askquiz.iq`.
