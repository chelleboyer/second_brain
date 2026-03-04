# User Journeys — Second Brain

## Journey 1: Capture

**Goal:** Turn a thought, idea, or decision into a structured, searchable brain entry.

| Step | Action | Where |
|------|--------|-------|
| 1 | Type raw text into capture box | Dashboard (`/`) |
| 2 | System classifies (type, PARA, entities), embeds, checks duplicates | Pipeline |
| 3 | Entry card appears in feed | Dashboard |
| 4 | Smart suggestions shown (related entries, initiative promotion) | Entry detail |
| 5 | **NEW:** Click action buttons on suggestions (create initiative, capture) | Entry detail |

---

## Journey 2: Recall

**Goal:** Find a previously captured thought using natural language search.

| Step | Action | Where |
|------|--------|-------|
| 1 | Type search query | Dashboard search bar |
| 2 | Semantic search returns ranked results | Dashboard |
| 3 | Click through to entry detail | Entry detail (`/entry/{id}`) |
| 4 | Edit, archive, pin, or view knowledge graph links | Entry detail |

---

## Journey 3: Knowledge Graph

**Goal:** Browse the entity graph and see how captured knowledge interconnects.

| Step | Action | Where |
|------|--------|-------|
| 1 | Navigate to Knowledge Graph | `/graph` |
| 2 | See entities and relationships | Graph page |
| 3 | Click entity → see all linked entries | Entity detail |
| 4 | Generate entity summary | Entity detail |

---

## Journey 4: Strategic Simulation

**Goal:** Get a strategic recommendation for the week and turn it into action.

| Step | Action | Where |
|------|--------|-------|
| 1 | Navigate to Strategy Dashboard | `/strategy` |
| 2 | Click "▶ Run" to execute weekly simulation | Dashboard |
| 3 | See strategic move, maintenance tasks, position-building items | Simulation result |
| 4 | **NEW:** Click 💾 on any item to capture as brain entry | Simulation result |
| 5 | **NEW:** Click ♟️ on strategic move or build item to create initiative | Simulation result |
| 6 | **NEW:** Click "📋 Capture All Tasks" to batch-capture all items | Simulation result |
| 7 | **NEW:** Click "📋 Save Full Analysis" to capture complete simulation | Simulation result |

---

## Journey 5: Initiative Management

**Goal:** Create, score, and track strategic initiatives with linked evidence.

| Step | Action | Where |
|------|--------|-------|
| 1 | Navigate to Initiatives | `/strategy/initiatives` |
| 2 | Create initiative (title, description, scoring) | Initiatives page |
| 3 | Score on 5 optionality dimensions | Create form |
| 4 | View initiative detail and link brain entries | Initiative detail |
| 5 | See category breakdown and visibility matrix | Initiatives page |

---

## Journey 6: Influence Tracking

**Goal:** Log weekly interactions and track influence growth over time.

| Step | Action | Where |
|------|--------|-------|
| 1 | Select week, stakeholder, and check signal boxes | Strategy dashboard |
| 2 | Fill in concrete details for each signal | Detail inputs (new) |
| 3 | See influence score computed and added to timeline | Dashboard |
| 4 | View signal mix, stakeholder heatmap, trends | Insights panel |
| 5 | See deep insights with concrete evidence for each signal | Deep insights drawer |

---

## Journey 7: Stakeholder Management

**Goal:** Track who you influence and how.

| Step | Action | Where |
|------|--------|-------|
| 1 | Navigate to Stakeholders | `/strategy/stakeholders` |
| 2 | Add stakeholder (name, role, influence level, notes) | Stakeholders page |
| 3 | See stakeholders appear in influence logging dropdown | Strategy dashboard |

---

## Journey 8: Asset Tracking

**Goal:** Inventory your strategic assets (reputation, optionality, skills).

| Step | Action | Where |
|------|--------|-------|
| 1 | Navigate to Assets | `/strategy/assets` |
| 2 | Create asset (name, type, current value) | Assets page |
| 3 | Assets feed into weekly simulation context | Simulation |

---

## Cross-Journey Connections

```
Capture ──→ Suggestions ──→ Create Initiative (NEW)
                          ──→ Link to existing entry

Simulation ──→ Capture as Entry (NEW)
           ──→ Create Initiative (NEW)
           ──→ Batch capture tasks (NEW)
           ──→ Save full analysis (NEW)

Influence ──→ Stakeholder context ──→ Simulation input
          ──→ Signal details ──→ Evidence trail

Initiatives ──→ Link brain entries ──→ Evidence-backed scoring
```

## Remaining Dead Ends (Future Work)

| Gap | Description | Priority |
|-----|-------------|----------|
| Simulation → Calendar | No export of tasks to external calendar/todo apps | Medium |
| Slack integration | Slash commands need server deployment | Medium |
| Entity → Initiative | No direct "promote entity to initiative" from graph page | Low |
| Influence → Entries | No auto-linking of influence logs to related brain entries | Low |
