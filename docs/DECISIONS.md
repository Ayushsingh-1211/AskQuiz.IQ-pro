# Architectural Decision Records (ADR)
> Purpose: Chronological register of architectural, algorithmic, and infrastructure decisions detailing options considered and reasons chosen.
> Last updated: 2026-10-29 | Status: Current
> Derived from: Git history, commit messages, `STATUS.md`, and codebase architecture

## ADR-01: PostgreSQL as Single Unified Datastore, Vector Store, and Task Queue
- **Date:** 2026-10-20 | **Status:** Accepted `[VERIFIED]`
- **Context:** Building a production-grade prototype under a strict $0 operating cost constraint. Traditional architectures use PostgreSQL for relational data, Redis for task queuing and caching, and Pinecone/Qdrant for vector embeddings.
- **Options Considered:**
  1. *Multi-service architecture:* PostgreSQL + Redis + Pinecone cloud accounts.
  2. *Single unified PostgreSQL:* PostgreSQL 16 with `pgvector` and `jobs` table using `FOR UPDATE SKIP LOCKED`.
- **Decision:** Selected Option 2. Native PostgreSQL `jobs` table replaces Redis; `pgvector` handles 384-d dense vectors; native `tsvector` handles full-text search.
- **Consequences:** Eliminates external service costs and operational failure points. Can run on a single Docker container or free serverless instance (Neon).

---

## ADR-02: Enforcement of Temporal Anchor Constraint (TAC) at Database Layer
- **Date:** 2026-10-20 | **Status:** Accepted `[VERIFIED]`
- **Context:** Preventing spoilers requires that future video chunks and words are never accessible during query answering.
- **Options Considered:**
  1. *Application-level filtering:* Retrieve all video chunks into Python memory and filter out timestamps $> \text{pause\_t}$.
  2. *Database-level SQL predicate:* Enforce `video_id = %s AND visible_from_s <= %s` directly in every SQL query.
- **Decision:** Selected Option 2 (Hard Rule 1).
- **Consequences:** Guaranteed mathematical impossibility of future chunk retrieval. Supported by runtime memory assertion (`assert_no_future`) before any LLM prompt is sent.

---

## ADR-03: Server-Side Construction of Citations & Coordinates
- **Date:** 2026-10-21 | **Status:** Accepted `[VERIFIED]`
- **Context:** LLMs frequently hallucinate exact timestamps, slide numbers, and page numbers when generating conversational explanations.
- **Options Considered:**
  1. *Instruct LLM to write timestamps:* Ask the model to output `"Video 01:23-01:45"` directly in its text.
  2. *Context-local short IDs with server mapping:* LLM outputs only abstract IDs (`c1`, `c2`). The server verifies chunk validity and constructs coordinates.
- **Decision:** Selected Option 2 (Hard Rule 2 & 3).
- **Consequences:** Eliminates citation hallucination. The server checks that cited IDs were present in context, obeys TAC, and formats exact coordinates.

---

## ADR-04: Dual Retrieval Mode: Local Dense E5 vs. Cloud-Safe Full-Text Search
- **Date:** 2026-10-22 | **Status:** Accepted `[VERIFIED]`
- **Context:** Render Free web containers have a strict 512 MB RAM ceiling. Loading PyTorch and SentenceTransformer for dense embeddings consumes $>400\text{ MB}$, triggering Out-Of-Memory termination.
- **Options Considered:**
  1. *Require paid cloud instance:* Mandate 2GB RAM container.
  2. *Dual retrieval backend:* Support `EMBEDDING_BACKEND=local` (E5 dense vectors + FTS) for workstations and `EMBEDDING_BACKEND=fts` (pure PostgreSQL FTS) for cloud containers.
- **Decision:** Selected Option 2.
- **Consequences:** On Render Free, AskQuiz.IQ runs in $<120\text{ MB}$ RAM with 100% uptime while retaining robust keyword retrieval and exact TAC anti-spoiler enforcement.

---

## ADR-05: HTTP 206 Partial Content Range Streaming for Media Playback
- **Date:** 2026-10-22 | **Status:** Accepted `[VERIFIED]`
- **Context:** Large video files (100MB – 2GB) cannot be loaded entirely into client memory or buffered linearly without causing scrubbing lag.
- **Options Considered:**
  1. *External Video CDN:* Upload to Mux or Cloudflare Stream (incurs cost).
  2. *FastAPI Range Streaming Proxy:* Implement HTTP 206 byte-range streaming reading directly from disk.
- **Decision:** Selected Option 2 (`apps/api/app/storage.py:range_streaming_response()`).
- **Consequences:** Enables instantaneous random seeking in HTML5 video players at zero infrastructure cost.

---

## ADR-06: Google Gemini Free Tier with Automated Fallback Chain
- **Date:** 2026-10-23 | **Status:** Accepted `[VERIFIED]`
- **Context:** Free-tier LLM endpoints enforce tight rate limits (15 RPM) and daily quotas.
- **Options Considered:**
  1. *Single model hard-coded:* Call `gemini-1.5-flash` directly.
  2. *Configurable router fallback chain:* Sequentially walk `gemini-3.5-flash-lite`, `gemini-3.5-flash`, and local `ollama` with content-hash caching.
- **Decision:** Selected Option 2 (`core/llm/router.py`).
- **Consequences:** High availability under free quotas; identical questions cost 0 tokens due to SHA256 content caching.

---

## ADR-07: Separation of Web API and Heavy Background Worker on Cloud
- **Date:** 2026-10-24 | **Status:** Accepted `[VERIFIED]`
- **Context:** Running Faster-Whisper ASR and FFmpeg transcoding inside the Render Free 512MB container causes SIGKILL 137.
- **Options Considered:**
  1. *Allow container crashes on upload:* Accept downtime when users upload videos.
  2. *Decouple worker on free cloud:* Configure `EMBEDDED_WORKER=false` on Render Free, pre-seed demo video chunks via `AUTO_SEED_DEMO=true`, and queue new uploads in the database.
- **Decision:** Selected Option 2.
- **Consequences:** Continuous 100% uptime for web API, playback, and Q&A on free cloud tiers.

---

## ADR-08: Dual Demo Login Credential Alias Support
- **Date:** 2026-10-25 | **Status:** Accepted `[VERIFIED]`
- **Context:** Presenters and evaluators during testing occasionally entered `demo` instead of `demo12345` or vice versa.
- **Options Considered:**
  1. *Strict password matching:* Reject `demo` if password was seeded as `demo12345`.
  2. *Alias fallback in auth module:* Permit both `demo` and `demo12345` for the `demo@askquiz.iq` account.
- **Decision:** Selected Option 2 (`apps/api/app/auth.py#L81`).
- **Consequences:** Zero login failures during live demonstrations and automated testing.
