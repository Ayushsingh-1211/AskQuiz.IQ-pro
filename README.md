# AskQuiz.IQ — Pause & Ask Learning Assistant
> **Watch, pause, ask.** AI-powered lecture learning assistant with strict anti-spoiler enforcement and verifiable source citations.

AskQuiz.IQ transforms passive video lectures into interactive, video-grounded tutoring experiences. Students can pause any lecture video at an arbitrary second, ask clarifying or conceptual questions, and receive precise factual answers derived strictly and exclusively from what was presented prior to the pause.

---

## 🌟 Key Highlights

- ⏱️ **Temporal Anchor Constraint (TAC):** Guaranteed **0 spoiler leaks**. The system mathematically prohibits retrieval of any speech or concepts occurring after your pause time.
- 📌 **Verifiable Timestamp Citations:** The server generates exact video timestamps (e.g., `Video 01:45-02:05`). Clicking on any citation chip instantly seeks the video to that moment for visual verification.
- ✂️ **Exact-Word Cut Trimming:** If you pause mid-sentence, the pipeline truncates transcript words to the exact millisecond of your pause, preventing even partial-sentence spoilers.
- 🎥 **Smooth Random Scrubbing:** Built-in HTTP 206 Partial Content Range streaming allows seamless scrubbing through multi-gigabyte video files without buffering delays.
- 💸 **$0 Perpetual Operating Cost:** Built entirely on free-tier infrastructure: React on Vercel + FastAPI on Render Free + PostgreSQL on Neon Free + Google Gemini Free Tier. Zero Redis required.

---

## 🚀 Quickstart

### 1. Zero-Cost Cloud Deployment
Deploy 24/7 to Vercel, Render Free, and Neon in under 10 minutes without credit cards:
👉 **[Read the ₹0 Cloud Deployment Guide](file:///c:/Users/AYUSH%20KUMAR%20SINGH/OneDrive/Documents/AskQuiz.IQ/DEPLOYMENT_GUIDE.md)**

### 2. Local Workstation Setup (Docker)

```bash
# Clone the repository
git clone https://github.com/Ayushsingh-1211/AskQuiz.IQ.git
cd AskQuiz.IQ

# Copy environment template and fill in GEMINI_API_KEY
cp infra/.env.example .env

# Launch local PostgreSQL with pgvector
docker compose -f infra/docker-compose.yml up -d

# Install backend dependencies
pip install -e .

# Install frontend dependencies
cd apps/web && npm install && cd ../..

# Seed demo user (demo@askquiz.iq / demo12345) and sample video
python infra/scripts/seed_users.py
python infra/scripts/seed_demo_data.py

# Start Backend API & Frontend dev server
uvicorn apps.api.app.main:app --port 8000 --reload
cd apps/web && npm run dev
```

Visit `http://localhost:5173` and log in with:
- **Email:** `demo@askquiz.iq`
- **Password:** `demo12345`

---

## 🧪 Testing & Verification

```bash
# Run unit and algorithmic TAC tests (no database required)
pytest tests/test_tac.py tests/test_verifier.py tests/test_chunking.py -v

# Run 10-question temporal evaluation benchmark
python eval/run_eval.py --quick
```

---

## 📚 Complete Documentation Set

For comprehensive technical architecture, algorithms, data schemas, API contracts, and decision logs, consult the documentation directory:

- 📖 **[AI Context Master Bundle (`docs/AI_CONTEXT.md`)](file:///c:/Users/AYUSH%20KUMAR%20SINGH/OneDrive/Documents/AskQuiz.IQ/docs/AI_CONTEXT.md)**: Single self-contained documentation bundle for zero-context AI assistants.
- 📑 **[Documentation Index (`docs/DOCS_INDEX.md`)](file:///c:/Users/AYUSH%20KUMAR%20SINGH/OneDrive/Documents/AskQuiz.IQ/docs/DOCS_INDEX.md)**: Full navigation index across all architectural specifications.
- 🏗️ **[System Architecture (`docs/ARCHITECTURE.md`)](file:///c:/Users/AYUSH%20KUMAR%20SINGH/OneDrive/Documents/AskQuiz.IQ/docs/ARCHITECTURE.md)**: Component boundaries, topology, and data flow diagrams.
- 🔄 **[End-to-End Execution Flows (`docs/FLOW.md`)](file:///c:/Users/AYUSH%20KUMAR%20SINGH/OneDrive/Documents/AskQuiz.IQ/docs/FLOW.md)**: Step-by-step user journeys and execution cards.
- 🧠 **[Algorithms & Logic (`docs/LOGIC.md`)](file:///c:/Users/AYUSH%20KUMAR%20SINGH/OneDrive/Documents/AskQuiz.IQ/docs/LOGIC.md)**: Pseudo-code and worked examples for TAC and RRF retrieval.
- 📡 **[API Specification (`docs/API.md`)](file:///c:/Users/AYUSH%20KUMAR%20SINGH/OneDrive/Documents/AskQuiz.IQ/docs/API.md)**: Complete REST endpoint schemas and error codes.
