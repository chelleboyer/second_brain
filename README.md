# 🧠 Second Brain

A Slack-native cognitive system that captures thoughts, classifies them with AI, resolves entities, detects duplicates, and surfaces structured reports — all through a local web dashboard. Includes a **Reputation & Optionality Engine** for strategic career positioning.

## Prerequisites

- **Python 3.11+**
- **Slack App** — Bot token with `channels:history`, `im:history`, `users:read`, `chat:write` scopes
- **Hugging Face Account** — Free API token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
- **Qdrant Cloud Account** — Free tier at [cloud.qdrant.io](https://cloud.qdrant.io)

## Installation

```bash
git clone https://github.com/chelleboyer/second_brain.git
cd second_brain

python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

pip install -e ".[dev]"
```

## Configuration

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS
```

Edit `.env` and fill in your tokens:

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Slack bot token (`xoxb-...`) |
| `SLACK_CHANNEL_ID` | Channel ID to monitor (`C0123456789`) |
| `SLACK_COLLECT_DMS` | Also collect bot DMs (`true`/`false`) |
| `HF_API_TOKEN` | Hugging Face API token (`hf_...`) |
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key |

## Slack App Setup

1. Create a new app at [api.slack.com/apps](https://api.slack.com/apps)
2. **OAuth & Permissions** → **Bot Token Scopes**:
   - `channels:history`, `groups:history`, `mpim:history`, `im:history` — read messages
   - `users:read` — resolve display names
   - `chat:write` — (optional, for future features)
3. Install to workspace, copy the **Bot User OAuth Token** into `.env`
4. Find your channel ID: right-click channel → **View channel details** → scroll to bottom
5. Invite the bot: `/invite @YourBotName` in the channel

## Running

```bash
.venv\Scripts\activate   # Windows
second-brain             # or: python -m src.main
```

Dashboard opens at **http://localhost:8000**.

On startup the app initializes SQLite, connects to Qdrant Cloud, runs a Slack catch-up for new messages, and starts the web server. If Slack catch-up fails, the dashboard still starts — use manual capture and fix Slack later.

## Features

### Capture & Classification

- **Slack ingest** — Polls a channel (and optionally DMs) for new messages, classifies each with an LLM
- **Manual capture** — Multi-line textarea with `Ctrl+Enter` submit and character counter
- **Duplicate detection** — 2-tier: exact content hash match + vector similarity ≥ 0.92
- **AI classification** — Llama 3.1 8B classifies entries by type, project, PARA category, and tags
- **Reclassify** — Re-run classification on any entry from its detail page
- **Edit** — Inline editing of title, summary, type, project, PARA category, and tags

### Entity Resolution & Knowledge Graph

- **3-tier entity matching** — Exact → fuzzy bigram → semantic embedding matching
- **Auto-linking** — New captures automatically link to matching active initiatives via fuzzy title matching
- **Entity CRUD** — Edit name, type, description, and aliases for any entity; delete with cascading mention cleanup
- **Entity pages** — Each entity has a detail page with backlinks, co-occurring entities, and timeline
- **Knowledge graph** — Interactive D3.js force-directed graph showing entity connections
- **Progressive summarization** — Generate LLM summaries for entities from their linked entries
- **Relationship viewer** — See how entries connect through shared entities

### Search & Recall

- **Dual search** — Vector similarity (Qdrant) + keyword (SQLite FTS5) with merged, deduplicated results
- **Recall** — Ask natural-language questions; retrieves relevant entries and generates an LLM-synthesized answer
- **Filters** — Filter by entry type, entity, and PARA category
- **Confidence scoring** — Visual confidence dots on search results

### Reports

- **Weekly Report** (`/reports/weekly`) — Entries grouped by day for the past 7 days, with type counts and navigation between weeks
- **Project Report** (`/reports/projects`) — All projects with entry counts, top types, and date ranges; drill into any project for full entry list
- **Trends Report** (`/reports/trends`) — 30-day sparkline activity, type distribution breakdown, most active entities, and a day-by-day activity heatmap

### Insights

- **Classification health** — Accuracy stats, unclassified queue with bulk reclassify
- **Strategic entries** — Filtered views of risks, tasks, decisions, and strategy notes
- **Type distribution** — Breakdown of entries by classification type

### Strategic Positioning (Reputation & Optionality Engine)

- **Initiative scoring** — 5-question Move Evaluation Engine rates every project on authority, asymmetric info, future mobility, reusable leverage, and visibility (0–25 scale → Maintenance / Supportive / Strategic)
- **Stakeholder mapping** — Track influence level, alignment, dependency, and trust for key people
- **Strategic assets** — Score reputation assets (reusability, signaling, market relevance, compounding) and optionality assets (portability, market demand, monetization, deploy speed)
- **Influence tracking** — Weekly logs of advice sought, decisions changed, framing adopted; auto-computed trend
- **Weekly simulation** — LLM-driven (with rule-based fallback) strategic review that outputs one strategic move, maintenance tasks, and position-building priorities
- **Full CRUD** — Inline edit forms for initiatives (scores, status, visibility), stakeholders (all metrics), and assets (all scores); delete any item from its card
- **Initiative promotion** — Suggestion engine recommends promoting unlinked project entities into scored initiatives
- **Factory reset** — One-click nuke of all data (SQLite + Qdrant vectors) from the Strategy dashboard, with confirmation
- **Strategy dashboard** (`/strategy`) — KPI meters, visibility matrix, simulation runner, influence history, and **Load Examples** button with pre-built datasets (Corporate Engineer or Personal/Solopreneur)

### Eval Harness

- **Model benchmarking** — Run classification eval against test data
- **Run management** — Start, monitor, and abort eval runs from the UI

### Slack Commands

```
/brain capture <text>    — Capture a thought
/brain recall <query>    — Semantic recall
/brain summarize week    — Weekly summary
/brain prd <thread>      — Generate PRD from thread
```

## Architecture

```
Slack ──poll──▶ Collector ──▶ Pipeline ──▶ Classifier (HF Llama 3.1 8B)
                                │  │              │
                                │  ▼              ▼
                                │ Entity       Qdrant Cloud
                                │ Resolver     (bge-small-en-v1.5, 384d)
                                │  │
                                ▼  ▼
                             SQLite (FTS5)
                                │
                   ┌────────────┼────────────┬──────────────┐
                   ▼            ▼            ▼              ▼
              Dashboard    Reports    Knowledge      Strategy Engine
                                       Graph        (Reputation &
                                                     Optionality)
            (FastAPI + HTMX + Alpine.js + D3.js)
```

### Key Components

| Component | Path | Purpose |
|-----------|------|---------|
| Pipeline | `src/core/pipeline.py` | Orchestrates capture: classify → deduplicate → store → resolve entities → auto-link initiatives |
| Classifier | `src/classification/classifier.py` | LLM-based entry classification via HF Inference API |
| Entity Resolver | `src/core/entity_resolution.py` | 3-tier entity matching and linking |
| Graph Service | `src/core/graph.py` | Knowledge graph queries and co-occurrence analysis |
| Suggestion Engine | `src/core/suggestions.py` | Related entry + initiative promotion suggestions |
| Summarization | `src/core/summarization.py` | Progressive entity summarization |
| Example Datasets | `src/core/example_datasets.py` | Pre-built strategy datasets loadable from the UI |
| Move Evaluator | `src/core/evaluation.py` | 5-dimension initiative scoring engine |
| Influence Tracker | `src/core/evaluation.py` | Weekly influence delta tracking and trending |
| Strategic Simulator | `src/core/simulation.py` | Weekly strategic simulation protocol |
| Strategy Repository | `src/storage/strategy_repository.py` | Stakeholder, initiative, asset, influence persistence |
| Repository | `src/storage/repository.py` | SQLite CRUD with FTS5 search |
| Vector Store | `src/retrieval/vector_store.py` | Qdrant embedding storage and similarity search |
| Routes | `src/api/routes.py` | All FastAPI route handlers |

### Data Model

All entries include: `id` (UUID), `type` (enum), `title`, `summary`, `raw_content`, `created_at`, `project` (nullable), `para_category`, `tags` (array), `embedding_vector_id`, `content_hash`, `novelty`.

## Development

```bash
pytest                        # Run tests (261 tests)
pytest -x -q                  # Quick run, stop on first failure
LOG_LEVEL=DEBUG second-brain  # Debug logging
```

### Seed Demo Data

```bash
python -m scripts.seed_strategy_demo
```

Populates the strategy engine with example stakeholders, initiatives, assets, and influence records for exploring the dashboard. You can also load example datasets directly from the UI — click **📦 Load Examples** on the Strategy dashboard and choose between:

- **Personal / Solopreneur** — Freelancer building audience, shipping side projects, and growing consulting revenue
- **Corporate Engineer** — Senior engineer navigating corporate influence, visibility, and career positioning

## Entry Types

| Type | Emoji | Description |
|------|-------|-------------|
| Idea | 💡 | New ideas and concepts |
| Task | ✅ | Actionable tasks |
| Decision | ⚖️ | Decisions made |
| Risk | ⚠️ | Identified risks |
| Arch Note | 🏗️ | Architecture notes |
| Strategy | 🎯 | Strategic thinking |
| Note | 📝 | General notes |
| Unclassified | ❓ | Classification failed (error state) |

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `missing_scope` from Slack | Bot token lacks required scopes | Add scopes in Slack app settings → reinstall → copy new token |
| `403 Forbidden` from Qdrant | Invalid API key | Copy key from Qdrant Cloud dashboard → paste into `.env` |
| `Port 8000 already in use` | Previous instance running | Kill Python processes or use a different port |
| `ModuleNotFoundError` | Dependencies not installed | Run `pip install -e ".[dev]"` |
| Slack catch-up returns 0 messages | Bot not invited to channel | `/invite @YourBotName` in the channel |
