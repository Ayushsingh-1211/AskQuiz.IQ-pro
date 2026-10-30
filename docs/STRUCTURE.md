# Repository Structure & File Map
> Purpose: Complete filesystem directory tree and map documenting every significant file and its concrete responsibility.
> Last updated: 2026-10-29 | Status: Current
> Derived from: AskQuiz.IQ repository scan

## 1. Directory Tree Map

```
AskQuiz.IQ/
├── apps/                              # User-facing applications (Frontend, API, Worker)
│   ├── api/                           # FastAPI web service
│   │   └── app/
│   │       ├── auth.py                # JWT creation, decoding, bcrypt password verification, login route
│   │       ├── config.py              # Central Pydantic Settings class loading all env keys
│   │       ├── deps.py                # FastAPI dependency injection (current user, database session)
│   │       ├── errors.py              # Custom AppException hierarchy and global error handlers
│   │       ├── logging.py             # Structured JSON logger with contextual X-Request-ID
│   │       ├── main.py                # FastAPI app initialization, lifespan, CORS, and worker thread
│   │       ├── storage.py             # File path resolution, stream token signing, HTTP 206 Range streamer
│   │       ├── db/                    # Database connection pooling and migration runner
│   │       │   ├── session.py         # Psycopg 3 connection pool and migration execution
│   │       │   └── migrations/        # Ordered SQL migration files (001, 002, 003)
│   │       ├── routes/                # HTTP endpoint definitions
│   │       │   ├── ask.py             # POST /videos/{id}/ask core temporal QA endpoint
│   │       │   ├── health.py          # /health, /diagnostics self-checks
│   │       │   ├── videos.py          # /videos upload, listing, stream proxy, WebVTT captions
│   │       │   ├── documents.py       # [PLANNED] PDF/PPT upload routes
│   │       │   ├── quiz.py            # [PLANNED] Check quiz routes
│   │       │   ├── interviews.py      # [PLANNED] Mock interview routes
│   │       │   └── summary.py         # [PLANNED] Lecture summary routes
│   │       └── schemas/               # Pydantic request and response models
│   ├── web/                           # React 18 TypeScript single-page application (Vite)
│   │   ├── src/
│   │   │   ├── App.tsx                # Root component, authentication routing, view switcher
│   │   │   ├── main.tsx               # DOM mounting and root style imports
│   │   │   ├── api/                   # Typed API client and contract interfaces
│   │   │   ├── components/            # UI components (AskBox, Player, UnlockBar, ChatPanel, QuickActions)
│   │   │   ├── hooks/                 # Custom React hooks (useAuth, usePlayerTime)
│   │   │   ├── pages/                 # View pages (Login, Library, Upload, Watch)
│   │   │   ├── styles/                # Global design system CSS tokens (tokens.css)
│   │   │   └── __tests__/             # Frontend vitest unit test suites
│   │   ├── package.json               # Node.js dependencies and script commands
│   │   ├── vite.config.ts             # Vite build and development configuration
│   │   └── vercel.json                # Vercel SPA routing and deployment rewrite rules
│   └── worker/                        # Asynchronous ingestion pipeline
│       ├── jobs.py                    # Database-backed job queue claimer and stage coordinator
│       ├── runner.py                  # Standalone worker loop and embedded daemon starter
│       └── stages/                    # Decoupled processing stages (fetch, audio, asr, chunk, embed)
├── core/                              # Shared business logic and AI algorithms
│   ├── answer.py                      # Question answering orchestrator: TAC, retrieval, router, verifier
│   ├── cache.py                       # Content-hash caching for LLM requests
│   ├── chunking.py                    # Word aggregation into 15-20s speech chunks
│   ├── context.py                     # Context pack builder with 3.5k token cap and short IDs
│   ├── embeddings.py                  # Dense 384-d vector embeddings using Multilingual-E5-Small
│   ├── intents.py                     # Rule-based query intent classification
│   ├── pause_frame.py                 # Server-side pause keyframe extraction via FFmpeg
│   ├── retrieval.py                   # Hybrid vector + FTS search under TAC with RRF ranking
│   ├── tac.py                         # Temporal Anchor Constraint definitions, word trimming, assertions
│   ├── verifier.py                    # Citation verifier and server-side coordinate label builder
│   ├── llm/                           # Multi-provider LLM abstraction
│   │   ├── base.py                    # Abstract BaseLLMProvider interface
│   │   ├── gemini.py                  # Google Gemini provider calling google-genai in JSON mode
│   │   ├── ollama.py                  # Local Ollama fallback provider
│   │   └── router.py                  # Fallback chain, daily caps, counters, and cache
│   ├── interview/                     # [PLANNED] Mock interview state machine and scorecards
│   └── prompts/                       # Prompt templates and system instructions
├── infra/                             # Deployment, containers, and operational scripts
│   ├── Dockerfile                     # Multi-stage production container for API and worker
│   ├── docker-compose.yml             # Local PostgreSQL + pgvector container definition
│   ├── .env.example                   # Master template of all environment variable names
│   └── scripts/                       # Operational scripts (seed_users, seed_demo_data, preflight)
├── eval/                              # Evaluation harness and ground-truth datasets
│   ├── dataset/                       # Media files and verified subtitles for benchmark tests
│   ├── questions.json                 # Labelled benchmark questions with pause timestamps
│   ├── run_eval.py                    # Evaluation runner computing spoiler leaks and accuracy
│   └── metrics.py                     # Scoring formulas for evaluations
├── tests/                             # Automated test suite (pytest)
│   ├── conftest.py                    # Pytest fixtures and mock database setup
│   ├── test_tac.py                    # Verification of TAC SQL clause, exact-word cut, and assertions
│   ├── test_verifier.py               # Citation verification, short-id resolution, and label generation
│   ├── test_chunking.py               # Speech chunk boundary and overlap verification
│   ├── test_auth.py                   # Authentication, password hashing, and token generation tests
│   └── test_api_ask.py                # End-to-end API test for POST /ask endpoint
├── docs/                              # Comprehensive AI Knowledge Base documentation set
├── pyproject.toml                     # Master Python project configuration and dependencies
├── render.yaml                        # Infrastructure-as-code Blueprint for Render Free tier
├── DEPLOYMENT_GUIDE.md                # Step-by-step ₹0 production deployment guide (Vercel+Render+Neon)
├── RUNBOOK.md                         # Operational developer runbook and milestone instructions
├── STATUS.md                          # Milestone status journal with verified gate transitions
└── README.md                          # Human-facing project overview
```
