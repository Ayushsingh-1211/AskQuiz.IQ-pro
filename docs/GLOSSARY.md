# Project Glossary & Domain Definitions
> Purpose: Standardized definitions of domain-specific concepts, algorithms, acronyms, and terminology used in AskQuiz.IQ.
> Last updated: 2026-10-29 | Status: Current
> Derived from: `spec/CORE.md`, `AGENTS.md`, `DEPLOYMENT_GUIDE.md`

## 1. Core Domain Concepts

### Temporal Anchor Constraint (TAC)
The foundational security and pedagogical rule of AskQuiz.IQ. TAC dictates that every retrieval query and LLM answer generation must operate solely on educational material revealed to the learner at or before the exact pause moment ($t \le \text{pause\_t}$). TAC prevents narrative and conceptual spoilers.

### `visible_from_s` (The Temporal Visibility Anchor)
The column in the PostgreSQL `chunks` table storing the exact floating-point timestamp in seconds at which a given chunk becomes legally viewable by the student:
- **Speech chunk:** $\text{visible\_from\_s} = \text{end\_s}$ (a spoken thought is only revealed once fully uttered).
- **Screen keyframe:** $\text{visible\_from\_s} = \text{frame\_timestamp}$ (revealed the moment it appears on screen).
- **Document (Permitted Mode):** $\text{visible\_from\_s} = 0.0$ (viewable from lecture start).
- **Document (Aligned Mode):** $\text{visible\_from\_s} = \text{first\_lecture\_coverage\_time}$ (hidden until introduced in video).

### Exact-Word Cut (`trim_at_word`)
An algorithmic trimming operation performed on the recent speech chunk overlapping the user's pause timestamp. Rather than including the entire 15–20 second speech chunk (which would leak spoken words after `pause_t`), words whose start times occur after `pause_t` are stripped.

### Spoiler Rule
The principle that an answer must never reference, explain, or preview definitions, proofs, or conclusions introduced in the video after `pause_t`. If a question asks about unrevealed material, the assistant must return a standard refusal:
> *"This isn't covered in the material up to mm:ss."*

### Context Pack
The sanitized bundle of data assembled on the server and injected into the LLM prompt. Contains:
1. `recent_window`: Spoken text from the last 60–180 seconds up to the exact pause word.
2. `chunks`: Top 8 retrieved historical chunks labeled with context-local short IDs (`c1` ... `c8`).
3. Total token ceiling enforced at 3,500 tokens.

### Context-Local Short IDs (`c1`, `c2`, ...)
Synthetic identifiers substituted for database UUIDs in LLM prompts. Prevents the model from hallucinating UUIDs or inserting timestamps. The model returns `[{"chunk_id": "c2"}]`, and the server maps `c2` back to physical video timestamps (e.g. `Video 01:45-02:05`).

### Reciprocal Rank Fusion (RRF)
An algorithmic rank-aggregation formula used in hybrid retrieval to merge dense vector similarity rankings with full-text lexical search rankings without needing score normalization:
$$\text{RRF Score}(d) = \sum_{m \in \{\text{vector}, \text{fts}\}} \frac{1}{k + r_m(d)} \quad (k=60)$$

### HTTP 206 Partial Content Range Streaming
A standard HTTP streaming protocol where the browser requests specific byte ranges (e.g. `bytes=1048576-2097151`) of a video file. Enables instantaneous scrubbing and playback without loading the full video file into browser memory.

### Content-Hash Caching
A deterministic caching mechanism where prompt text, system instructions, and images are hashed via SHA256. Identical queries return cached results in $<5\text{ms}$ with zero LLM API token consumption.

### Cloud-Safe FTS Mode (`EMBEDDING_BACKEND=fts`)
An operational profile for memory-constrained cloud environments (e.g. Render Free with 512MB RAM). Bypasses loading heavy PyTorch and SentenceTransformer models, running entirely on PostgreSQL `tsvector` full-text search within 100MB RAM.

### Zero-Cost ($0) Stack
The architectural design principle of AskQuiz.IQ ensuring that the prototype operates entirely on perpetual free tiers: Vercel Hobby (Frontend CDN), Render Free (FastAPI Web Service), Neon Free (PostgreSQL + pgvector), and Google Gemini Free Tier (API).
