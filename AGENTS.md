# AGENTS.md

Project: Michelle Second Brain (Slack-Native Cognitive System)

---

## 1. System Philosophy

This project builds a controlled, operator-driven second brain.

It is NOT:

* An autonomous swarm
* A self-executing AI
* A speculative reasoning lab

It IS:

* A structured cognition engine
* A knowledge capture system
* A disciplined RAG platform
* A decision memory layer

Human-in-the-loop is mandatory.

---

## 2. Agent Operating Principles

All agents must:

1. Prefer clarity over cleverness.
2. Generate deterministic, readable code.
3. Avoid speculative architecture.
4. Follow existing project structure strictly.
5. Never introduce unnecessary frameworks.
6. Default to simplicity over abstraction.
7. Avoid magic behavior.
8. Fail loudly and explicitly.

No hidden side effects.
No autonomous loops.
No background execution without explicit design.

---

## 3. Project Structure

Agents must respect this structure:

```
/src
    /api
    /core
    /classification
    /retrieval
    /storage
    /slack
    /models
/tests
/scripts
AGENTS.md
README.md
```

No deviation unless explicitly approved.

---

## 4. Technical Stack

Backend:

* Python 3.11+
* FastAPI
* Pydantic
* SQLite (initial)
* Qdrant (local vector store)

LLM Layer:

* Provider must be configurable
* No provider-specific logic baked into business rules

Slack:

* Slack Events API
* Slash commands
* Webhook responses

Do not introduce:

* Kubernetes
* Celery
* Redis (unless explicitly requested)
* ORM frameworks beyond SQLModel or SQLAlchemy Core

---

## 5. Agent Roles

### 5.1 Architect Agent

Responsible for:

* Designing schemas
* Defining API contracts
* Creating folder structures
* Defining data models

Must:

* Produce diagrams in markdown or mermaid
* Justify structural decisions
* Avoid overengineering

---

### 5.2 Backend Agent

Responsible for:

* API endpoints
* Business logic
* Integration layers
* Data persistence

Must:

* Write clean, typed code
* Include docstrings
* Avoid global state
* Include error handling

---

### 5.3 Classification Agent

Responsible for:

* Converting Slack input into structured objects

Output types:

* Idea
* Task
* Decision
* Risk
* Architecture Note
* Strategy

Must:

* Return strict JSON
* Validate against Pydantic schema
* Never hallucinate fields
* Default to “Note” if uncertain

---

### 5.4 Retrieval Agent

Responsible for:

* RAG search
* Context assembly
* Structured summaries

Must:

* Return citations of stored objects
* Separate retrieval from synthesis
* Never fabricate stored data

---

### 5.5 Slack Interface Agent

Responsible for:

* Parsing commands
* Formatting responses
* Routing requests to backend services

Must:

* Keep Slack responses concise
* Avoid exposing internal errors
* Log detailed errors internally

---

## 6. Data Model Constraints

All stored objects must include:

* id (UUID)
* type (enum)
* title
* summary
* raw_content
* created_at
* project (nullable)
* tags (array)
* embedding_vector_id (nullable)

No dynamic schema mutation allowed.

---

## 7. Memory & RAG Rules

1. All stored items must be embedded.
2. Embeddings must not be recalculated unless content changes.
3. Retrieval must:

   * Fetch top N similar objects
   * Return similarity scores
4. Synthesis must:

   * Operate only on retrieved objects
   * Clearly separate “stored knowledge” from “model reasoning”

No hidden cross-memory blending.

---

## 8. Slack Command Contracts

Example commands:

```
/brain capture <text>
/brain recall <query>
/brain summarize week
/brain prd <thread>
```

Agents must:

* Validate command format
* Reject malformed input
* Provide actionable error messages

---

## 9. Error Handling Standards

All agents must:

* Use structured logging
* Raise explicit exceptions
* Never swallow errors
* Return meaningful HTTP status codes
* Log stack traces internally

---

## 10. Testing Standards

Every module must include:

* Unit tests
* Schema validation tests
* Classification JSON validation tests

No code merged without passing tests.

---

## 11. Code Generation Rules

Agents must:

* Prefer explicit over implicit
* Avoid premature optimization
* Avoid clever one-liners
* Use clear naming conventions
* Avoid circular imports
* Include type hints everywhere

---

## 12. Security Requirements

* No secrets hardcoded
* Use environment variables
* Validate Slack request signatures
* No direct execution of user-provided code
* Sanitize inputs before storage

---

## 13. Deployment Constraints

Initial deployment target:

* Local development
* Optional Windows-compatible environment

Agents must not assume:

* Linux-only behavior
* Docker-only deployment
* Cloud-native infrastructure

---

## 14. Forbidden Behaviors

Agents must NOT:

* Introduce autonomous planning loops
* Execute code automatically
* Modify files without explicit instruction
* Invent APIs
* Introduce breaking schema changes silently
* Install dependencies without listing them explicitly

---

## 15. Definition of Done

A feature is complete when:

* Code compiles
* Tests pass
* Types validate
* No TODO comments remain
* Logging is implemented
* README updated if behavior changed

---

## 16. Tone & Intent

The system must embody:

* Strategic clarity
* Calm execution
* Disciplined cognition
* Operator-first control

It must feel like a precision instrument — not an experimental lab.

---
