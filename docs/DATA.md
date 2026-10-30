# Data Models & Storage Lifecycle
> Purpose: Specification of physical storage structures, filesystem layouts, chunk representations, and dataset artifacts.
> Last updated: 2026-10-29 | Status: Current
> Derived from: `apps/api/app/storage.py`, `apps/worker/stages/`, `eval/dataset/`, `eval/questions.json`

## 1. Storage Directory Hierarchy (`DATA_DIR`)

All physical files generated or ingested by AskQuiz.IQ reside under the path defined by `DATA_DIR` (defaults to `./data` in development or `/app/data` in Docker containers).

```
DATA_DIR/
├── videos/
│   └── <video_id>/                    # One isolated directory per video UUID
│       ├── original.mp4                # Raw uploaded video asset or downloaded stream
│       ├── proxy.mp4                   # 720p H.264 faststart transcode for Range streaming
│       ├── audio.wav                   # 16 kHz 16-bit mono uncompressed PCM audio
│       ├── captions.srt                # Generated or fetched SubRip subtitle file
│       ├── captions.vtt                # Converted WebVTT caption file for HTML5 player
│       └── frames/                     # Extracted keyframes (P3 [PLANNED])
│           ├── frame_00012_0024.jpg
│           └── frame_00045_0090.jpg
├── documents/
│   └── <doc_id>/                      # Uploaded lecture PDFs / PPTs (P4 [PLANNED])
│       ├── original.pdf
│       └── pages/
├── cache/                             # Local disk cache for content-hashed outputs
└── .health_test                       # Ephemeral check file for preflight filesystem validation
```

---

## 2. In-Memory & Serialized Chunk Formats

### Speech Chunk (`source_type = 'speech'`) `[VERIFIED]`
Speech chunks represent 15–20 second slices of transcribed speech.
- `text`: Concatenated word tokens.
- `start_s`: Timestamp in seconds of the initial word token.
- `end_s`: Timestamp in seconds of the terminating word token.
- `visible_from_s`: Equal to `end_s` (**The speech spoiler rule: a concept is not revealed until spoken completely**).
- `meta`: Detailed JSON object containing word-level timestamps used for exact-word trimming:
  ```json
  {
    "words": [
      {"word": "Let's", "start": 12.14, "end": 12.42},
      {"word": "explore", "start": 12.48, "end": 12.86},
      {"word": "gradient", "start": 12.92, "end": 13.40},
      {"word": "descent.", "start": 13.44, "end": 13.98}
    ]
  }
  ```

### Screen Chunk (`source_type = 'screen'`) `[PLANNED: spec/P3.md]`
Screen chunks capture visual whiteboard, code editor, or presentation text.
- `text`: Concatenation of OCR text and small-model vision descriptions.
- `start_s`: Frame appearance timestamp.
- `end_s`: Frame replacement timestamp.
- `visible_from_s`: Frame timestamp (visible the instant it appears on screen).
- `frame_path`: Relative filesystem path under `DATA_DIR/videos/<id>/frames/`.
- `meta`:
  ```json
  {
    "ocr_confidence": 0.94,
    "has_handwriting": true,
    "phash": "a7b3c9..."
  }
  ```

### Document Chunk (`source_type = 'pdf' | 'ppt'`) `[PLANNED: spec/P4.md]`
Document chunks represent pages of reference material or slides.
- `text`: Extracted page text and presenter speaker notes.
- `page`: 1-based PDF page number.
- `slide`: 1-based slide index.
- `visible_from_s`:
  - **Permitted mode:** `0.0` (accessible from the beginning of the lecture).
  - **Aligned mode:** The earliest timestamp where the video presentation covers this page ($\ge \tau$).

---

## 3. Evaluation Dataset Structure (`eval/`)

AskQuiz.IQ contains a standardized evaluation testbed to guarantee 0 spoiler leaks.

### Ground Truth Dataset (`eval/dataset/`) `[VERIFIED]`
- `eval/dataset/talking_teacher.mp4`: Short sample lecture video.
- `eval/dataset/talking_teacher.en.srt`: Verified ground-truth subtitles for zero-compute testing.

### Evaluation Question Labels (`eval/questions.json`) `[VERIFIED]`
An array of 10 test questions (expandable to 40) testing temporal boundaries:
```json
[
  {
    "id": "q1",
    "video_title": "Talking Teacher",
    "pause_t": 15.0,
    "question": "What is the topic introduced at the start?",
    "expected_covered": true
  },
  {
    "id": "q2",
    "video_title": "Talking Teacher",
    "pause_t": 5.0,
    "question": "What will be concluded at the end of the lecture?",
    "expected_covered": false,
    "expected_refusal": true
  }
]
```

---

## 4. Content Deduplication & Caching Lifecycle

1. **Upload Deduplication**: `hashlib.sha256` computed during upload buffering. If `(user_id, content_hash)` matches an existing record, the uploaded bytes are purged from disk and the existing video row is returned.
2. **LLM Content Caching**: Prompt text, system instruction, and image paths are hashed via SHA256 (`core/cache.py`). Cached responses are returned in $<5\text{ms}$ with zero Gemini API quota consumption.
3. **Database Pre-seeding**: `infra/scripts/seed_demo_data.py` idempotently inserts the demo video and its 25 pre-computed chunks on first boot, enabling instant playback and Q&A without running heavy ASR pipelines.
