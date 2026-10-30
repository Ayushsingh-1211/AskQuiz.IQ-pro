# Environment Setup & Deployment Runbook
> Purpose: Step-by-step instructions for local workstation setup, automated testing, and zero-cost production cloud deployment.
> Last updated: 2026-10-29 | Status: Current
> Derived from: `RUNBOOK.md`, `DEPLOYMENT_GUIDE.md`, `infra/Dockerfile`, `render.yaml`

## 1. Prerequisites & Tooling

### System Tooling
- **Operating System:** Windows 10/11, macOS, or Ubuntu Linux.
- **Python:** Python 3.11+ (Tested on Python 3.12.10).
- **Node.js:** Node.js 20+ and npm 10+.
- **Docker:** Docker Desktop with Docker Compose.
- **FFmpeg & FFprobe:** Must be present on system `PATH`.
  - Windows: `winget install Gyan.FFmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
- **Tesseract OCR:** Required with English (`eng`) and Hindi (`hin`) traineddata.
  - Windows: UB-Mannheim build (`winget install UB-Mannheim.TesseractOCR`)
  - Ubuntu/Debian: `sudo apt install tesseract-ocr tesseract-ocr-hin`
- **Cloudflare Tunnel CLI (Optional for Remote Demos):**
  - Windows: `winget install Cloudflare.cloudflared`

---

## 2. Local Workstation Installation

### Step 1: Clone & Configure Environment
```bash
git clone https://github.com/Ayushsingh-1211/AskQuiz.IQ.git
cd AskQuiz.IQ

# Create local environment file from template
cp infra/.env.example .env
```
Open `.env` in your text editor and provide:
- `GEMINI_API_KEY`: API key from [Google AI Studio](https://aistudio.google.com/).
- Model identifiers:
  ```env
  ANSWER_MODEL=gemini-3.5-flash-lite
  VISION_MODEL=gemini-3.5-flash-lite
  LLM_FALLBACK_CHAIN=gemini-3.5-flash-lite,gemini-3.5-flash,ollama
  DATABASE_URL=postgresql://pause:pause@localhost:5432/pause
  DATA_DIR=./data
  ```

### Step 2: Launch Local Database
```bash
docker compose -f infra/docker-compose.yml up -d
```
*Note: Starts PostgreSQL 16 with `pgvector` on ports `5432` and `5433`.*

### Step 3: Install Python Backend Dependencies
```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install --upgrade pip
pip install -e .
```

### Step 4: Install Frontend Dependencies
```bash
cd apps/web
npm install
cd ../..
```

### Step 5: Seed Demo Accounts & Sample Video
```bash
# Seed demo accounts (demo@askquiz.iq / demo12345)
python infra/scripts/seed_users.py

# Seed sample lecture video and pre-computed chunks
python infra/scripts/seed_demo_data.py
```

### Step 6: Start Services
In separate terminal tabs:
```bash
# 1. Start FastAPI Backend (with embedded worker)
uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --reload

# 2. Start Vite Frontend
cd apps/web
npm run dev
```
Open your browser at `http://localhost:5173`.
Log in with `demo@askquiz.iq` / `demo12345`.

---

## 3. Automated Testing & Verification

### Unit & Algorithmic Tests (No DB Required)
```bash
pytest tests/test_tac.py tests/test_verifier.py tests/test_chunking.py -v
```
*Expected: 7 passed in under 15 seconds.*

### Frontend UI Unit Tests
```bash
cd apps/web
npm test
```
*Expected: AskBox component focus-lock and time-capture tests pass.*

### Evaluation Benchmark
```bash
python eval/run_eval.py --quick
```
*Expected: 10/10 questions evaluated, `spoiler_leak = 0.0`.*

---

## 4. Zero-Cost ($0) Cloud Deployment Runbook

Deploy a live, persistent 24/7 instance without spending a cent using Vercel, Render Free, and Neon.

### Summary Topology
- **Database:** Neon Free Serverless PostgreSQL (`pgvector` included, 0.5 GB storage).
- **Backend:** Render Free Web Service (Docker runtime, 512 MB RAM ceiling).
- **Frontend:** Vercel Hobby Free Tier (Global edge CDN, automated HTTPS).

### A. Setup Neon Database
1. Create a project named `askquiz-db` on [Neon](https://neon.tech).
2. Copy the pooled connection string:
   ```text
   postgresql://neondb_owner:***@ep-xyz.aws.neon.tech/neondb?sslmode=require
   ```

### B. Deploy Backend to Render Free
1. Create a **New Web Service** from your GitHub repository.
2. Select runtime: **Docker** (`infra/Dockerfile`, Docker Context `.`).
3. Set Environment Variables:
   - `DATABASE_URL`: Your Neon connection string (with `?sslmode=require`).
   - `GEMINI_API_KEY`: Your Google AI Studio key.
   - `JWT_SECRET`: Random 32-character hexadecimal string.
   - `ALLOWED_ORIGINS`: `https://askquiz-iq.vercel.app,http://localhost:5173`
   - `EMBEDDING_BACKEND`: `fts` *(Cloud-safe, bypasses heavy PyTorch models)*.
   - `EMBEDDED_WORKER`: `false` *(Keeps API memory under 120MB on Render's 512MB RAM tier)*.
   - `AUTO_SEED_DEMO`: `true` *(Automatically seeds demo lecture & 25 chunks on first boot)*.
   - `WEB_CONCURRENCY`: `1`
   - `ANSWER_MODEL`: `gemini-3.5-flash-lite`
   - `VISION_MODEL`: `gemini-3.5-flash-lite`
   - `LLM_FALLBACK_CHAIN`: `gemini-3.5-flash-lite,gemini-3.5-flash`
   - `DATA_DIR`: `/app/data`
4. Click Deploy. Note your live URL: `https://askquiz-api.onrender.com`.

### C. Deploy Frontend to Vercel
1. Import repository on [Vercel](https://vercel.com).
2. Root Directory: `apps/web`.
3. Add Environment Variable:
   - `VITE_API_URL`: `https://askquiz-api.onrender.com` (no trailing slash).
4. Click Deploy. Access your application worldwide at `https://askquiz-iq.vercel.app`.
