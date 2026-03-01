---
title: 'Second Brain MVP — Capture & Recall Loop'
slug: 'second-brain-mvp-capture-recall'
created: '2026-02-28'
status: 'ready-for-dev'
stepsCompleted: [1, 2, 3, 4]
tech_stack:
  - Python 3.11+
  - FastAPI
  - Pydantic v2
  - SQLite (aiosqlite)
  - Qdrant Cloud (persistent)
  - Hugging Face Inference API
  - Slack SDK (read-only polling)
  - structlog
  - Jinja2 + htmx
files_to_modify: []
code_patterns:
  - 'Layered: API → Service → Repository'
  - 'Pydantic BaseSettings for config'
  - 'LLM provider protocol for abstraction'
  - 'Repository pattern for SQLite'
  - 'Structured logging via structlog'
test_patterns:
  - 'pytest + pytest-asyncio'
  - 'In-memory SQLite for DB tests'
  - 'Mock HF API responses for classification tests'
  - 'Shared fixtures in conftest.py'
---

# Tech-Spec: Second Brain MVP — Capture & Recall Loop

**Created:** 2026-02-28

## Overview

### Problem Statement

Michelle has no system to capture thoughts from Slack and retrieve them later. Ideas, decisions, risks, and tasks expressed in Slack messages get lost in channel noise with no structured way to store, classify, or recall them.

### Solution

A local FastAPI web application running on a Windows laptop that pulls messages from a designated Slack channel AND bot DMs on startup and manual refresh, classifies them via Hugging Face Inference API, embeds them via HF Inference API, stores structured data in SQLite and vectors in Qdrant Cloud, and provides dual search (vector similarity + keyword/tag filtering) through a combined dashboard UI with live capture feed and search in one view.

### Scope

**In Scope:**

- Project scaffold (pyproject.toml, folder structure, base models)
- Slack message collection from designated channel + bot DMs: startup catch-up + manual refresh button
- Capture pipeline: message → classify (HF Inference API) → embed (HF Inference API) → store (SQLite + Qdrant Cloud)
- Auto-tagging from classification type (no manual tags — zero friction capture)
- Recall via both vector similarity search and keyword/tag filtering
- Combined dashboard UI (FastAPI + Jinja2 + htmx): capture feed + search on one page
- Color-coded classification type chips (💡 Idea, ✅ Task, ⚖️ Decision, ⚠️ Risk, 🏗️ Arch Note, 🎯 Strategy, 📝 Note, ❓ Unclassified)
- Search result source badges: 🧲 (vector match) + 🔤 (keyword match), dual-match boosted to top
- Slack permalink on every captured entry for original context
- Thread awareness: capture thread starters, show reply count + link (don't fetch full threads)
- Author tracking: store author_id + author_name per entry for multi-author channels
- Deduplication by Slack message timestamp (ts) — never store the same message twice
- Copy-to-clipboard button on search results for quick export
- Daily capture digest counter on dashboard
- Empty search → capture prompt ("No matches. Capture a thought about X?")
- Structured logging, error handling, type hints everywhere
- Tests for models, classification parsing, storage, retrieval

**Out of Scope:**

- `/brain summarize week` and `/brain prd <thread>` commands
- Slack slash commands (require public tunnel)
- Multi-tenant / multi-user support
- Docker / cloud deployment of the app itself
- Slack app creation (already configured)
- Mobile / responsive UI (desktop browser only)

## Context for Development

### Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Hosting | Windows laptop (local) | Always available when working, no cloud app hosting |
| LLM | HF Inference API (cloud) | No local GPU/model needed, fast, quality models |
| Embeddings | HF Inference API (cloud) | Same provider, consistent, `all-MiniLM-L6-v2` |
| Slack Sources | Channel + bot DMs (read-only polling) | DM capture = private thoughts, channel = shared thoughts |
| Message Collection | Startup catch-up + manual refresh | Not always-on; on-demand is sufficient |
| Vector Store | Qdrant Cloud (persistent SSD) | Managed, persistent, no data loss on restart |
| Persistence | SQLite | Durable local store of record |
| Classification | Immediate on capture via HF Inference API | 8 types: Idea, Task, Decision, Risk, Arch Note, Strategy, Note + Unclassified (error state) |
| Search | Dual: vector similarity + keyword/tag | Full recall power from day one |
| UI | FastAPI + Jinja2 + htmx | Combined dashboard: capture feed + search in one view |
| Credentials | Environment variables via `.env` | Slack, HF, and Qdrant tokens |

### Codebase Patterns

- **Architecture:** Layered — API routes → Service layer → Repository/Store
- **Models:** Pydantic v2 strict models for all domain objects
- **Config:** Pydantic `BaseSettings` reading from `.env` file
- **DB Access:** Repository pattern with explicit SQL via `aiosqlite`
- **LLM Abstraction:** Provider protocol (Python `Protocol` class) so HF can be swapped for Ollama/OpenAI later
- **Error Handling:** Custom exception hierarchy, never swallow errors, structured logging
- **Input Sanitization:** Jinja2 auto-escaping is ON by default (never use `| safe` on user content). All SQL uses parameterized queries (`?` placeholders, never f-strings). Raw Slack text stored as-is but always rendered through Jinja2's auto-escape.
- **File Naming:** `snake_case.py`, one module per concern

### Files to Create

```
src/
├── __init__.py
├── main.py                    # FastAPI app + startup catch-up lifecycle
├── config.py                  # Pydantic BaseSettings from .env
├── api/
│   ├── __init__.py
│   ├── routes.py              # /refresh, /recall, /entries endpoints
│   └── templates/
│       ├── base.html          # Layout with htmx
│       ├── dashboard.html     # Combined: capture feed + search + digest counter
│       └── partials/
│           ├── entry_card.html # Single entry card with type chip + permalink
│           ├── search_results.html  # htmx partial for search results with source badges
│           └── capture_prompt.html  # Empty search → capture prompt partial
├── core/
│   ├── __init__.py
│   ├── exceptions.py          # Custom exception hierarchy
│   └── pipeline.py            # Capture pipeline: collect → classify → embed → store
├── models/
│   ├── __init__.py
│   ├── brain_entry.py         # BrainEntry domain model (includes slack_ts, author_id, author_name, thread_ts, reply_count, archived_at)
│   └── enums.py               # EntryType enum (8 values: Idea, Task, Decision, Risk, ArchNote, Strategy, Note, Unclassified)
├── classification/
│   ├── __init__.py
│   ├── classifier.py          # Classification service
│   └── provider.py            # LLM provider protocol + HF implementation
├── storage/
│   ├── __init__.py
│   ├── database.py            # SQLite setup + schema init
│   └── repository.py          # BrainEntry CRUD operations
├── retrieval/
│   ├── __init__.py
│   ├── search.py              # Dual search orchestrator
│   ├── vector_store.py        # Qdrant Cloud operations
│   └── keyword_search.py      # SQLite FTS5 keyword/tag search
├── slack/
│   ├── __init__.py
│   └── collector.py           # Fetch messages since last timestamp
tests/
├── __init__.py
├── conftest.py                # Shared fixtures
├── test_models.py             # Schema validation tests
├── test_classification.py     # Classification parsing tests
├── test_storage.py            # Repository CRUD tests
├── test_retrieval.py          # Dual search tests
├── test_pipeline.py           # Capture pipeline orchestration tests
scripts/                         # Reserved per AGENTS.md (future utility scripts)
pyproject.toml                 # Project config + all dependencies
.env.example                   # Env var placeholders (no secrets)
.gitignore                     # Exclude .env, *.db, __pycache__/, .pytest_cache/
README.md                      # Setup, install, run instructions
```

### Technical Decisions

- **No slash commands** — requires public URL/tunnel, out of scope for local laptop
- **htmx over React/Vue** — server-rendered simplicity, no build step, minimal JS
- **HF Inference API over local models** — avoids torch/transformers install (~2GB+), faster inference
- **Qdrant Cloud over local** — persistent, managed, eliminates local Qdrant process
- **Channel + bot DMs** — watches designated channel AND bot DMs, configurable via env vars
- **Auto-tags only** — classification type is the tag, no manual tagging friction
- **Combined dashboard** — feed + search on one page, not separate views
- **Slack permalinks** — every entry links back to original Slack message for full context
- **Empty search → capture** — turns missed searches into capture opportunities

### Architecture Decision Records

#### ADR-001: HF Inference API over Local Models

**Status:** Accepted | **Context:** Need LLM for classification + embeddings on Windows laptop

| Criteria | HF Inference API | Ollama Local | transformers Local |
|----------|-----------------|--------------|-------------------|
| Setup complexity | Low (API key) | Medium | High (~2GB torch) |
| Latency | ~200-500ms | ~1-3s CPU | ~2-5s CPU |
| Offline | ❌ | ✅ | ✅ |
| Cost | Free tier ~30k req/mo | Free | Free |
| Model quality | Best | Good | Good |

**Decision:** HF Inference API — zero setup, best quality, fast. Free tier sufficient for MVP.
**Degradation:** If API fails, store raw message as "unclassified", retry on next refresh. Provider protocol allows swapping to Ollama later.

#### ADR-002: Qdrant Cloud over Local / SQLite Vectors

**Status:** Accepted | **Context:** Need persistent vector search without local process management

| Criteria | Qdrant Cloud | Qdrant Local | SQLite + numpy |
|----------|-------------|-------------|----------------|
| Persistence | ✅ Managed | Requires config | ✅ In SQLite |
| Setup | URL + key | Docker/binary | Zero |
| Scalability | High | Medium | Low (~10k) |
| Restart behavior | Survives | Survives (if persistent) | Survives |

**Decision:** Qdrant Cloud — managed, persistent, free tier (1GB/1M vectors) sufficient. No Docker on Windows.
**AGENTS.md Override:** AGENTS.md Section 4 specifies "Qdrant (local vector store)." This ADR explicitly supersedes that constraint — Qdrant Cloud chosen for persistence and zero-process-management. AGENTS.md should be updated to reflect this decision. Provider abstraction allows reverting to local Qdrant if needed.
**Degradation:** Keyword search (SQLite FTS5) works independently as fallback. Can migrate to local Qdrant via provider abstraction.

#### ADR-003: Read-Only Polling over Webhooks / Slash Commands

**Status:** Accepted | **Context:** Laptop not always-on, not publicly routable

| Criteria | Polling | Slash Commands | Events API |
|----------|---------|---------------|------------|
| Public URL | ❌ No | ✅ Yes (tunnel) | ✅ Yes (tunnel) |
| Real-time | ❌ On-demand | ✅ | ✅ |
| Always-on | ❌ No | ✅ Yes | ✅ Yes |

**Decision:** Read-only polling on startup + refresh. No tunnel needed.
**AGENTS.md Override:** AGENTS.md Section 4 lists "Slack Events API, Slash commands, Webhook responses" as the Slack stack. This ADR explicitly supersedes that — all three require a publicly routable URL (tunnel), which is impractical for a local laptop. Polling is the appropriate pattern for this deployment model. AGENTS.md should be updated to reflect this decision.
**Security Note (re: AGENTS.md §12 "Validate Slack request signatures"):** Signature validation is N/A in polling mode — there are no inbound Slack requests to validate. Security is maintained via: (1) `SLACK_BOT_TOKEN` stored in `.env` for authenticated outbound API calls, (2) app binds to `127.0.0.1` only (no external access), (3) no user-provided code is executed.
**Degradation:** `last_processed_timestamp` in SQLite ensures durable catch-up. Slack `conversations.history` with `oldest` param prevents duplicates.

#### ADR-004: Combined Dashboard over Separate Pages

**Status:** Accepted | **Context:** UI for browsing entries and running recall

**Decision:** Feed + search on single page. Eliminates context switching. htmx partials keep it clean.
**Trade-off:** Slightly more on screen vs. zero navigation.

#### ADR-005: Immediate Classification over Lazy/Batch

**Status:** Accepted | **Context:** When to classify captured messages

**Decision:** Immediate on capture. Type filtering, digest counters, and dashboard UX depend on classification existing. HF API ~200ms, so 50 catch-up messages ≈ 10s.
**Degradation:** If HF fails mid-batch, store as "unclassified" and continue. Show progress: "Catching up: 23/50..."

#### ADR-006: Auto-Tags from Classification over Manual Tagging

**Status:** Accepted | **Context:** How entries get tagged

**Decision:** Auto-tags only. Classification type IS the tag. Zero-friction capture.
**Migration:** `tags` array in data model supports manual tagging later without schema changes. For now, `tags = [entry_type.value]`.

### Constraints

- Must run on Windows (Python 3.11+)
- Requires internet for HF Inference API and Qdrant Cloud
- Human-in-the-loop mandatory
- No autonomous loops or background execution
- No secrets in code — all via environment variables

## Implementation Plan

### Tasks

#### Phase 1: Project Scaffold & Core Models (Foundation — no external dependencies)

- [ ] **Task 1: Initialize project structure**
  - File: `pyproject.toml`
  - Action: Create with project metadata, all dependencies listed in Dependencies section, Python 3.11+ requirement, pytest config
  - Notes: Use `[project.scripts]` entry point: `second-brain = "src.main:run"`

- [ ] **Task 2: Create folder structure with `__init__.py` files**
  - Files: All `__init__.py` files in `src/`, `src/api/`, `src/core/`, `src/models/`, `src/classification/`, `src/storage/`, `src/retrieval/`, `src/slack/`, `tests/`
  - Action: Create empty `__init__.py` in every package directory
  - Notes: Establishes Python package structure

- [ ] **Task 3: Create configuration module**
  - File: `src/config.py`
  - Action: Create `Settings` class extending Pydantic `BaseSettings`. Fields: `SLACK_BOT_TOKEN: str`, `SLACK_CHANNEL_ID: str`, `SLACK_COLLECT_DMS: bool = True`, `HF_API_TOKEN: str`, `HF_CLASSIFICATION_MODEL: str = "mistralai/Mistral-7B-Instruct-v0.3"`, `HF_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"`, `QDRANT_URL: str`, `QDRANT_API_KEY: str`, `QDRANT_COLLECTION_NAME: str = "brain_entries"`, `LOG_LEVEL: str = "INFO"`, `DB_PATH: str = "second_brain.db"`
  - Notes: Use `model_config = SettingsConfigDict(env_file=".env")`. Singleton pattern via `@lru_cache`. `DB_PATH` must be resolved to an absolute path at startup: if relative, resolve relative to the project root (directory containing `pyproject.toml`). Use `Path(__file__).resolve().parent.parent / db_path` to ensure consistent DB location regardless of working directory. Log the resolved path on startup.

- [ ] **Task 4: Create `.env.example`**
  - File: `.env.example`
  - Action: Create with all env var placeholders (no real secrets), matching config.py fields
  - Notes: Include inline comments explaining each variable

- [ ] **Task 5: Create EntryType enum**
  - File: `src/models/enums.py`
  - Action: Create `EntryType(str, Enum)` with values: `IDEA = "idea"`, `TASK = "task"`, `DECISION = "decision"`, `RISK = "risk"`, `ARCH_NOTE = "arch_note"`, `STRATEGY = "strategy"`, `NOTE = "note"`, `UNCLASSIFIED = "unclassified"`. Add `TYPE_DISPLAY` dict mapping each type to its emoji + color: `{EntryType.IDEA: {"emoji": "💡", "color": "blue", "label": "Idea"}, ...}`
  - Notes: `Unclassified` is the error/fallback state, NOT a valid classification output. **AGENTS.md Override (re: Section 5.3):** AGENTS.md frames "Note" as the uncertain-default ("Default to 'Note' if uncertain"). Per Socratic Questioning analysis, Note is now a first-class 7th classification type — the LLM actively classifies content as a Note when it genuinely doesn't fit other categories. `Unclassified` (8th value) serves as the error state when the HF API fails entirely. AGENTS.md should be updated to reflect this split.

- [ ] **Task 6: Create BrainEntry domain model**
  - File: `src/models/brain_entry.py`
  - Action: Create Pydantic model `BrainEntry` with fields: `id: UUID` (default_factory=uuid4), `type: EntryType`, `title: str`, `summary: str`, `raw_content: str`, `created_at: datetime` (default_factory=utcnow), `project: str | None = None`, `tags: list[str]` (default_factory=list), `embedding_vector_id: str | None = None`, `slack_ts: str | None = None` (unique Slack dedup key — None for manual captures), `slack_permalink: str | None = None` (None for manual captures), `author_id: str`, `author_name: str`, `thread_ts: str | None = None`, `reply_count: int = 0`, `archived_at: datetime | None = None`, `source: Literal["slack", "manual"] = "slack"`. Also create `BrainEntryCreate` (input model without id/created_at) and `SearchResult` model with: `entry: BrainEntry`, `score: float`, `source: Literal["vector", "keyword", "both"]`
  - Notes: Follows AGENTS.md data model constraints. `slack_ts` is the dedup key for Slack messages. For manual captures (`source="manual"`), `slack_ts` and `slack_permalink` are None, and dedup uses the `id` field instead. SQLite UNIQUE constraint on `slack_ts` must allow NULLs (SQLite permits multiple NULLs in UNIQUE columns by default).

- [ ] **Task 7: Create custom exceptions**
  - File: `src/core/exceptions.py`
  - Action: Create exception hierarchy: `SecondBrainError(Exception)` base, `ClassificationError(SecondBrainError)`, `StorageError(SecondBrainError)`, `RetrievalError(SecondBrainError)`, `SlackCollectionError(SecondBrainError)`, `ProviderError(SecondBrainError)`
  - Notes: Each includes `message: str` and optional `details: dict`

#### Phase 2: Storage Layer (SQLite — local, testable independently)

- [ ] **Task 8: Create SQLite database module**
  - File: `src/storage/database.py`
  - Action: Create `Database` class with: `async init_db()` that creates `brain_entries` table (columns matching BrainEntry fields, `slack_ts TEXT UNIQUE`), creates FTS5 virtual table `brain_entries_fts` using content-sync triggers (content table = `brain_entries`), creates `app_state` table with `key TEXT PRIMARY KEY, value TEXT` (for `last_processed_timestamp`). Include `async get_connection()` context manager using `aiosqlite`. **FTS5 sync triggers are mandatory:** create `AFTER INSERT`, `AFTER DELETE`, and `AFTER UPDATE` triggers on `brain_entries` that keep `brain_entries_fts` in sync. Use the FTS5 content-sync pattern: `CREATE VIRTUAL TABLE brain_entries_fts USING fts5(title, summary, raw_content, tags, content='brain_entries', content_rowid='rowid');` with corresponding triggers to INSERT/DELETE from the FTS table.
  - Notes: Explicit SQL, no ORM. `CREATE TABLE IF NOT EXISTS` for idempotent init. FTS5 for keyword search. Without the sync triggers, FTS5 would return zero results.

- [ ] **Task 9: Create repository module**
  - File: `src/storage/repository.py`
  - Action: Create `BrainEntryRepository` class with methods: `async save(entry: BrainEntry) -> BrainEntry` (INSERT OR IGNORE by slack_ts, returns entry), `async get_by_id(id: UUID) -> BrainEntry | None`, `async get_recent(limit: int = 50) -> list[BrainEntry]`, `async get_by_type(entry_type: EntryType) -> list[BrainEntry]`, `async search_keyword(query: str, limit: int = 20) -> list[tuple[BrainEntry, float]]` (FTS5 search with rank score), `async get_digest(date: str) -> dict[str, int]` (count by type for given date), `async get_last_processed_ts() -> str | None`, `async set_last_processed_ts(ts: str)`, `async entry_exists(slack_ts: str) -> bool`
  - Notes: All methods use explicit SQL via `aiosqlite`. Keyword search uses FTS5 `MATCH` with `bm25()` ranking.

#### Phase 3: LLM Provider & Classification (HF Inference API)

- [ ] **Task 10: Create LLM provider protocol and HF implementation**
  - File: `src/classification/provider.py`
  - Action: Create `LLMProvider(Protocol)` with methods: `async classify_and_extract(text: str) -> dict` (returns `{"type": EntryType, "title": str, "summary": str}`) and `async embed(text: str) -> list[float]`. Create `HuggingFaceProvider` implementing the protocol. For `classify_and_extract`: POST to `https://api-inference.huggingface.co/models/{model}` with a structured prompt that returns JSON with type, title, and summary. Parse response, validate type against EntryType enum, default to `NOTE` if type is uncertain. For `embed`: POST to embedding model endpoint, return vector. Include retry logic (3 attempts with exponential backoff) and structured error logging.
  - Notes: Combined classification + extraction prompt: `"Analyze the following message and return a JSON object with exactly three fields:\n1. \"type\": one of [idea, task, decision, risk, arch_note, strategy, note]\n2. \"title\": a concise title (max 10 words)\n3. \"summary\": a 1-2 sentence summary\n\nRespond with ONLY valid JSON, no other text.\n\nMessage: {text}"`. Use `httpx.AsyncClient` for requests. Parse JSON response; if JSON parsing fails, attempt regex extraction of type and use truncated raw text as title/summary fallback. Return `UNCLASSIFIED` type only on total API failure (not as a classification result).

- [ ] **Task 11: Create classifier service**
  - File: `src/classification/classifier.py`
  - Action: Create `Classifier` class that wraps `LLMProvider`. Method: `async classify_and_embed(text: str) -> tuple[dict, list[float]]`. Returns `({"type": EntryType, "title": str, "summary": str}, embedding_vector)`. Calls `provider.classify_and_extract()` and `provider.embed()` independently. If classify_and_extract fails: returns `({"type": EntryType.UNCLASSIFIED, "title": text[:60], "summary": text[:200]}, embedding)` — uses truncated raw text as fallback title/summary. If embed fails: returns `(extraction_result, [])` — classification/extraction still kept. Logs all failures with structlog.
  - Notes: Decouples classification from embedding failures. Both are attempted independently. Title/summary always have values — either LLM-generated or truncated fallbacks.

#### Phase 4: Vector Store (Qdrant Cloud)

- [ ] **Task 12: Create Qdrant Cloud vector store**
  - File: `src/retrieval/vector_store.py`
  - Action: Create `VectorStore` class. Init: connect to Qdrant Cloud using `QDRANT_URL` + `QDRANT_API_KEY`. Method `async init_collection()`: create collection if not exists, vector size 384 (MiniLM output), cosine distance. Method `async upsert(id: str, vector: list[float], payload: dict)`: store vector with entry metadata. Method `async search(query_vector: list[float], limit: int = 20) -> list[tuple[str, float]]`: return (entry_id, score) pairs. Include connection error handling.
  - Notes: Vector size 384 matches `all-MiniLM-L6-v2`. Payload contains `entry_type` and `created_at` for optional filtering.

- [ ] **Task 13: Create keyword search module**
  - File: `src/retrieval/keyword_search.py`
  - Action: Create `KeywordSearch` class wrapping repository's FTS5 search. Method `async search(query: str, limit: int = 20) -> list[SearchResult]`. Delegates to `repository.search_keyword()`, wraps results as `SearchResult` with `source="keyword"`.
  - Notes: Thin wrapper to match the `SearchResult` interface for merge in the dual search orchestrator.

- [ ] **Task 14: Create dual search orchestrator**
  - File: `src/retrieval/search.py`
  - Action: Create `SearchOrchestrator` class. Method `async search(query: str, limit: int = 20) -> list[SearchResult]`. Steps: (1) Embed query via `LLMProvider.embed()`, (2) Run vector search + keyword search in parallel (`asyncio.gather`), (3) **Normalize scores:** Qdrant cosine similarity is already [0, 1]. FTS5 `bm25()` returns negative values (lower = better) — normalize by negating and scaling to [0, 1] using `score_norm = 1 / (1 + abs(bm25_score))`. (4) Merge results: entries appearing in BOTH sets get `source="both"` and boosted score = `(vector_norm + keyword_norm) / 2 * 1.5`, capped at 1.0. (5) Deduplicate by entry ID, keeping highest score. (6) Sort by normalized score descending. (7) Return top `limit` results.
  - Notes: If vector search fails (Qdrant down), return keyword results only. If embedding fails, return keyword results only. Always degrade gracefully. Normalization ensures scores from different sources are comparable before merge.

#### Phase 5: Slack Collector (read-only polling)

- [ ] **Task 15: Create Slack message collector**
  - File: `src/slack/collector.py`
  - Action: Create `SlackCollector` class. Init with `WebClient` from `slack_sdk`. Method `async collect_new_messages() -> list[dict]`. Steps: (1) Get `last_processed_ts` from repository, (2) Call `conversations.history` for channel with `oldest=last_ts` and `limit=200`, (3) **Paginate fully:** if response has `has_more=true`, continue calling with `cursor` from `response_metadata.next_cursor` until all messages are fetched, (4) If `SLACK_COLLECT_DMS=true`, call `conversations.list(types="im")` to find bot DM channel, then paginate `conversations.history` on it similarly, (5) For each message: extract `ts`, `text`, `user` (resolve display name via `users.info`), `permalink` (via `chat.getPermalink`), `thread_ts`, `reply_count`, (6) Filter out bot messages (`subtype` present) and system messages, (7) Update `last_processed_ts` to newest `ts`, (8) Return list of raw message dicts.
  - Notes: Slack SDK is sync — wrap in `asyncio.to_thread()` for async compat. Slack API default limit is 100, max 200. **Must paginate** — without pagination, messages beyond the first page are silently dropped (data loss after a long absence). Cache `users.info` results in a dict to avoid repeated lookups for the same user.

#### Phase 6: Capture Pipeline (end-to-end wiring)

- [ ] **Task 16: Create capture pipeline service**
  - File: `src/core/pipeline.py` (new file, add to structure)
  - Action: Create `CapturePipeline` class. Method `async process_messages(messages: list[dict]) -> tuple[int, int]` (returns processed_count, failed_count). For each message: (1) Check `repository.entry_exists(slack_ts)` — skip if duplicate, (2) Call `classifier.classify_and_embed(text)` — returns `(extraction_dict, embedding)` where `extraction_dict` contains `type`, `title`, `summary`, (3) Create `BrainEntry` with: `type=extraction_dict["type"]`, `title=extraction_dict["title"]`, `summary=extraction_dict["summary"]`, `raw_content=text`, `tags=[entry_type.value]`, `slack_ts=msg["ts"]`, `slack_permalink=msg["permalink"]`, `author_id=msg["user"]`, `author_name=msg["user_name"]`, `thread_ts=msg.get("thread_ts")`, `reply_count=msg.get("reply_count", 0)`, (4) Save to SQLite via `repository.save()`, (5) If embedding exists (non-empty list), upsert to Qdrant via `vector_store.upsert()`, (6) Log success/failure per entry. Method `async catch_up() -> tuple[int, int]`: calls `collector.collect_new_messages()` then `process_messages()`. Method `async capture_manual(text: str, author_name: str = "Michelle") -> BrainEntry`: for manual dashboard captures — classify + embed, create BrainEntry with `source="manual"`, `slack_ts=None`, `slack_permalink=None`, `author_id="manual"`, save and return.
  - Notes: Sequential processing (not parallel) to respect HF rate limits. Progress logged: "Processing 23/50..."

#### Phase 7: FastAPI App & Dashboard UI

- [ ] **Task 17: Create FastAPI application**
  - File: `src/main.py`
  - Action: Create FastAPI app with `lifespan` async context manager. On startup: init `Database`, init Qdrant collection, run `pipeline.catch_up()`, log results. Mount static files (if any), configure Jinja2 templates. Include structlog configuration. Create `run()` function that calls `uvicorn.run(app, host="127.0.0.1", port=8000)`.
  - Notes: Startup catch-up runs automatically. Template directory: `src/api/templates/`.

- [ ] **Task 18: Create API routes**
  - File: `src/api/routes.py`
  - Action: Create FastAPI router with endpoints:
    - `GET /` → render `dashboard.html` with recent entries + digest counter
    - `POST /refresh` → run `pipeline.catch_up()`, return htmx partial with new entries + updated digest
    - `GET /search?q={query}&type={type}` → run dual search, return htmx partial `search_results.html`. If no results, return `capture_prompt.html` partial.
    - `GET /entries` → return all entries (paginated), filterable by type
    - `POST /capture` → manual capture from dashboard (text input). Calls `pipeline.capture_manual(text)` which classifies, generates title/summary, embeds, and stores with `source="manual"`, `slack_ts=None`, `slack_permalink=None`. Returns htmx partial with the new entry card.
  - Notes: All htmx endpoints return HTML partials. Full page loads return complete templates. Manual captures bypass Slack entirely — different code path from Slack message processing.

- [ ] **Task 19: Create base HTML template**
  - File: `src/api/templates/base.html`
  - Action: Create HTML5 layout with: htmx CDN script, minimal CSS (inline or `<style>` block), header with "🧠 Second Brain" title, main content block, footer. Include htmx `hx-indicator` for loading states.
  - Notes: No CSS framework needed — keep it minimal. Dark mode friendly (dark bg, light text).

- [ ] **Task 20: Create dashboard template**
  - File: `src/api/templates/dashboard.html`
  - Action: Extends `base.html`. Layout: Top bar with "🧠 Second Brain" + Refresh button (`hx-post="/refresh"` with loading indicator). Two-column layout on desktop: LEFT = capture feed (recent entries as `entry_card.html` partials, newest first), RIGHT = search box (`hx-get="/search"` with `hx-trigger="keyup changed delay:300ms"`) + results area + digest counter showing today's captures by type with colored chips.
  - Notes: Refresh button shows "Catching up..." with htmx indicator. Search is live with 300ms debounce.

- [ ] **Task 21: Create entry card partial**
  - File: `src/api/templates/partials/entry_card.html`
  - Action: Single entry card showing: type chip (emoji + colored badge from `TYPE_DISPLAY`), title (bold), summary (truncated), author name, relative time ("3h ago"), reply count if > 0 ("💬 12 replies"), Slack permalink icon (🔗 opens in new tab). Compact card layout.
  - Notes: `created_at` formatted as relative time. Permalink opens Slack in browser.

- [ ] **Task 22: Create search results partial**
  - File: `src/api/templates/partials/search_results.html`
  - Action: List of search results. Each result shows: entry card content + source badge (🧲 vector / 🔤 keyword / 🧲🔤 both), score as percentage, "📋 Copy" button (JS `navigator.clipboard.writeText()` on the summary). Results sorted by score.
  - Notes: Copy button copies `title + summary` to clipboard. Source badge color: vector=blue, keyword=green, both=gold.

- [ ] **Task 23: Create capture prompt partial**
  - File: `src/api/templates/partials/capture_prompt.html`
  - Action: Shown when search returns no results. Display: "No matches found for '{query}'. Want to capture a thought about it?" with a text input pre-filled with query and a "Capture" button (`hx-post="/capture"`).
  - Notes: One-click capture with pre-filled text reduces friction.

#### Phase 8: Structured Logging Setup

- [ ] **Task 24: Configure structlog**
  - File: `src/main.py` (add to existing)
  - Action: Configure structlog in the app startup: JSON renderer for production, console renderer for dev (based on `LOG_LEVEL`). Add processors: timestamp, log level, caller info. Create bound loggers per module: `log = structlog.get_logger(__name__)`.
  - Notes: Every module should use `structlog.get_logger(__name__)`. Log format: `{"event": "message_classified", "entry_id": "uuid", "type": "idea", "ts": "..."}`

#### Phase 9: Tests

- [ ] **Task 25: Create test configuration and fixtures**
  - File: `tests/conftest.py`
  - Action: Create fixtures: `db` (in-memory SQLite with schema initialized), `repository` (BrainEntryRepository with in-memory db), `sample_entry` (factory function returning BrainEntry with defaults), `mock_hf_provider` (mocked HuggingFaceProvider returning configurable responses)
  - Notes: Use `pytest-asyncio` with `mode=auto`.

- [ ] **Task 26: Create model validation tests**
  - File: `tests/test_models.py`
  - Action: Test: BrainEntry creates with valid fields, BrainEntry rejects missing required fields, EntryType enum has all 8 values, TYPE_DISPLAY maps all types, SearchResult validates source literal, BrainEntry `slack_ts` is required, `archived_at` defaults to None
  - Notes: Pydantic validation tests — ensure strict mode catches bad data.

- [ ] **Task 27: Create classification tests**
  - File: `tests/test_classification.py`
  - Action: Test: HF provider parses valid JSON response → correct EntryType + title + summary, HF provider handles malformed JSON → falls back to regex type extraction + truncated text, HF provider handles ambiguous type → defaults to NOTE, HF provider handles total API failure → returns UNCLASSIFIED with truncated text fallback, Classifier handles classify failure but embed success, Classifier handles embed failure but classify success, classification prompt contains all 7 valid types, title fallback is truncated to 60 chars, summary fallback is truncated to 200 chars
  - Notes: Mock `httpx.AsyncClient` responses. Never call real HF API in tests.

- [ ] **Task 28: Create storage tests**
  - File: `tests/test_storage.py`
  - Action: Test: save entry and retrieve by ID, save duplicate slack_ts is ignored (no error), get_recent returns newest first, get_by_type filters correctly, keyword search finds matching entries, keyword search returns ranked results, get_digest returns correct counts, last_processed_ts round-trips correctly
  - Notes: Use in-memory SQLite. Each test gets fresh DB via fixture.

- [ ] **Task 29: Create retrieval tests**
  - File: `tests/test_retrieval.py`
  - Action: Test: dual search merges vector + keyword results, dual-match entries get "both" source and boosted score, vector-only results have "vector" source, keyword-only results have "keyword" source, search degrades to keyword-only when Qdrant fails, search degrades to keyword-only when embedding fails, results sorted by score descending, deduplication by entry ID works
  - Notes: Mock VectorStore and KeywordSearch. Test the merge/boost logic in SearchOrchestrator.

- [ ] **Task 30: Create README**
  - File: `README.md`
  - Action: Create with sections: Project overview (one paragraph), Prerequisites (Python 3.11+, HF account, Qdrant Cloud account, Slack app), Installation (`pip install -e .`), Configuration (copy `.env.example` to `.env`, fill in tokens), Running (`python -m src.main` or `second-brain`), Usage (open `http://localhost:8000`, explain dashboard), Architecture (link to tech-spec), Development (running tests: `pytest`)
  - Notes: Keep concise. Link to tech-spec for details.

- [ ] **Task 31: Create .gitignore**
  - File: `.gitignore`
  - Action: Create with entries: `.env`, `*.db`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `dist/`, `*.egg-info/`, `.venv/`, `venv/`
  - Notes: Prevents committing secrets (`.env`), database files, and build artifacts. Required by AGENTS.md Section 12 ("No secrets hardcoded" — committing `.env` is functionally equivalent).

- [ ] **Task 32: Create capture pipeline tests**
  - File: `tests/test_pipeline.py`
  - Action: Test: `process_messages` processes valid messages end-to-end (mock classifier + repository + vector_store), duplicate `slack_ts` is skipped via `entry_exists` check, classification failure still stores entry as Unclassified with truncated title/summary, embedding failure still stores entry in SQLite (just skips Qdrant upsert), `catch_up` calls collector then process_messages, `capture_manual` creates entry with `source="manual"` and `slack_ts=None`, progress logging emits correct counts
  - Notes: Mock all dependencies (classifier, repository, vector_store, collector). This is the critical integration seam — AGENTS.md Section 10 requires tests for every module.

- [ ] **Task 33: Create scripts directory**
  - File: `scripts/.gitkeep`
  - Action: Create empty `scripts/` directory with `.gitkeep` placeholder
  - Notes: Required by AGENTS.md Section 3 Project Structure. Reserved for future utility scripts.

### Acceptance Criteria

#### Capture Pipeline
- [ ] **AC-1:** Given the app starts up, when there are new messages in the configured Slack channel since last run, then all new messages are fetched, classified, embedded, and stored in SQLite + Qdrant
- [ ] **AC-2:** Given a message is captured, when classification succeeds, then the entry has a valid type (one of 7: Idea, Task, Decision, Risk, Arch Note, Strategy, Note) and tags=[type]
- [ ] **AC-3:** Given a message is captured, when HF classification API fails, then the entry is stored with type=Unclassified and a yellow badge appears on the dashboard
- [ ] **AC-4:** Given the same Slack message is encountered twice (overlapping refresh), when the collector processes it, then only one entry exists in SQLite (dedup by slack_ts)
- [ ] **AC-5:** Given bot DMs collection is enabled, when the app refreshes, then messages from bot DM channel are also captured alongside channel messages

#### Search & Recall
- [ ] **AC-6:** Given entries exist in both SQLite and Qdrant, when a user searches for a query, then results come from both vector similarity AND keyword matching, with source badges shown
- [ ] **AC-7:** Given an entry matches both vector and keyword search, when results are displayed, then it shows a "both" badge and appears higher in results (boosted score)
- [ ] **AC-8:** Given Qdrant Cloud is unreachable, when a user searches, then keyword-only results are returned (graceful degradation, no error shown)
- [ ] **AC-9:** Given a search returns no results, when the results area renders, then a capture prompt is shown: "No matches. Capture a thought about '{query}'?"

#### Dashboard UI
- [ ] **AC-10:** Given the dashboard loads, when entries exist, then the capture feed shows recent entries with color-coded type chips, author names, relative timestamps, and Slack permalink icons
- [ ] **AC-11:** Given the user clicks "Refresh", when new messages exist in Slack, then new entries appear in the feed without full page reload (htmx partial swap)
- [ ] **AC-12:** Given entries were captured today, when the dashboard loads, then the digest counter shows today's capture count broken down by type
- [ ] **AC-13:** Given a thread starter message is captured, when displayed on dashboard, then reply count is shown (e.g., "💬 12 replies")
- [ ] **AC-14:** Given search results are displayed, when user clicks "Copy", then the entry title + summary are copied to clipboard

#### Data Integrity
- [ ] **AC-15:** Given the app is stopped and restarted, when it starts up, then it catches up from the last processed timestamp (stored in SQLite) — no messages are missed or duplicated
- [ ] **AC-16:** Given an entry is stored, when its Slack permalink is clicked, then it opens the original Slack message in the browser

#### Title & Summary Generation
- [ ] **AC-17:** Given a Slack message is captured, when classification succeeds, then the entry has an LLM-generated title (max ~10 words) and 1-2 sentence summary — not just the raw message text
- [ ] **AC-18:** Given classification API fails, when a fallback entry is created, then `title` = first 60 chars of raw text, `summary` = first 200 chars of raw text (truncated gracefully, never empty)

#### Manual Capture
- [ ] **AC-19:** Given the user submits text via the dashboard capture form, when processed, then the entry is stored with `source="manual"`, `slack_ts=None`, `slack_permalink=None`, and is classified + embedded normally
- [ ] **AC-20:** Given a manual capture is saved, when the dashboard refreshes, then the manual entry appears in the feed with no Slack permalink icon (since it has no Slack origin)

### Testing Strategy

**Unit Tests (mocked dependencies):**
- `test_models.py` — Pydantic schema validation, enum completeness, model defaults, optional slack_ts for manual captures
- `test_classification.py` — HF response parsing (JSON with type + title + summary), fallback behavior, error handling
- `test_storage.py` — Repository CRUD, FTS5 search (verifies triggers populate FTS table), dedup logic, digest counts
- `test_retrieval.py` — Dual search merge, score normalization (Qdrant [0,1] vs FTS5 bm25), boosting, degradation, dedup
- `test_pipeline.py` — End-to-end orchestration, dedup skip, classification failure fallback, manual capture path

**Integration Tests (optional, run manually):**
- Slack collector against real workspace (requires valid token)
- HF Inference API classification (requires valid token)
- Qdrant Cloud upsert + search (requires valid credentials)

**Manual Testing Checklist:**
- [ ] Start app → dashboard loads with catch-up progress
- [ ] Post message in Slack channel → Refresh → message appears classified
- [ ] DM the bot → Refresh → DM appears in feed
- [ ] Search for a keyword → results with correct source badges appear
- [ ] Search for nonsense → capture prompt appears
- [ ] Click Slack permalink → opens in browser
- [ ] Click Copy → text on clipboard
- [ ] Stop app, post 3 messages, restart → all 3 caught up

## Additional Context

### Dependencies

```
# Core
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
aiosqlite>=0.19.0
qdrant-client>=1.7.0
slack-sdk>=3.27.0
httpx>=0.26.0
structlog>=24.1.0
python-dotenv>=1.0.0
jinja2>=3.1.0

# Dev
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

### Environment Variables

```
# Slack
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_CHANNEL_ID=C0123456789
SLACK_COLLECT_DMS=true

# Hugging Face
HF_API_TOKEN=hf_your_token_here
HF_CLASSIFICATION_MODEL=mistralai/Mistral-7B-Instruct-v0.3
HF_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Qdrant Cloud
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_COLLECTION_NAME=brain_entries

# App
LOG_LEVEL=INFO
```

### Notes

- HF model names configurable — can swap to any HF-hosted model via env var
- Startup catch-up: query Slack history since last recorded timestamp in SQLite
- Manual refresh: same logic, triggered by button click in browser UI
- Classification prompt engineered for 7 real types (Idea, Task, Decision, Risk, Arch Note, Strategy, Note). "Unclassified" is NOT a classification output — it's the error state when HF API fails.
- **Title/summary generation:** The LLM prompt returns a JSON object with `type`, `title`, and `summary` in a single API call. If JSON parsing fails, regex extraction is attempted for type, and truncated raw text serves as title (60 chars) / summary (200 chars). Title and summary are NEVER empty.
- Deduplication: Slack message `ts` is unique key in SQLite. `INSERT OR IGNORE` prevents double-capture on overlapping refreshes.
- Thread awareness: store `thread_ts` and `reply_count` per entry. Thread starters captured; replies not fetched for MVP but reply count shown in UI.
- Author tracking: `author_id` + `author_name` stored per entry. Captures all authors in channel; author filter available in UI later.
- Archival: `archived_at` nullable timestamp on every entry. No archive UI for MVP — future-proofs the schema.
- DM capture: bot DMs collected alongside channel messages, both configurable
- Auto-tags: classification type becomes the entry's tag automatically, no manual input
- Color-coded type chips: 💡 Idea (blue), ✅ Task (green), ⚖️ Decision (purple), ⚠️ Risk (red), 🏗️ Arch Note (gray), 🎯 Strategy (gold), 📝 Note (teal), ❓ Unclassified (yellow — surfaces for review)
- Search result source badges: 🧲 vector match, 🔤 keyword match — dual-match items boosted
- Slack permalink stored per entry for drill-back to original message context
- Dashboard digest: daily counter showing captures by type
- Empty search UX: "No matches found. Want to capture a thought about '{query}'?" with one-click capture
- Copy-to-clipboard button on search results for quick pasting into docs/meetings

### AGENTS.md Overrides

This spec deliberately deviates from AGENTS.md in the following areas (all decided through elicitation):

| AGENTS.md Section | Original Constraint | This Spec's Decision | ADR/Rationale |
|---|---|---|---|
| §4 Technical Stack | Qdrant (local vector store) | Qdrant Cloud | ADR-002 — persistence, zero Docker |
| §4 Technical Stack | Slack Events API, Slash commands, Webhooks | Read-only polling | ADR-003 — no public URL on laptop |
| §5.3 Classification | "Default to 'Note' if uncertain" (Note = fallback) | Note = first-class 7th type; Unclassified = error state | Socratic Questioning finding |
| §12 Security | Validate Slack request signatures | N/A in polling mode | ADR-003 Security Note |

**Action required:** AGENTS.md should be updated to reflect these decisions before or during implementation.
