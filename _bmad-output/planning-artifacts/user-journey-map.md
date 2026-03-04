# Second Brain — Complete User Journey Map

> Generated: 2026-03-03
> Scope: All pages, actions, data flows, dead ends, and automation opportunities

---

## Part 1: Application Information Architecture

### Navigation Structure (Sidebar)

| Section | Route | Template |
|---|---|---|
| **Inbox** | `GET /` | `dashboard.html` |
| **Pinned** | `GET /?filter=pinned` | `dashboard.html` |
| **By Type: Ideas** | `GET /?type=idea` | `dashboard.html` |
| **By Type: Tasks** | `GET /?type=task` | `dashboard.html` |
| **By Type: Decisions** | `GET /?type=decision` | `dashboard.html` |
| **By Type: Goals** | `GET /?type=strategy` | `dashboard.html` |
| **By Type: Notes** | `GET /?type=note` | `dashboard.html` |
| **By Type: Risks** | `GET /?type=risk` | `dashboard.html` |
| **By Type: Architecture** | `GET /?type=arch_note` | `dashboard.html` |
| **Projects** | `GET /reports/projects` | `reports/projects.html` |
| **Topics** (Entities) | `GET /entities` | `entities.html` |
| **Strategy** | `GET /strategy` | `strategy/dashboard.html` |
| **Insights** | `GET /insights` | `insights.html` |
| **Graph** | `GET /graph` | `graph.html` |
| **Weekly Report** | `GET /reports/weekly` | `reports/weekly.html` |
| **Trends** | `GET /reports/trends` | `reports/trends.html` |
| **Archive** | `GET /?show_archived=true` | `dashboard.html` |
| **Eval Harness** | `GET /eval` | `eval.html` |

### Global Actions (Available on Every Page)

| Action | Trigger | Mechanism |
|---|---|---|
| **Quick Capture** | Top-bar button or `Ctrl+K` | Modal → `POST /capture` |
| **Global Search** | Top-bar input or `/` key | HTMX `GET /search` → dropdown partial |
| **Sync from Slack** | Bell icon 🔔 | HTMX `POST /refresh` |
| **Theme Toggle** | 🌓 button | JS localStorage |
| **Link to Insights** | 📊 icon | Navigate to `/insights` |
| **Link to Graph** | 🔗 icon | Navigate to `/graph` |

---

## Part 2: All User Journeys (Numbered)

### Journey 1: Manual Capture (Brain → Entry)

1. User opens app (lands on Dashboard `/`)
2. Types text in **inline capture bar** at top of inbox, OR presses `Ctrl+K` for modal
3. Submits text → `POST /capture`
4. **Pipeline executes**: classify → extract entities → check novelty → embed → store
5. New entry card appears at top of feed (HTMX prepend)
6. If **duplicate detected**: shows duplicate notice with link to existing entry
7. If **augment detected**: entry created with `↗ Augment` badge
8. Entry card shows: type chip, confidence dot, title, author, project, timestamp
9. **Suggestions lazy-load** below the card via `GET /entry/{id}/suggestions`

**What suggestions can appear:**
- Type-based links (e.g., captured a Risk → shows related Decisions/Strategies)
- Proactive prompts ("You've captured 3 things about X — want a summary?")
- Entity overlap (entries sharing 2+ entities)
- **Initiative promotion** ("X isn't tracked as a strategic initiative — promote it?")

### Journey 2: Slack Sync → Review

1. User clicks 🔔 **Sync from Slack** button
2. `POST /refresh` triggers `pipeline.catch_up()` — pulls new Slack messages
3. Dashboard re-renders with new entries from Slack
4. Each message goes through same pipeline: classify → extract → novelty → embed → store
5. User reviews entries in the inbox feed

### Journey 3: Browse & Filter Entries

1. User lands on Dashboard
2. **KPI summary** shows: active entries, goals, tasks, streak, focus toggle
3. **Filter tabs** along top of inbox: All / Idea / Task / Decision / Goal / Note / Risk / Arch Note
4. Clicking a tab → `GET /?type=X` — filters entry feed
5. **Sidebar type links** do the same filtering
6. **Unclassified tab** shows entries that need manual classification
7. Can toggle **Show Archive** to see soft-deleted entries

### Journey 4: Focus on an Entry

1. User clicks any entry card in the feed
2. **Focus panel** loads on right side via `GET /entry/{id}/focus` (HTMX)
3. Focus panel shows: title, type chip, project, author, timestamp, pin button
4. **Actions available in focus panel:**
   - **Open in Slack** (if Slack source) — external link to Slack permalink
   - **Copy** — copies title + summary to clipboard
   - **Reclassify** — dropdown to change entry type → `POST /entry/{id}/reclassify`
   - **Archive/Snooze** — `POST /entry/{id}/archive`
   - **View Full Detail** — navigates to `/entry/{id}`
5. Entity pills link to entity search

### Journey 5: Entry Detail Page

1. User clicks entry title or "View Full Detail" from focus panel
2. `GET /entry/{id}` → full `entry_detail.html` page
3. Shows: full raw content, metadata, all fields
4. **Actions:**
   - Edit → `GET /entry/{id}/edit` → inline edit form (HTMX)
   - Save edits → `PUT /entry/{id}` (title, summary, project)
   - Cancel edit → `GET /entry/{id}/card` restores original
   - Archive/Unarchive → `POST /entry/{id}/archive|unarchive`
   - Pin/Unpin → `POST /entry/{id}/pin|unpin`
   - Delete → `DELETE /entry/{id}` (permanent)
   - Reclassify → dropdown
   - **Relationships panel** → `GET /entry/{id}/relationships` (HTMX lazy-load)
   - **Suggestions panel** → `GET /entry/{id}/suggestions` (HTMX lazy-load)

### Journey 6: Search & Recall

1. User types in global search bar (top bar) or presses `/`
2. After 300ms debounce → `GET /search?q=X&type=Y&entity=Z`
3. Multi-signal search (vector + keyword + entity + recency)
4. Results appear in dropdown partial
5. If no results → shows **capture prompt** ("Want to capture this?")

**Contextual Recall (deeper):**
6. User can access recall via `GET /recall?q=X`
7. Returns citation-backed answers from stored knowledge
8. Response includes source entries with scores

### Journey 7: Entity Browser

1. Navigate to **Topics** (`/entities`)
2. See all entities with type filter and search
3. Filter by type: Project / Person / Technology / Concept / Organization
4. Search entities by name
5. Click entity → **Entity Detail Page** (`/entity/{id}`)

### Journey 8: Entity Detail

1. On entity detail page:
   - Description, aliases, type, entry count
   - **Linked entries** — all brain entries mentioning this entity
   - **Co-occurring entities** — entities that appear alongside this one
   - **Progressive summary** — AI-generated summary of all linked entries
2. **Actions:**
   - Edit entity → `GET /entity/{id}/edit` → inline form
   - Update → `PUT /entity/{id}` (name, type, description, aliases)
   - Delete entity → `DELETE /entity/{id}` (redirects to `/entities`)
   - **Generate/Refresh Summary** → `POST /entity/{id}/summarize`
   - **Timeline view** → `GET /entity/{id}/timeline` (HTMX)

### Journey 9: Knowledge Graph Visualization

1. Navigate to **Graph** (`/graph`)
2. Page loads → fetches `GET /api/graph` (JSON nodes + edges)
3. Renders interactive visualization:
   - Entity nodes (sized by entry count)
   - Entry nodes (with type/PARA info)
   - Edges for: mentions, supports, contradicts, evolves, implements, blocks, related_to
4. **READ-ONLY** — no actions available from graph view

### Journey 10: Insights Page

1. Navigate to **Insights** (`/insights`)
2. Shows:
   - Classification health: rate, classified vs unclassified count
   - **Unclassified queue** — entries needing review
   - Type-specific backlogs: Risks, Tasks, Decisions, Strategies, Ideas
3. **Actions per entry:** same as entry card (reclassify, archive, pin)
4. Sidebar shows an unclassified alert badge via `GET /insights/unclassified-count`

### Journey 11: Weekly Report

1. Navigate to **Weekly Report** (`/reports/weekly`)
2. Shows entries grouped by day for the selected week
3. Can navigate weeks: `?weeks_ago=0|1|2…12`
4. Sections: by-day breakdown, type counts, top entities, risks, decisions, tasks
5. Uses 30-day activity sparkline and type breakdown
6. **READ-ONLY** — report view only

### Journey 12: Trends Report

1. Navigate to **Trends** (`/reports/trends`)
2. 30-day trend analysis: activity patterns, type shifts, PARA distribution
3. Week-over-week velocity comparison (recent 7d vs previous 7d)
4. **READ-ONLY** — report view only

### Journey 13: Projects Report

1. Navigate to **Projects** (`/reports/projects`)
2. All projects listed with entry counts and type distributions
3. Shows unassigned entries count
4. Click a project → **Project Detail** (`/reports/project/{name}`)
5. Project detail: entries by type, PARA breakdown
6. **READ-ONLY** — no management actions for projects themselves

### Journey 14: Eval Harness

1. Navigate to **Eval Harness** (`/eval`)
2. See past evaluation results (classification model accuracy, latency)
3. **Run eval** → `POST /eval/run` (starts background subprocess)
4. Mode options: All / Classification only / Embedding only
5. Live progress via polling: `GET /eval/status` every 2s
6. Shows live log tail and partial model results
7. Can **Abort** → `POST /eval/abort`
8. Recommendation shown for best-performing model

---

## Part 3: Strategy Section — Complete Journey Map

### Journey 15: Strategy Dashboard

1. Navigate to **Strategy** (`/strategy`)
2. **Hero bar**: influence trend direction + message
3. **Stat chips**: Influence avg, Strategic initiatives count, Stakeholder count, Asset count, Visible initiatives
4. **Navigation**: links to Initiatives, Stakeholders, Assets sub-pages
5. **Gear menu** → Example datasets (Personal / Corporate) and Factory Reset

#### Tile: This Week's Move (Simulation)
6. If simulation exists → shows: strategic move, maintenance tasks, position building moves, influence/optionality trends, top initiatives
7. **Run button** → `POST /strategy/simulate` → runs weekly simulation (LLM or rule-based fallback)
8. Simulation result replaces tile body via HTMX

#### Tile: Influence Pulse
9. Shows: average score, trend direction, sparkline of recent scores
10. Explains scoring: Advice +2, Decision changed +3, Framing adopted +3, Consultations ≤ +4 (cap 10)
11. **See Deep Insights** button → `GET /strategy/influence-insights` → HTMX loads insights panel

#### Tile: Top Initiative
12. Shows highest-scoring initiative with score breakdown
13. Lists next 3 initiatives below
14. Links to initiative detail and initiatives browser

#### Tile: Log This Week
15. **Form to log influence interactions:**
    - Date picker (week_start)
    - Stakeholder dropdown (populated from tracked stakeholders)
    - Checkboxes: Advice sought, Decision changed, Framing adopted
    - Per-signal detail fields (appear when checkbox ticked)
    - Consultation count (number input)
    - Notes textarea
16. Submit → `POST /strategy/influence` → new influence row in timeline

#### Tile: Insights & Advice
17. If ≥1 week logged:
    - Stakeholder engagement heatmap (avg score per stakeholder)
    - Signal mix breakdown (advice%, decision%, framing%) with concrete details
    - Actionable recommendations
18. If no data: "Log a few weeks to see insights"

#### Influence History Timeline
19. Shows all logged influence deltas chronologically
20. Streak counter, peak/valley week indicators
21. Deep insights drawer (loaded on demand)

### Journey 16: Initiatives Browser

1. Navigate to **Initiatives** (`/strategy/initiatives`)
2. Filter by: status (active/completed/paused/abandoned) and category (Maintenance/Supportive/Strategic)
3. Shows category breakdown and visibility matrix
4. **Create new initiative** → form with:
   - Title, description
   - Type: Scored or Mandatory
   - 5 scoring dimensions (0-5 each): Authority, Asymmetric Info, Future Mobility, Reusable Leverage, Right Visibility
   - Visibility level: Hidden / Local / Executive / Market
   - Risk level (0-5)
   - Notes
5. Submit → `POST /strategy/initiatives` → auto-computes category:
   - Score < 12 → Maintenance
   - Score 12-17 → Supportive
   - Score 18+ → Strategic
6. Card shows: category badge, visibility level, total score/25, risk

### Journey 17: Initiative Detail

1. Click initiative → `GET /strategy/initiative/{id}`
2. Full page with: category, visibility, score/25, description
3. **Score breakdown** bar chart (5 dimensions)
4. Metadata: risk level, status, created time, notes
5. **Linked Items** section:
   - Shows existing links to brain entries and entities
   - **Link search picker** → `GET /api/strategy/search-linkable?q=X` (JSON)
   - Search returns matching entries (with type emoji) and entities
   - Click result → select → optional note → Submit link → `POST /strategy/initiative/{id}/links`
   - Each link shows as a connected item, can be deleted
6. **Edit initiative** → `GET /strategy/initiative/{id}/edit` → inline edit form
7. **Delete initiative** → `DELETE /strategy/initiative/{id}`

### Journey 18: Stakeholder Management

1. Navigate to **Stakeholders** (`/strategy/stakeholders`)
2. See all tracked stakeholders with key metrics
3. **Create stakeholder** → form with:
   - Name, Role
   - Influence level (0-10), Incentives
   - Alignment score (-5 to +5)
   - Dependency on you (0-10)
   - Trust score (0-10)
   - Notes
4. Submit → `POST /strategy/stakeholders`
5. **Edit** → `GET /strategy/stakeholder/{id}/edit` → inline form → `PUT /strategy/stakeholder/{id}`
6. **Delete** → `DELETE /strategy/stakeholder/{id}`

### Journey 19: Strategic Assets

1. Navigate to **Assets** (`/strategy/assets`)
2. Filter by type: Reputation / Optionality
3. **Create asset** → form with:
   - Title, description
   - Type: Reputation or Optionality
   - Visibility level
   - **Reputation attributes** (0-10 each): Reusability, Signaling Strength, Market Relevance, Compounding Potential
   - **Optionality attributes** (0-10 each): Portability, Market Demand, Monetization Potential, Time to Deploy
   - Notes
4. Computed scores: Reputation score (avg of rep attributes), Optionality score (avg of opt attributes with inverted deploy time)
5. **Edit** → `GET /strategy/asset/{id}/edit` → inline form → `PUT /strategy/asset/{id}`
6. **Delete** → `DELETE /strategy/asset/{id}`

### Journey 20: Weekly Simulation Protocol

1. From Strategy Dashboard, click **▶ Run** in "This Week's Move" tile
2. `POST /strategy/simulate` triggers `StrategicSimulator.run_simulation()`
3. **Gathers current state**: active initiatives, stakeholders, assets, influence trend
4. **If LLM available**: sends formatted prompt to LLM, parses structured response
5. **If no LLM**: runs rule-based fallback:
   - Picks top strategic initiative as the week's move
   - Lists maintenance initiatives as maintenance tasks
   - Generates position-building suggestions
6. **Produces `WeeklySimulation`** with:
   - `strategic_move`: ONE highest-leverage action for the week
   - `maintenance_tasks`: 2-3 keep-the-lights-on tasks
   - `position_building`: 1-2 reputation/optionality compounding moves
   - `influence_trend`: up/down/flat with reason
   - `optionality_trend`: up/down/flat with reason
   - `top_initiatives`: names of top 3 initiatives
   - `raw_analysis`: full LLM output (if used)
7. Result displayed in simulation tile via HTMX

### Journey 21: Admin / Factory Reset

1. From Strategy Dashboard gear menu → "Factory Reset" button
2. Requires confirm dialog
3. `POST /admin/reset` → deletes ALL data from every table
4. Also clears Qdrant vector collections
5. Shows deletion count and link to Dashboard

### Journey 22: Slack Slash Commands

1. User types `/brain <command>` in Slack
2. `POST /slack/commands` receives the command
3. Routed through `app_state.slack_commands.handle()`
4. Examples: `/brain capture <text>`, `/brain recall <query>`
5. Returns JSON response to Slack

---

## Part 4: Data Flow Between Sections

### Entry → Entity Flow
```
Manual/Slack Text → Classifier → Entities Extracted → EntityResolver
    → New Entity created (if not existing)
    → EntityMention junction record created
    → Entity.entry_count incremented
```

### Entry → Suggestion → Initiative Promotion
```
New Entry captured → SuggestionEngine runs
    → Checks if entry.project matches any Initiative title
    → If not → "Promote to initiative?" suggestion shown
    → ⚠️ DEAD END: User sees suggestion but CANNOT act on it in-app
       (no "Promote" button that auto-creates an initiative)
```

### Strategy Data Model Connections
```
Stakeholder ←─── InfluenceDelta (via stakeholder_id)
    │
    └─── Referenced in Simulation prompt
         
Initiative ←─── InitiativeLink ──→ BrainEntry or Entity
    │
    ├─── InitiativeScores (5-dimension scoring)
    ├─── Category auto-computed from scores
    └─── Referenced in Simulation prompt

StrategicAsset
    ├─── linked_initiative_ids (list field — ⚠️ NOT wired in UI)
    └─── Referenced in Simulation prompt

WeeklySimulation
    ├─── Consumes: Initiatives, Stakeholders, Assets, InfluenceTrend
    └─── Produces: strategic_move, maintenance_tasks, position_building
         ⚠️ Output is DISPLAY ONLY — no actionable links back
```

---

## Part 5: All Dead Ends & Workflow Gaps

### 🔴 Dead End 1: Simulation Output Has No Execution Path
**Where**: Strategy Dashboard → "This Week's Move" tile  
**Problem**: The simulation produces a `strategic_move`, `maintenance_tasks`, and `position_building` recommendations — but these are **text only**. The user reads them and must:
- Manually go create tasks elsewhere
- Manually remember what to do this week
- Copy-paste the output into a to-do app

**Gap**: No "Turn into brain entry" button, no "Create initiative from this" action, no task tracking integration.

### 🔴 Dead End 2: Initiative Promotion Suggestion Is Not Actionable  
**Where**: Entry card → suggestion → "Promote to initiative?"  
**Problem**: The `SuggestionEngine._initiative_promotion_suggestions()` returns a suggestion with `action=f"promote_to_initiative:{name}"` — but the suggestions template (`partials/suggestions.html`) only **displays** the message. There is no handler for this action. The user must:
- Read the suggestion
- Manually navigate to `/strategy/initiatives`
- Manually create the initiative by hand

### 🔴 Dead End 3: Suggestions Are Display-Only
**Where**: Every entry card / entry detail  
**Problem**: All suggestions (type links, proactive prompts, entity overlap, initiative promotion) render as informational text only. None have:
- A "Create relationship" button
- A "Generate summary now" button
- A "Link this entry to that initiative" button

The user reads the suggestion and must manually perform the recommended action.

### 🔴 Dead End 4: Tasks Have No Completion/Status System
**Where**: Dashboard → tasks filtered view  
**Problem**: Entries of type "Task" have no status field (todo/in-progress/done). The only "action" is to archive them. Users must:
- Track task completion outside the app
- Use archive as a proxy for "done" (losing important completed tasks)

### 🔴 Dead End 5: Strategic Move → No Calendar/Reminder Integration
**Where**: Strategy Dashboard → simulation result  
**Problem**: "Focus on: Build authentication module" has no integrations to:
- Create a calendar event
- Set a reminder
- Push to Slack
- Create an external task

### 🔴 Dead End 6: Copy-to-Clipboard Is the Only Export
**Where**: Focus panel → Copy button  
**Problem**: The only way to extract information is copy title+summary to clipboard. No:
- Export to markdown file
- Export to PDF
- Share via email
- Push to external systems

### 🔴 Dead End 7: Reports Are Read-Only
**Where**: Weekly Report, Trends, Project Detail  
**Problem**: All report views are purely informational. The user cannot:
- Act on risks shown in the weekly report
- Create follow-ups from decisions
- Generate action items from trends

### 🔴 Dead End 8: Graph Is View-Only  
**Where**: Knowledge Graph page  
**Problem**: The graph visualization has no interactive actions — cannot:
- Create relationships by dragging nodes
- Navigate to entry/entity detail by clicking nodes
- Filter or explore interactively

### 🔴 Dead End 9: Asset ↔ Initiative Links Not Wired in UI
**Where**: Strategic Assets page  
**Problem**: The `StrategicAsset` model has a `linked_initiative_ids` field, but the assets UI (`strategy/assets.html`) has no mechanism to link assets to initiatives. The connection exists in the data model but is inaccessible.

### 🔴 Dead End 10: Influence Recommendations Are Not Actionable
**Where**: Strategy Dashboard → Insights & Advice tile  
**Problem**: Recommendations like "Schedule 1:1s with key stakeholders" or "Ship a visible artifact this week" are text-only. No:
- "Create task" button
- "Add to calendar" button
- Integration with any task management system

### 🔴 Dead End 11: No Notification or Follow-Up System
**Where**: Entire app  
**Problem**: There are no reminders, notifications, or follow-up prompts. The user must:
- Remember to log influence weekly
- Remember to run simulations
- Remember to review unclassified entries

---

## Part 6: Strategy Section — Full Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐
│   STAKEHOLDERS  │     │   INITIATIVES    │     │  STRATEGIC ASSETS │
│                 │     │                  │     │                   │
│ name, role      │     │ title, desc      │     │ title, desc       │
│ influence: 0-10 │     │ 5-dim scores     │     │ type: rep/opt     │
│ alignment: -5/+5│     │ category: auto   │     │ 4+4 attribute     │
│ dependency: 0-10│     │ visibility level │     │   scores (0-10)   │
│ trust: 0-10     │     │ risk: 0-5        │     │ visibility level  │
│ notes           │     │ status           │     │ linked_init_ids   │
└────────┬────────┘     │ linked entries   │     │   ⚠️ NOT IN UI    │
         │              │ linked entities  │     └───────────────────┘
         │              └────────┬─────────┘
         │                       │
         ▼                       │
┌─────────────────┐              │
│ INFLUENCE DELTA │              │
│ (weekly log)    │              │
│                 │              │
│ week_start      │              │
│ stakeholder ref │              │
│ advice_sought   │              │
│ decision_changed│              │
│ framing_adopted │              │
│ consultation_ct │              │
│ detail fields   │              │
│ delta_score     │              │
│  (auto-computed)│              │
└────────┬────────┘              │
         │                       │
         ▼                       ▼
┌──────────────────────────────────────────┐
│          WEEKLY SIMULATION               │
│                                          │
│ Consumes ALL above as LLM prompt context │
│                                          │
│ Produces:                                │
│  • strategic_move (1 action)             │
│  • maintenance_tasks (2-3 items)         │
│  • position_building (1-2 moves)         │
│  • influence_trend (up/down/flat)        │
│  • optionality_trend (up/down/flat)      │
│  • top_initiatives (top 3 names)         │
│  • raw_analysis (full LLM text)          │
│                                          │
│ ⚠️ OUTPUT IS TERMINAL — no downstream   │
│    actions, no entry creation, no task   │
│    creation, no calendar integration     │
└──────────────────────────────────────────┘
```

### Strategy ↔ Brain Entry Connections

| Connection | Mechanism | Status |
|---|---|---|
| Initiative → Brain Entry | `InitiativeLink` (linked_type="entry") | ✅ **Works** — manual search & link from initiative detail page |
| Initiative → Entity | `InitiativeLink` (linked_type="entity") | ✅ **Works** — manual search & link from initiative detail page |
| Brain Entry → Initiative suggestion | `SuggestionEngine._initiative_promotion_suggestions()` | ⚠️ **Display only** — no action button |
| Asset → Initiative | `linked_initiative_ids` field on `StrategicAsset` | 🔴 **Not wired** — field exists, no UI |
| Simulation → Brain Entry | None | 🔴 **Missing** — no way to save simulation output |
| Simulation → Initiative | None | 🔴 **Missing** — no way to create initiative from simulation |
| Simulation → Task | None | 🔴 **Missing** — maintenance tasks can't become tracked tasks |
| Influence Delta → Brain Entry | None | 🔴 **Missing** — influence logs don't create knowledge records |

---

## Part 7: Automation Opportunities

### Priority 1: Simulation → Brain Entries
**What**: Add "Save as Entry" buttons to each simulation output section
- "Save strategic move as Goal entry" → auto-creates BrainEntry of type STRATEGY
- "Save maintenance tasks" → creates TASK entries
- "Save positioning moves" → creates STRATEGY entries

**Impact**: Closes the biggest dead end. Simulation output flows into the knowledge graph rather than evaporating.

### Priority 2: Actionable Suggestions  
**What**: Add action buttons to suggestion cards:
- "Promote to Initiative" → pre-filled initiative form with entry title/project
- "Create Relationship" → auto-creates EntryRelationship between suggested entries
- "Generate Summary" → triggers entity summarization  
- "Link to Initiative" → opens initiative picker

**Impact**: Closes 2 dead ends. Turns suggestions from passive hints into workflow accelerators.

### Priority 3: Task Status Management
**What**: Add status field to Tasks: `todo → in_progress → done`
- Filter by status on dashboard
- "Complete" button on task entries
- Task completion feeds into influence tracking ("shipped a visible artifact")

**Impact**: Eliminates need for external task tracking for brain-originated tasks.

### Priority 4: Simulation Auto-Schedule
**What**: Auto-run simulation every Monday (or configurable day)
- Save result automatically
- Push summary to Slack
- Show "New simulation ready" alert on dashboard

**Impact**: Removes need to remember to run simulation manually.

### Priority 5: Initiative Auto-Creation from Entries
**What**: When a brain entry of type STRATEGY is captured with a project field:
- Auto-check if initiative exists for that project
- If not, auto-create a draft initiative (status: "draft")
- Link the entry to the new initiative

**Impact**: Bridges the gap between knowledge capture and strategic tracking.

### Priority 6: Influence → Brain Entry Integration
**What**: When logging an influence delta:
- Auto-create a brain entry of type NOTE capturing the week's interactions
- Tag with stakeholder entity
- Include advice/decision/framing details

**Impact**: Influence logs become searchable knowledge, appear in weekly reports.

### Priority 7: Asset → Initiative Linking UI
**What**: Add link management to asset detail/edit form
- Search and link initiatives to assets
- Show linked initiatives on asset card

**Impact**: Closes a data model gap — the field exists but is invisible.

### Priority 8: Graph Interactivity  
**What**: Make graph nodes clickable:
- Click entity node → navigate to entity detail
- Click entry node → navigate to entry detail
- Add "Create Relationship" drag interaction

**Impact**: Graph transitions from visualization to navigation tool.

### Priority 9: Report-to-Action Bridging
**What**: Add action buttons on report entries:
- Weekly report → "Follow up" button on risk entries
- Project report → "Create initiative for project" button
- Trends → "Investigate" button for anomalous periods

**Impact**: Reports become workflow triggers instead of static views.

### Priority 10: Notification System
**What**: Dashboard alerts for:
- "You haven't logged influence this week"
- "5 unclassified entries need review"
- "New simulation available"
- "Entity X mentioned 5 times this week — generate summary?"

**Impact**: Removes cognitive load of remembering to perform recurring actions.

---

## Part 8: Summary Statistics

| Metric | Count |
|---|---|
| **Total pages/views** | 17 distinct routes + partials |
| **Total user actions** | ~45 (forms, buttons, HTMX interactions) |
| **CRUD operations** | 15 (create/read/update/delete across entries, entities, stakeholders, initiatives, assets, influence, links) |
| **Dead ends identified** | 11 |
| **Automation opportunities** | 10 |
| **Strategy data entities** | 5 (Stakeholder, Initiative, Asset, InfluenceDelta, WeeklySimulation) |
| **Cross-section bridges** | 2 working, 6 missing |

### The Fundamental Gap

The app is excellent at **capture and classification** (Journey 1-2) and **analysis** (Journey 10-12). The Strategy section is well-modeled but is a **closed loop** — its outputs (simulations, recommendations) don't flow back into the brain entry system. The biggest architectural gap is:

> **Simulation produces text → User reads it → User must act outside the app**

This is the single highest-impact dead end to close. Every simulation run should produce one-click actionable outputs that feed back into entries, tasks, and initiative management within the system.
