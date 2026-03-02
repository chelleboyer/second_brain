# AGENTS.md
Second Brain — Engineering Manager Memory Mode

This document defines how AI agents must operate in this repository.

The system is a local-first, operator-controlled second brain with structured memory for Engineering Management.

The goal is:
- Deterministic capture
- Structured Decision / Task / Risk memory
- Slack channel ingestion
- Transparent retrieval with receipts
- Human-in-the-loop control

Agents must optimize for clarity, auditability, and reversibility.

------------------------------------------------------------
CORE PRINCIPLES
------------------------------------------------------------

1. No Autonomous Background Agents
   - No long-running autonomous loops.
   - Slack ingestion is polling-based and operator-triggered.
   - No hidden watchers or background summarizers.

2. Human Is Always Authority
   - Slack messages are stored exactly as written.
   - Parsed fields are derived, never destructive.
   - Never overwrite raw_text.

3. Retrieval Before Synthesis
   - All LLM synthesis must be grounded in retrieved MemoryItems.
   - Always display receipts (Slack permalink, IDs).
   - Never fabricate context.

4. Deterministic Storage
   - Structured fields stored separately from embeddings.
   - Embeddings are replaceable.
   - Metadata is canonical.

5. Local-First Architecture
   - SQLite for metadata.
   - Qdrant for vectors.
   - FastAPI backend.
   - Slack ingestion via Web API polling.

------------------------------------------------------------
ENGINEERING MANAGER MEMORY OBJECT MODEL
------------------------------------------------------------

MemoryItem Types:
- Decision
- Task
- Risk
- Note
- Meeting

Required Fields:
- id (UUID)
- type
- title
- body
- raw_text
- status
- owner
- project
- source (slack|manual|web|file)
- source_ref (Slack permalink)
- happened_at
- created_at
- embedding_id
- parse_confidence

Status Rules:
Decision:
  - Active
  - Superseded
  - Reversed

Task:
  - Open
  - Closed

Risk:
  - Open
  - Watching
  - Closed

Note:
  - Active

------------------------------------------------------------
SLACK INGESTION RULES
------------------------------------------------------------

Channel:
- EM_MEMORY_CHANNEL_ID environment variable required.

Ingestion Method:
- conversations.history polling
- chat.getPermalink for canonical source_ref
- No Slack Events API
- No slash commands

Parsing Rules:
- First line determines type:
    "decision:" -> Decision
    "task:"     -> Task
    "risk:"     -> Risk
    else        -> Note

- Key-value extraction supported:
    owner:
    project:
    due:
    impact:
    likelihood:
    mitigation:
    why:
    options:

- Store full original message in raw_text.
- Parsed structured fields stored separately.
- parse_confidence = high | medium | low

Agents must never:
- Reject a Slack message.
- Modify Slack text.
- Invent missing fields.

------------------------------------------------------------
SEARCH & RETRIEVAL RULES
------------------------------------------------------------

Search must:
- Combine vector + keyword search.
- Display source badge (vector|keyword|both).
- Always include Slack permalink if source = slack.

Facets Required:
- type
- status
- owner
- project
- date range
- source

All LLM summaries must:
- Show top retrieved items.
- Provide IDs and source_ref.
- Clearly separate summary from evidence.

------------------------------------------------------------
DASHBOARDS REQUIRED
------------------------------------------------------------

1. Decision Log
   - Active Decisions
   - Sort by happened_at DESC

2. Open Loops
   - Open Tasks grouped by owner
   - Open Risks grouped by project

3. This Week
   - New Decisions
   - New Tasks
   - New Risks

------------------------------------------------------------
EVALUATION RULES
------------------------------------------------------------

Regression Harness Must Track:
- Classification accuracy
- Retrieval recall@k
- Latency per stage
- Parsing accuracy

No feature may degrade retrieval performance without logging change.

------------------------------------------------------------
SECURITY RULES
------------------------------------------------------------

- Slack token stored in environment variable.
- No token logging.
- No cross-channel ingestion.
- No auto-expanding Slack threads unless explicitly triggered.

------------------------------------------------------------
WHAT AGENTS MUST OPTIMIZE FOR
------------------------------------------------------------

- Auditability
- Clarity
- Deterministic behavior
- Manager usability
- Minimal cognitive load
- Slack-native workflow

This is not a note-taking app.
This is an Engineering Decision Memory System.