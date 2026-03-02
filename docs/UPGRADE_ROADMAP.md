# Second Brain — Upgrade Log & Roadmap

## Phase 1: Foundation Layer ✅ (Complete)

### What Was Built

Phase 1 transforms the system from a simple capture-and-recall pipeline into an intelligent knowledge organization platform. All changes are backward-compatible — existing data and tests continue to work unmodified.

#### 1. New Enums (`src/models/enums.py`)

| Enum | Values | Purpose |
|------|--------|---------|
| `PARACategory` | project, area, resource, archive | Tiago Forte's PARA organizational method |
| `EntityType` | project, person, technology, concept, organization | Types of extracted named entities |
| `RelationshipType` | supports, contradicts, evolves, implements, blocks, related_to | Typed directional links between entries |
| `NoveltyVerdict` | new, augment, duplicate | Outcome of incoming content analysis |

Display configs added: `PARA_DISPLAY`, `ENTITY_DISPLAY` (emoji + color + label for each).

#### 2. Enhanced Models (`src/models/brain_entry.py`)

**BrainEntry** — 5 new fields:
- `para_category` — PARA classification (default: `resource`)
- `confidence` — 0.0–1.0 classification confidence score
- `extracted_entities` — list of entity names extracted from the content
- `novelty` — whether this entry is new, augmenting existing, or duplicate
- `augments_entry_id` — UUID of the entry this one augments (if applicable)

**New Models:**
- `Entity` — named thing spanning multiple captures (name, type, aliases, description, entry_count)
- `EntityMention` — junction table linking an entity to a specific brain entry
- `EntryRelationship` — typed directional link between two entries with confidence and reason
- `ClassificationResult` — structured Pydantic model for the enhanced classifier output

#### 3. Entity Resolution Engine (`src/core/entity_resolution.py`)

Two new classes:

**EntityRepository** — Full CRUD for:
- Entities (save, get, search by name/alias, increment count)
- Entity mentions (save, query by entry or entity)
- Entry relationships (save, query by entry)

**EntityResolver** — Intelligence layer:
- **Fuzzy matching** — bigram Dice coefficient for name similarity (threshold: 0.75)
- **Alias management** — automatically adds variant names as aliases on match
- **Novelty detection** — counts shared entities between new and existing entries; marks as AUGMENT when ≥ 2 entities overlap with the same prior entry
- **Auto-linking** — creates `evolves` relationships when augmentation is detected

#### 4. Enhanced Classification Prompt (`src/classification/provider.py`)

The LLM now extracts 9 fields per message (up from 3):

| Field | Type | Description |
|-------|------|-------------|
| `type` | EntryType | idea, task, decision, risk, arch_note, strategy, note |
| `title` | string | Concise title (max 10 words) |
| `summary` | string | 1-2 sentence summary |
| `para_category` | PARACategory | project / area / resource / archive |
| `confidence` | float | 0.0–1.0 classification confidence |
| `entities` | list[dict] | Named entities with name + type |
| `project` | string? | Project name if clearly identifiable |
| `action_items` | list[str] | Extracted action items |
| `keywords` | list[str] | 3-5 topic keywords for search indexing |

Robust fallback chain preserved: API failure → JSON parse failure → regex extraction → fallback defaults.

#### 5. Updated Pipeline (`src/core/pipeline.py`)

New flow: **Collect → Classify → Extract Entities → Resolve Novelty → Link → Embed → Store**

- Entity resolution is optional (graceful degradation if not configured)
- Keywords are appended to tags for richer search
- Qdrant payloads include `para_category` for filtered vector search
- Auto-creates `evolves` relationship when augmentation detected

#### 6. Database Schema (`src/storage/database.py`)

3 new tables + 5 new columns on `brain_entries`:

```
brain_entries: +para_category, +confidence, +extracted_entities, +novelty, +augments_entry_id
entities: id, name, entity_type, aliases, description, created_at, updated_at, entry_count
entity_mentions: id, entity_id, entry_id, mention_text, created_at
entry_relationships: id, source_entry_id, target_entry_id, relationship_type, confidence, reason
```

Indexes on entity name, mention foreign keys, and relationship endpoints.

#### 7. Tests

84/84 passing (55 original + 29 new):
- Entity & relationship model tests
- EntityRepository CRUD tests
- EntityResolver matching + alias tests
- Novelty detection tests
- Bigram similarity function tests
- Enhanced BrainEntry field tests
- All enum coverage tests

---

## Phase 2: Intelligence Layer ✅ (Complete)

### What Was Built

Phase 2 adds an intelligence layer on top of the foundation — semantic entity matching, knowledge graph traversal, progressive summarization, and proactive smart suggestions. All changes are backward-compatible.

#### 2A. Semantic Entity Matching (`src/core/entity_resolution.py`, `src/retrieval/vector_store.py`)

- **Vector-based entity matching** — entities are embedded and stored in a dedicated Qdrant collection (`{collection}_entities`) alongside entry embeddings
- **Dual matching strategy** — fuzzy string matching (Dice coefficient) runs first; if no match, falls back to semantic vector similarity search
- **Per-type configurable thresholds** — each `EntityType` has its own similarity threshold:
  - Person: 0.80, Technology: 0.75, Project: 0.75, Concept: 0.65, Organization: 0.75, Default: 0.70
- **Auto-embedding** — new entities are automatically embedded and upserted to Qdrant when first resolved
- **VectorStore enhancements** — new `upsert_entity()` and `search_entities()` methods, `init_collection()` creates both entry and entity collections

#### 2B. Graph Traversal Service (`src/core/graph.py`)

New `GraphService` class with full graph query capabilities:

| Method | Description |
|--------|-------------|
| `get_backlinks(entry_id)` | Find all entries that link to a given entry |
| `get_entity_backlinks_summary(entity_name)` | Summary of all entries mentioning an entity |
| `find_relationship_chain(start_id, end_id)` | BFS shortest path with optional type filter |
| `find_typed_chain(start_id, type_sequence)` | Match specific EntryType sequences (e.g., Idea → Decision → Task) |
| `walk_graph(entry_id, depth)` | Depth-limited BFS following relationships + entity co-occurrence |
| `get_entity_cooccurrence(entity_name)` | Entities that frequently appear alongside a given entity |
| `get_entry_relationships_detail(entry_id)` | Full details of all relationships for an entry |

Constants: `MAX_WALK_DEPTH = 5`

#### 2C. Progressive Summarization (`src/core/summarization.py`, `src/storage/database.py`)

- **EntitySummary model** — new Pydantic model (`id`, `entity_id`, `summary_text`, `entry_count_at_summary`, timestamps)
- **New DB table** — `entity_summaries` with unique constraint on `entity_id` and index
- **Staleness detection** — summaries are marked stale when new entries are added (compares `entry_count_at_summary` vs current count)
- **Incremental summarization** — only re-summarizes when stale; incremental prompt updates existing summary with new entries only
- **Cross-entity strategic summary** — synthesizes knowledge across multiple entities into a strategic brief
- **Three LLM prompts** — entity summary, incremental update, and cross-entity synthesis

#### 2D. Smart Suggestions Engine (`src/core/suggestions.py`)

- **`Suggestion` model** — structured suggestion with `suggestion_type`, `message`, `related_entry_ids`, `entity_name`, and `to_dict()` for API serialization
- **Type-based rules** — configurable rules per `EntryType`:
  - Risk → surface related decisions and strategies
  - Task → link to implementing ideas or decisions
  - Decision → show risks and tasks
  - Idea → surface related strategies
  - Strategy → show supporting decisions and ideas
- **Proactive suggestions** — activity-based: "You've captured 3+ things about Entity X this week — want a summary?"
- **Entity-based overlap** — finds related entries sharing ≥ 2 entities with the current entry
- **On-demand API** — `get_suggestions_for_entry(entry_id)` returns suggestions for any stored entry
- **Pipeline integration** — suggestions generated non-blocking at end of capture flow

#### Pipeline & Wiring

- `EntityResolver` now accepts `vector_store` and `provider` for semantic matching
- `CaptureService` receives and invokes `SuggestionEngine` at end of capture
- `AppState` includes `GraphService`, `SummarizationService`, `SuggestionEngine`
- All Phase 2 services initialized in `main.py` lifespan with config-driven thresholds

#### Tests

144/144 passing (84 from Phase 1 + 60 new):
- 12 semantic entity matching tests (thresholds, vector search, embedding, custom config)
- 14 graph traversal tests (backlinks, chains, typed chains, walks, co-occurrence)
- 23 progressive summarization tests (model, CRUD, staleness, summarization, strategic summary)
- 11 smart suggestions tests (model, type rules, proactive, entity overlap, on-demand)

---

## Phase 3: Enhanced Retrieval ✅ (Complete)

### What Was Built

Phase 3 upgrades the retrieval layer from simple vector search to a multi-signal, graph-aware search engine with contextual recall.

#### 3A. Graph-Aware Search (`src/retrieval/search.py`)

- **`SearchOrchestrator`** — new multi-signal search engine replacing the old single-vector approach
- **1-hop neighbor expansion** — search results include directly linked entries (via relationships + entity co-occurrence) to surface contextual knowledge
- **Entity-scoped search** — `search_by_entity(entity_name)` finds all entries mentioning a given entity, ranked by recency and confidence
- **Timeline view** — `get_timeline(entity_name)` returns chronological knowledge evolution for an entity

#### 3B. Contextual Recall (`src/retrieval/recall.py`)

- **`RecallService`** — LLM-powered question answering over stored knowledge
- **Citation-backed answers** — every synthesized claim links to source entries by ID
- **Confidence-weighted** — higher-confidence entries rank higher in recall results
- **`RecallResult` model** — structured output with answer text, source entries, search results, and overall confidence
- **Graceful degradation** — `recall_simple()` returns raw search results without LLM when provider unavailable

#### 3C. Multi-Signal Ranking

Four-signal weighted ranking system:
| Signal | Weight | Description |
|--------|--------|-------------|
| Vector similarity | 0.40 | Semantic embedding similarity from Qdrant |
| Keyword BM25 | 0.30 | Full-text keyword matching (title, summary, raw content, tags) |
| Entity overlap | 0.15 | Shared named entities between query and result |
| Recency | 0.15 | Exponential decay with 30-day half-life |

- **Dual-match boost** — entries found by both vector and keyword search get a 1.2× multiplier
- **`_recency_score()`** — exponential decay function with configurable half-life
- **`_entity_overlap_score()`** — Jaccard-like overlap for entity lists
- **Type and entity filtering** — results can be filtered by `EntryType` and entity keywords

---

## Phase 4: Integration & Polish ✅ (Complete)

### What Was Built

Phase 4 integrates all intelligence features into user-facing API endpoints and Slack commands, with comprehensive test coverage.

#### 4A. Updated API & Routes (`src/api/routes.py`)

New endpoints:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/entities` | GET | Entity browser page with search and type filtering |
| `/entity/{id}` | GET | Entity detail page with summary, timeline, and linked entries |
| `/api/entities` | GET | JSON API for entity listing (used by search dropdowns) |
| `/entry/{id}/relationships` | GET | HTMX partial — relationship explorer for an entry |
| `/graph` | GET | Knowledge graph visualization page |
| `/api/graph` | GET | JSON API for D3.js graph data (nodes + links) |
| `/entry/{id}/suggestions` | GET | HTMX partial — smart suggestions for an entry |
| `/entity/{id}/summarize` | POST | Trigger progressive summary generation for an entity |
| `/recall` | POST | Contextual recall — citation-backed Q&A over stored knowledge |
| `/entity/{id}/timeline` | GET | HTMX partial — chronological timeline for an entity |
| `/slack/commands` | POST | Slack slash command handler endpoint |

#### 4B. Slack Command Enhancements (`src/slack/commands.py`)

Full `SlackCommandHandler` class with command routing:
| Command | Description |
|---------|-------------|
| `/brain capture <text>` | Capture with entity extraction feedback in response |
| `/brain recall <query>` | Entity-aware recall with sources |
| `/brain entity <name>` | Entity brief + linked entry count |
| `/brain summarize <entity\|project>` | Progressive summary generation |
| `/brain help` | Command reference |

#### 4C. Comprehensive Tests

47 new tests (191 total, all passing):
- **`tests/test_enhanced_retrieval.py`** (29 tests) — recency score, entity overlap, signal weights, multi-signal merge, search filters, entity-scoped search, recall results, recall service (including LLM and graceful degradation)
- **`tests/test_slack_commands.py`** (18 tests) — all 5 commands with edge cases (empty input, missing services, error handling)

---

## Phase 5: Web UI Refresh ✅ (Complete)

### What Was Built

Phase 5 transforms the UI from a basic dark dashboard with inline CSS into a modern, professional knowledge management interface with sidebar navigation, responsive design, and rich data visualization.

#### 5A. Architecture & Tooling

- **CSS extraction** — all styles moved from inline `<style>` in `base.html` to `src/api/static/css/main.css` (~650 lines)
- **Design tokens** — CSS custom properties for colors, spacing, typography, shadows, transitions
- **Dark/light themes** — `[data-theme="dark"]` and `[data-theme="light"]` with full variable sets
- **CDN dependencies** — Inter + JetBrains Mono fonts, HTMX 1.9.10, Alpine.js 3.14.8, D3.js v7
- **Static file serving** — FastAPI `StaticFiles` mount at `/static`
- **Backward-compatible** — old class names aliased to prevent breakage

#### 5B. Navigation & Layout (`base.html`)

- **Persistent sidebar** with three sections: Main (Dashboard), Knowledge (Entities, Graph), Analysis (Insights, Eval Harness)
- **Active nav state** via `{% block nav_* %}` overrides in child templates
- **Collapsible sidebar** on mobile with Alpine.js `sidebarOpen` state
- **Mobile hamburger menu** with overlay backdrop
- **Theme toggle** in sidebar footer with localStorage persistence
- **Toast notification system** — success, error, and info toast messages
- **Block structure** — `page_title`, `page_heading`, `header_actions`, `content`, and nav blocks

#### 5C. Dashboard Redesign (`dashboard.html`)

- **Stats bar** — active entries, archived entries, today's captures
- **Panel grid** — 2-column layout with capture form, search, recall, digest, and quick links
- **Enhanced capture form** — text input with submit
- **Search** — query input + type/entity filter dropdowns
- **Recall bar** — contextual Q&A input
- **Quick links** — navigation to Entities, Graph, Insights, Eval pages

#### 5D. Entry Cards v2 (`partials/entry_card.html`)

- **PARA-colored left border** — `para-project` (blue), `para-area` (green), `para-resource` (teal), `para-archive` (gray)
- **Confidence dot** — green (≥70%), yellow (40-69%), red (<40%)
- **Novelty badges** — "↗ Augment" and "♻ Duplicate" indicators
- **Entity pills** — clickable tags linking to entity search
- **PARA category** displayed in metadata line
- **Augmentation link** — "↗ Augments: [parent entry]"
- **Lazy-loaded suggestions** via `hx-trigger="intersect once"`

#### 5E. Entity Browser (`entities.html`, `entity_detail_page.html`)

- **Entity list** — search input + entity type filter tabs
- **Entity cards** — type chip, entry count, description, aliases
- **Entity detail page** — breadcrumb nav, entity type chip, generate summary button
- **Two-column detail layout** — summary + timeline (left), linked entries + co-occurring entities (right)
- **Lazy-loaded timeline** via HTMX

#### 5F. Knowledge Graph Visualization (`graph.html`)

- **D3.js force-directed layout** — entities and entries as nodes, relationships as edges
- **Color coding** — entity-type colors for entity nodes, entry-type colors for entry nodes
- **Interactive** — drag nodes, zoom/pan, click to navigate to detail pages
- **Type filter** — dropdown to filter nodes by entity type
- **Stats display** — node and link counts
- **Legend** — entity type color reference

#### 5G. Enhanced Search UI

- **Faceted filters** — type and entity dropdowns on dashboard search
- **Entity dropdown** — auto-populated from `/api/entities`
- **Search result cards** — entity pills and PARA indicators highlighted

#### 5H. Insights & Eval Polish

- **Active nav states** — sidebar highlights current page
- **Consistent layout** — all pages use sidebar-aware base.html with proper heading blocks
- **Removed redundant back-links** — navigation handled by sidebar

#### 5I. Responsive Design

- **Mobile breakpoint** at 768px — sidebar collapses, hamburger menu appears
- **Small screen** at 480px — panel grid stacks to single column
- **Touch-friendly** — larger hit targets for action buttons
- **CSS media queries** in design system
- **Print styles** — hide sidebar, show content only

#### 5J. Theme & Polish

- **Design tokens** — 4px spacing grid, Inter/JetBrains Mono typography, full color palette
- **Dark/light theme toggle** — CSS custom properties switch via `data-theme` attribute, persisted in localStorage
- **Skeleton loaders** — placeholder animations during lazy content loads
- **Toast notifications** — success/error/info floating notifications
- **PARA category border colors** — consistent visual language throughout

#### New Template Files

| Template | Purpose |
|----------|---------|
| `entry_detail.html` | Enhanced entry detail with PARA info, confidence, entity pills, relationships, suggestions |
| `entities.html` | Entity browser with search and type filters |
| `entity_detail_page.html` | Entity detail with summary, timeline, linked entries, co-occurrence |
| `graph.html` | D3.js knowledge graph visualization |
| `partials/relationships.html` | Entry relationship explorer (outgoing/incoming) |
| `partials/suggestions.html` | Smart suggestion cards |
| `partials/recall_results.html` | Contextual recall with confidence and sources |
| `partials/timeline.html` | Chronological entity timeline |

---

## Summary: What's Done vs What's Left

| Phase | Status | Key Deliverables |
|-------|--------|------------------|
| Phase 1: Foundation | ✅ Complete | Enums, models, entity resolution, enhanced classification, DB schema |
| Phase 2: Intelligence | ✅ Complete | Semantic matching, graph traversal, progressive summarization, smart suggestions |
| Phase 3: Retrieval | ✅ Complete | Graph-aware search, contextual recall, multi-signal ranking |
| Phase 4: Integration | ✅ Complete | Entity API routes, Slack enhancements, comprehensive tests (191 passing) |
| Phase 5: UI Refresh | ✅ Complete | Modern UI, entity browser, knowledge graph viz, responsive design, dark/light themes |
