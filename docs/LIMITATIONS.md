# System Limitations, Gaps & Technical Debt
> Purpose: Honest register of implemented shortcuts, memory ceilings, edge cases, and unimplemented milestones.
> Last updated: 2026-10-29 | Status: Current
> Derived from: Code inspection, `STATUS.md`, `DEPLOYMENT_GUIDE.md`, test runs

## 1. What is NOT Built (Honest Gap Analysis)

While the core **Pause & Ask** experience, TAC temporal enforcement, speech transcription, hybrid/FTS retrieval, and citation verification are fully operational, several components planned in the Master Specification exist only as stubs or placeholders:

| Feature / Module | Spec Ref | File Stubs | Status | What is Missing |
|---|---|---|---|---|
| **Screen Frame Extraction & OCR** | `spec/P3.md` (M5) | `apps/worker/stages/frames.py`, `ocr.py`, `vision.py` | `[PLANNED]` | Sub-sampling video at 2s intervals, perceptual hashing (pHash) for scene change detection, Tesseract OCR extraction on frames, and small-model vision descriptions. |
| **Document Ingestion & Timeline Alignment** | `spec/P4.md` (M6) | `apps/worker/stages/docs.py`, `align.py`, `routes/documents.py`, `DocUpload.tsx` | `[PLANNED]` | PDF text extraction via PyMuPDF, PPT slide/notes extraction via python-pptx, and cosine alignment ($\tau \ge 0.5$) to reveal document pages only when the instructor introduces them. |
| **Standalone Quiz Generator** | `spec/P7.md` (M7) | `core/quiz.py`, `routes/quiz.py`, `QuizPanel.tsx` | `[PLANNED]` | Dynamic multiple-choice check question generator with source-chunk validation and interactive quiz widget. (QuickAction "🎯 Quiz me" currently uses standard conversational prompt). |
| **Progressive Lecture Summaries** | `spec/P5.md`, `P6.md` | `core/summary.py`, `routes/summary.py` | `[PLANNED]` | 5-minute precomputed sliding summaries under TAC. (QuickAction "📝 Summarize so far" operates via conversational QA prompt). |
| **Adaptive Mock Interview Simulator** | `spec/P11.md` (M8) | `core/interview/`, `routes/interviews.py`, `InterviewSetup.tsx`, `InterviewLive.tsx`, `Scorecard.tsx`, `003_interview.sql` | `[PLANNED]` | State machine for multi-turn technical interviews, scoring across 4 dimensions (Technical, Communication, Problem Solving, Structure), quote extraction, and explained scorecard generation. |
| **Full 40-Question Benchmark** | `spec/P10.md` (M9) | `eval/questions.json` | `[PARTIAL]` | 10 temporal boundary questions are fully labelled and pass with `spoiler_leak = 0.0`. 30 additional diverse scenario questions remain to be authored. |

---

## 2. Infrastructure & Hardware Limitations

### A. Render Free 512MB RAM Ceiling `[VERIFIED: DEPLOYMENT_GUIDE.md]`
- **Limitation:** Render Free web instances enforce a strict 512 MB memory limit.
- **Impact on Heavy Processing:** Running local ML models (Faster-Whisper ASR, SentenceTransformer PyTorch embeddings, and OpenCV) requires between 800 MB and 1.5 GB RAM. Executing the worker on raw uploaded video files inside Render Free triggers an immediate Out-Of-Memory termination (`SIGKILL 137`).
- **Mitigation / Architecture:**
  1. `EMBEDDED_WORKER=false` and `EMBEDDING_BACKEND=fts` are set in production cloud configurations.
  2. The web API runs at $\approx 100\text{ MB}$ RAM using native PostgreSQL Full-Text Search.
  3. The demo lecture video and its 25 chunks are pre-seeded via `AUTO_SEED_DEMO=true`.
  4. Newly uploaded video files on the free cloud instance are safely queued in PostgreSQL `jobs` table but cannot be processed by the free web container. To process fresh uploads, a separate local worker or paid container instance must be connected to the database.

### B. Local Database Connection Dependency for Test Suites `[VERIFIED]`
- **Limitation:** Running full integration tests (`test_auth.py`, `test_api_ask.py`) requires a live PostgreSQL instance. If Docker is stopped, `psycopg_pool` blocks for 30 seconds before timing out with `psycopg_pool.PoolTimeout`.
- **Mitigation:** Pure unit tests (`test_tac.py`, `test_verifier.py`, `test_chunking.py`) are fully decoupled from database fixtures and pass cleanly in $<15\text{s}$.

---

## 3. Known Shortcuts & Technical Debt

1. **Dual Demo Password Alias:**
   - *File:* `apps/api/app/auth.py#L81`
   - *Detail:* The demo user account `demo@askquiz.iq` explicitly allows authentication with either `demo12345` or `demo`.
   - *Rationale:* Eliminates presenter login friction during live demonstrations.
2. **Hardcoded Demo Video UUID Fallback:**
   - *File:* `apps/api/app/routes/videos.py#L292`, `L307`
   - *Detail:* Video UUID `1ba5b57f-4aad-489d-9948-3d6ab873055e` has hardcoded fallback paths mapping directly to `eval/dataset/talking_teacher.mp4` and `eval/dataset/talking_teacher.en.srt` if database file paths are unreadable.
   - *Rationale:* Guarantees that the seeded demo lecture always plays and streams regardless of container directory mount idiosyncrasies.
3. **In-Memory Cache Volatility:**
   - *File:* `core/cache.py`
   - *Detail:* The content-hash cache for LLM outputs is currently stored in a Python process dictionary. If the API process restarts or spins down on idle (Render Free sleep), the in-memory cache resets.
4. **YouTube Bot Detection Sensitivity:**
   - *File:* `apps/worker/stages/fetch.py`
   - *Detail:* Rapid sequential requests to YouTube via `yt-dlp` from cloud IP ranges occasionally trigger YouTube's bot challenge. The worker mitigates this by flagging `visual_unavailable=true` and falling back to transcript captions.
