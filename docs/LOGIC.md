# Logic & Algorithmic Register
> Purpose: Mathematical specifications, algorithms, formulas, decision rules, pseudo-code, and worked examples across the codebase.
> Last updated: 2026-10-29 | Status: Current
> Derived from: `core/tac.py`, `core/retrieval.py`, `core/chunking.py`, `core/verifier.py`, `core/answer.py`, `core/llm/router.py`, `apps/api/app/storage.py`

## 1. Algorithmic Overview

AskQuiz.IQ operates under a strict governing paradigm called the **Temporal Anchor Constraint (TAC)**. The central algorithmic challenge is providing rich, coherent answers using large language models while mathematically guaranteeing that no conceptual or factual information from the future of a video lecture leaks to the student.

---

## 2. Logic Register Entries

### L-01: Temporal Anchor Constraint (TAC) SQL Clause
- **Purpose:** Restricts database queries so that only chunks visible at or before the learner's pause timestamp are ever loaded into server memory.
- **Location:** `core/tac.py:get_tac_sql_clause()`
- **Inputs / Outputs:**
  - Input: None (returns parameterized SQL string).
  - Output: SQL clause `video_id = %s AND visible_from_s <= %s`.
- **Rules / Steps:**
  1. Hard rule 1: Every retrieval must filter on `video_id = $1 AND visible_from_s <= $pause_t` in SQL.
  2. Bypassing or removing this clause is strictly forbidden across the codebase.
- **Pseudo-code:**
  ```python
  def get_tac_sql_clause() -> str:
      return "video_id = %s AND visible_from_s <= %s"
  ```
- **Worked example:**
  - Input: `video_id = "v-123"`, `pause_t = 120.0`
  - SQL: `WHERE video_id = 'v-123' AND visible_from_s <= 120.0`
  - Result: A chunk with `visible_from_s = 121.5` is filtered out at the database engine level before hitting Python.
- **Edge cases handled:** `pause_t = 0.0` returns only chunks explicitly permitted at start (e.g. permitted documents with `visible_from_s = 0`).
- **Why this design:** Pushing filtering into the database engine ensures no downstream code can inadvertently access future chunks.
- **Confidence tag:** `[VERIFIED: core/tac.py#L9-L12]`

---

### L-02: Exact-Word Cut Trimming
- **Purpose:** Prevents partial-sentence spoilers when a video is paused mid-utterance.
- **Location:** `core/tac.py:trim_at_word()`
- **Inputs / Outputs:**
  - Input: `words: List[Dict[str, Any]]` (`[{"word": str, "start": float, "end": float}]`), `pause_t: float`.
  - Output: `List[Dict[str, Any]]` (trimmed words).
- **Rules / Steps:**
  1. Iterate each word token in chronological order.
  2. If `word.start <= pause_t`, include word in returned slice.
  3. If `word.start > pause_t`, immediately exclude word and truncate subsequent stream.
- **Pseudo-code:**
  ```python
  def trim_at_word(words, pause_t):
      return [w for w in words if float(w.get("start", 0.0)) <= pause_t]
  ```
- **Worked example:**
  - Pause timestamp: `pause_t = 10.0` seconds.
  - Raw words in overlapping chunk:
    - `{"word": "welcome", "start": 7.0, "end": 7.5}` -> Kept (`7.0 <= 10.0`)
    - `{"word": "to", "start": 8.0, "end": 8.3}` -> Kept (`8.0 <= 10.0`)
    - `{"word": "the", "start": 8.5, "end": 8.8}` -> Kept (`8.5 <= 10.0`)
    - `{"word": "lecture", "start": 9.2, "end": 9.8}` -> Kept (`9.2 <= 10.0`)
    - `{"word": "on", "start": 10.1, "end": 10.3}` -> Dropped (`10.1 > 10.0`)
    - `{"word": "algorithms", "start": 10.5, "end": 11.5}` -> Dropped (`10.5 > 10.0`)
  - Result: `"welcome to the lecture"`.
- **Edge cases handled:** Empty word list returns empty list. Words starting exactly at `pause_t` are included.
- **Why this design:** Speech chunks are typically 15–20s long. If the user pauses at second 10 of a 15-second chunk, retrieving the entire chunk exposes 5 seconds of future speech. Trimming at the exact word eliminates this leak.
- **Confidence tag:** `[VERIFIED: core/tac.py#L14-L22, tests/test_tac.py#L12-L31]`

---

### L-03: Dynamic Spoken Recent Window
- **Purpose:** Gathers the immediate preceding speech context prior to `pause_t`, adapting dynamically to silent periods.
- **Location:** `core/tac.py:recent_window()`
- **Inputs / Outputs:**
  - Input: `conn: psycopg.Connection`, `video_id: str`, `pause_t: float`, `window_s: float = 60.0`, `min_words: int = 20`, `wide_window_s: float = 180.0`.
  - Output: `Dict[str, Any]` (`{text: str, words: list, start_s: float, end_s: float, word_count: int}`).
- **Rules / Steps:**
  1. Calculate `start_t = max(0.0, pause_t - window_s)`.
  2. Query database for speech chunks overlapping `[start_t, pause_t]` using:
     `start_s <= pause_t AND end_s >= start_t`.
  3. Extract all word tokens within `[start_t, pause_t]`. Deduplicate by `(start, end, word)`.
  4. Apply `trim_at_word(words, pause_t)`.
  5. If `word_count < min_words` (20 words) and current `window_s < wide_window_s`, recurse with `window_s = 180.0`.
  6. Return aggregated text string and metadata.
- **Pseudo-code:**
  ```python
  def recent_window(conn, video_id, pause_t, window_s=60.0, min_words=20, wide_window_s=180.0):
      start_t = max(0.0, pause_t - window_s)
      rows = query_overlapping_speech_chunks(video_id, start_t, pause_t)
      words = extract_and_deduplicate_words(rows, start_t, pause_t)
      trimmed = trim_at_word(words, pause_t)
      if len(trimmed) < min_words and window_s < wide_window_s:
          return recent_window(conn, video_id, pause_t, window_s=wide_window_s)
      return {
          "text": " ".join(w["word"] for w in trimmed),
          "words": trimmed,
          "start_s": trimmed[0]["start"] if trimmed else start_t,
          "end_s": trimmed[-1]["end"] if trimmed else pause_t,
          "word_count": len(trimmed)
      }
  ```
- **Worked example:**
  - Learner pauses at `pause_t = 80.0s`.
  - Initial 60s window: `[20.0s, 80.0s]`.
  - If teacher paused for 50 seconds to write on a board, only 8 words exist in `[20.0s, 80.0s]`.
  - Since `8 < 20`, window widens to 180s: `[0.0s, 80.0s]`.
  - Gathers 45 words spoken during the introduction, providing sufficient semantic context for the LLM.
- **Edge cases handled:** Video paused near start (`pause_t < 60s`) clamps `start_t = 0.0`.
- **Confidence tag:** `[VERIFIED: core/tac.py#L24-L86]`

---

### L-04: Strict Anti-Spoiler Assertion (`assert_no_future`)
- **Purpose:** Absolute safety circuit breaker before sending prompt to any LLM.
- **Location:** `core/tac.py:assert_no_future()`
- **Inputs / Outputs:**
  - Input: `context_pack: Dict[str, Any]`, `pause_t: float`.
  - Output: `None` (Raises `AssertionError` on violation).
- **Rules / Steps:**
  1. Define epsilon: $\epsilon = 1 \times 10^{-4}$ (0.0001s).
  2. For every chunk $c$ in `context_pack["chunks"]`:
     - If `float(c["visible_from_s"]) > pause_t + epsilon`:
       Log critical error and raise `AssertionError("TAC VIOLATION")`.
  3. For every word $w$ in `context_pack["recent_window"]["words"]`:
     - If `float(w["start"]) > pause_t + epsilon`:
       Log critical error and raise `AssertionError("TAC VIOLATION")`.
- **Pseudo-code:**
  ```python
  def assert_no_future(context_pack, pause_t):
      epsilon = 1e-4
      for c in context_pack.get("chunks", []):
          if float(c.get("visible_from_s", 0.0)) > pause_t + epsilon:
              raise AssertionError(f"TAC VIOLATION: chunk {c.get('id')} future visibility")
      for w in context_pack.get("recent_window", {}).get("words", []):
          if float(w.get("start", 0.0)) > pause_t + epsilon:
              raise AssertionError(f"TAC VIOLATION: word '{w.get('word')}' in future")
  ```
- **Worked example:**
  - `pause_t = 45.0`
  - Chunk with `visible_from_s = 45.00005` passes.
  - Chunk with `visible_from_s = 45.1` immediately raises `AssertionError`.
- **Edge cases handled:** Floating-point rounding errors mitigated via `1e-4` epsilon.
- **Why this design:** Catches bugs in retrieval logic or SQL joins before LLM generation occurs.
- **Confidence tag:** `[VERIFIED: core/tac.py#L88-L110, tests/test_tac.py#L33-L62]`

---

### L-05: Speech Chunk Aggregation
- **Purpose:** Groups continuous word streams into overlapping chunks suitable for semantic embedding and retrieval.
- **Location:** `core/chunking.py:chunk_words()`
- **Inputs / Outputs:**
  - Input: `words: List[Dict[str, Any]]`, `target_duration_s: float = 18.0`, `overlap_s: float = 3.0`.
  - Output: `List[Dict[str, Any]]` (structured chunks).
- **Rules / Steps:**
  1. Start window at first word `start_idx = 0`.
  2. Compute `target_end_t = words[start_idx]["start"] + 18.0`.
  3. Expand `end_idx` until next word exceeds `target_end_t`.
  4. Construct chunk: `start_s = words[start_idx]["start"]`, `end_s = words[end_idx - 1]["end"]`.
  5. Set `visible_from_s = end_s`. (The speech chunk cannot be known until the speaker finishes speaking it).
  6. Compute overlap boundary: `overlap_target_t = end_s - 3.0`.
  7. Advance `start_idx` to first word where `start >= overlap_target_t`.
- **Pseudo-code:**
  ```python
  while start_idx < n:
      target_end_t = words[start_idx]["start"] + 18.0
      while end_idx < n and words[end_idx]["end"] <= target_end_t:
          end_idx += 1
      chunk = {
          "source_type": "speech",
          "text": " ".join(w["word"] for w in words[start_idx:end_idx]),
          "start_s": words[start_idx]["start"],
          "end_s": words[end_idx - 1]["end"],
          "visible_from_s": words[end_idx - 1]["end"],
          "meta": {"words": words[start_idx:end_idx]}
      }
      overlap_target_t = chunk["end_s"] - 3.0
      advance start_idx to overlap_target_t
  ```
- **Worked example:**
  - Word 1 at `0.0s`, Word 10 at `18.2s`.
  - Chunk 1 spans `[0.0s, 18.2s]`, `visible_from_s = 18.2s`.
  - Overlap target = `18.2 - 3.0 = 15.2s`.
  - Chunk 2 begins at Word 8 (`15.4s`), preserving continuity across sentence boundaries.
- **Confidence tag:** `[VERIFIED: core/chunking.py#L4-L60, tests/test_chunking.py]`

---

### L-06: Hybrid Reciprocal Rank Fusion (RRF) Retrieval
- **Purpose:** Merges vector semantic similarity rankings with full-text lexical search rankings under TAC.
- **Location:** `core/retrieval.py:hybrid_retrieve()`
- **Inputs / Outputs:**
  - Input: `conn`, `video_id`, `query: str`, `pause_t: float`, `top_k: int = 8`.
  - Output: `List[Dict[str, Any]]` (top ranked chunks).
- **Formula:**
  $$\text{RRF Score}(d) = \sum_{m \in \{\text{vector}, \text{fts}\}} \frac{1}{k + r_m(d)}$$
  where constant $k = 60$, and $r_m(d) \in [1, 20]$ is the rank of chunk $d$ in system $m$.
- **Rules / Steps:**
  1. If `EMBEDDING_BACKEND != "fts"`, run vector cosine distance query on `chunks.embedding` with TAC filter:
     `WHERE video_id = %s AND visible_from_s <= %s ORDER BY embedding <=> query::vector LIMIT 20`.
  2. Run PostgreSQL full-text search query on `chunks.tsv` with TAC filter:
     `WHERE video_id = %s AND visible_from_s <= %s AND tsv @@ plainto_tsquery('simple', query) ORDER BY fts_score DESC LIMIT 20`.
  3. If FTS matches $< 8$, execute fallback OR query via `to_tsquery('simple', or_terms)`.
  4. Accumulate RRF score for each unique chunk ID.
  5. Sort candidate chunks descending by RRF score.
  6. Guarantee screen diversity: if any screen chunk matched in candidate pool, ensure at least 1 screen chunk is included in final `top_k`.
- **Worked example:**
  - Chunk $A$: Vector Rank 1 ($r=1$), FTS Rank 3 ($r=3$).
    $$\text{Score}(A) = \frac{1}{60 + 1} + \frac{1}{60 + 3} = \frac{1}{61} + \frac{1}{63} = 0.01639 + 0.01587 = 0.03226$$
  - Chunk $B$: Vector Rank 20 ($r=20$), FTS Rank 1 ($r=1$).
    $$\text{Score}(B) = \frac{1}{60 + 20} + \frac{1}{60 + 1} = \frac{1}{80} + \frac{1}{61} = 0.01250 + 0.01639 = 0.02889$$
  - Chunk $A$ ranks above Chunk $B$.
- **Edge cases handled:** In cloud FTS mode (`EMBEDDING_BACKEND=fts`), vector search is skipped entirely. If FTS returns zero matches, falls back to most recent historical chunks prior to `pause_t`.
- **Confidence tag:** `[VERIFIED: core/retrieval.py#L48-L186]`

---

### L-07: Conversational Stop-Word Filtering & Query Formulation
- **Purpose:** Extracts meaningful terms from informal questions to formulate reliable PostgreSQL tsqueries.
- **Location:** `core/retrieval.py:_extract_tsquery_terms()`
- **Inputs / Outputs:**
  - Input: `query: str` (e.g. *"Can you explain what gradient descent means in this video?"*).
  - Output: `Optional[str]` (e.g. `"gradient | descent | means"`).
- **Rules / Steps:**
  1. Tokenize query using alphanumeric regex `[a-zA-Z0-9]+`.
  2. Convert to lowercase.
  3. Filter out tokens with length $< 3$.
  4. Filter out common English conversational words and question framing (e.g. `explain`, `tell`, `video`, `lecture`, `what`, `this`, `can`).
  5. Deduplicate preserving order; limit to top 8 tokens.
  6. Join with OR operator (` | `).
- **Worked example:**
  - Input: *"Can you please explain gradient descent in the video?"*
  - Extracted: `["gradient", "descent"]`
  - Output tsquery: `"gradient | descent"`
- **Confidence tag:** `[VERIFIED: core/retrieval.py#L12-L46]`

---

### L-08: Server-Side Citation Verification & Coordinate Mapping
- **Purpose:** Validates cited sources and formats deterministic timestamps, ensuring LLMs never hallucinate coordinates.
- **Location:** `core/verifier.py:verify_and_build_citations()`
- **Inputs / Outputs:**
  - Input: `raw_citations: List[Dict[str, Any]]` (from LLM), `id_map: Dict[str, Dict]`, `pause_t: float`.
  - Output: `Tuple[List[Dict[str, Any]], bool]` (`(verified_citations, is_valid)`).
- **Rules / Steps:**
  1. Strip formatting from cited ID (e.g. `[c2]` -> `c2`).
  2. Resolve ID in `id_map` (checks short ID `c2` first, then full UUID). If missing, flag invalid and skip.
  3. Check TAC: `if chunk.visible_from_s > pause_t + 1e-4`, flag invalid and skip.
  4. Server constructs coordinate labels:
     - Speech chunk: `Video mm:ss-mm:ss` based on `(start_s, end_s)`.
     - Screen chunk: `Screen mm:ss`.
     - PDF document: `PDF p.{page}`.
     - Presentation slide: `Slide {slide}`.
  5. Return verified list and validation boolean.
- **Pseudo-code:**
  ```python
  def verify_and_build_citations(raw_citations, id_map, pause_t):
      verified = []
      is_valid = True
      for c in raw_citations:
          cid = clean(c["chunk_id"])
          chunk = id_map.get(cid)
          if not chunk or chunk["visible_from_s"] > pause_t + 1e-4:
              is_valid = False
              continue
          label = f"Video {format_ts(chunk['start_s'])}-{format_ts(chunk['end_s'])}"
          verified.append({"chunk_id": str(chunk["id"]), "source_ref": {"label": label, ...}})
      return verified, is_valid
  ```
- **Worked example:**
  - LLM cites `[{"chunk_id": "c1"}]`.
  - `id_map["c1"]`: `start_s = 65.0`, `end_s = 82.0`, `visible_from_s = 82.0`.
  - `pause_t = 100.0` -> `82.0 <= 100.0` (Valid).
  - Server formats label: `Video 01:05-01:22`.
- **Confidence tag:** `[VERIFIED: core/verifier.py#L16-L82, tests/test_verifier.py]`

---

### L-09: Multi-Turn Conversation History TAC Filtering
- **Purpose:** Prevents information leakage when a user asks a question at minute 5, rewinds to minute 2, and asks a follow-up question.
- **Location:** `apps/api/app/routes/ask.py#L55-L64`, `core/answer.py#L38-L44`
- **Rules / Steps:**
  1. When querying previous chat history for a session:
     `SELECT role, content, pause_t FROM messages WHERE session_id = %s AND (pause_t IS NULL OR pause_t <= %s)`.
  2. Any message recorded at `pause_t > current_pause_t` is omitted from conversation history.
- **Worked example:**
  - Turn 1: User at `05:00` asks *"What did the professor say about Transformers?"* -> Saved with `pause_t = 300.0`.
  - User rewinds video to `01:30`.
  - Turn 2: User at `01:30` asks *"Can you explain that again?"*
  - Turn 1 is filtered out because `300.0 > 90.0`.
  - LLM receives only context up to `01:30`, preventing the answer from discussing Transformers prematurely.
- **Confidence tag:** `[VERIFIED: apps/api/app/routes/ask.py#L55-L64]`

---

### L-10: LLM Content-Hash Caching & Fallback Chain Routing
- **Purpose:** Eliminates duplicate LLM calls, enforces per-model daily caps, and provides automated fallback.
- **Location:** `core/llm/router.py:route_generate_json()`
- **Formula:**
  $$\text{Hash} = \text{SHA256}(\text{prompt} \parallel \text{images} \parallel \text{system\_instruction})$$
- **Rules / Steps:**
  1. Compute SHA256 content hash of inputs.
  2. If `use_cache=True` and key exists in cache, return cached dict immediately.
  3. Parse `LLM_FALLBACK_CHAIN` (e.g. `gemini-3.5-flash-lite,gemini-3.5-flash,ollama`).
  4. For each model:
     - Check `LLM_DAILY_CAP`. If call count $\ge$ cap, skip.
     - Try generation. On success, increment counter, cache result, and return.
     - On exception, log warning and try next model.
  5. If all fail, return graceful degradation payload with `refusal: true`:
     `"Free quota reached, retrying in 30s."`
- **Confidence tag:** `[VERIFIED: core/llm/router.py#L22-L84]`

---

### L-11: Database-Native Task Claiming with SKIP LOCKED
- **Purpose:** Distributed asynchronous worker job queue without external message brokers (Redis/RabbitMQ).
- **Location:** `apps/worker/jobs.py:claim_and_execute_next_job()`
- **SQL Specification:**
  ```sql
  SELECT id, job_type, payload, attempts
  FROM jobs
  WHERE status = 'queued'
  ORDER BY created_at ASC
  LIMIT 1
  FOR UPDATE SKIP LOCKED;
  ```
- **Rules / Steps:**
  1. Transaction begins and executes `FOR UPDATE SKIP LOCKED`.
  2. Locks the oldest queued row, skipping any rows currently locked by other concurrent workers.
  3. Updates row status to `'processing'` and increments `attempts`.
  4. Commits lock acquisition.
  5. Executes stage pipeline. On completion, updates status to `'completed'`. On uncaught exception, marks status `'failed'` with error message.
- **Why this design:** Eliminates Redis entirely while ensuring exactly-once execution per job across multiple worker instances.
- **Confidence tag:** `[VERIFIED: apps/worker/jobs.py#L163-L230]`

---

### L-12: HTTP 206 Partial Content Range Streaming
- **Purpose:** Sub-second random seeking across multi-gigabyte video files.
- **Location:** `apps/api/app/storage.py:range_streaming_response()`
- **Rules / Steps:**
  1. Inspect `Range` HTTP header (e.g. `bytes=1048576-`).
  2. Parse `start_byte` and `end_byte`. If `end_byte` omitted, default to `min(start + 1MB, file_size - 1)`.
  3. Open file descriptor, seek to `start_byte`, read chunk.
  4. Return `StreamingResponse` with status `206 Partial Content` and headers:
     - `Content-Range: bytes {start}-{end}/{total}`
     - `Accept-Ranges: bytes`
     - `Content-Length: {length}`
     - `Content-Type: video/mp4`
- **Confidence tag:** `[VERIFIED: apps/api/app/storage.py#L65-L100]`
