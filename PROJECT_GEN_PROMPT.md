# PROJECT_GEN_PROMPT.md

Reusable Prompt Pack for Generating New Modules in Michelle’s Second Brain

---

## Purpose

This prompt standardizes how AI generates new modules inside this project.

It prevents:

* Overengineering
* Framework drift
* Abstraction spirals
* Hidden dependencies
* Architectural improvisation

Every new feature must be generated using this prompt.

---

# MASTER GENERATION PROMPT

Paste the section below into your coding model when creating a new module.

---

You are generating a new module inside an existing Slack-native Second Brain system.

Follow ALL constraints strictly.

## 1. Project Context

This system is:

* Python 3.11+
* FastAPI backend
* SQLite (initial DB)
* Qdrant vector store
* Slack as primary interface
* Human-in-the-loop always

This is NOT an autonomous agent framework.

This is a structured cognition system.

Do not introduce:

* Celery
* Redis
* Background worker frameworks
* Kubernetes
* ORM frameworks beyond SQLAlchemy Core or SQLModel
* Event-driven orchestration systems
* Microservices

Keep it simple and local.

---

## 2. Module Name

Module to generate: `{MODULE_NAME}`

It must live in:

```
/src/{MODULE_NAME}
```

---

## 3. Required Output Structure

You must generate:

1. Folder structure
2. Pydantic models
3. Service layer
4. API router (if applicable)
5. Minimal tests
6. Clear docstrings
7. Explicit dependencies

No placeholders.
No TODO comments.
No pseudo-code.

---

## 4. Architectural Rules

* No global state.
* No circular imports.
* All functions must be typed.
* All public methods must include docstrings.
* No hidden side effects.
* Fail loudly.
* Log structured errors.

If persistence is required:

* Use repository pattern (simple, not abstract-heavy).
* Keep SQL explicit.
* Do not auto-migrate schema.

---

## 5. Classification Modules (If Applicable)

If module involves classification:

* Output must validate against strict Pydantic schema.
* LLM response must be parsed safely.
* No blind JSON trust.
* Provide validation wrapper.

If uncertain classification:

* Default to "Note".

---

## 6. Retrieval Modules (If Applicable)

If module involves RAG:

* Separate retrieval from synthesis.
* Return similarity scores.
* Include object IDs in responses.
* Never fabricate memory.
* Provide deterministic retrieval function.

---

## 7. Slack Integration Rules

If module connects to Slack:

* Validate Slack signature.
* Do not expose stack traces in Slack responses.
* Return concise Slack output.
* Log detailed errors internally.

---

## 8. Logging Standards

Use structured logging:

* Log level
* Event name
* Object ID (if available)
* Error details (if applicable)

No print statements.

---

## 9. Tests Required

Must include:

* Schema validation test
* Happy path test
* Failure path test

Use pytest.

---

## 10. Deliverables Format

Output in this order:

1. Folder structure
2. File-by-file code blocks
3. Explanation of design decisions
4. Explicit dependency list
5. Example usage

No commentary outside those sections.

---

# QUICK MODE (For Small Features)

If feature is small (single function or small enhancement), use this lighter version:

---

You are extending an existing FastAPI + SQLite + Qdrant project.

Constraints:

* No new frameworks.
* No new infrastructure.
* No new architectural layers.
* Keep changes isolated.
* Maintain typing.
* Maintain structured logging.
* Provide tests.

Generate only:

* Modified files
* New files
* Tests

Do not rewrite unrelated modules.

---

# ADVANCED MODE (For Architectural Changes)

If you are changing schema or core architecture, prepend this:

---

Before generating code:

1. Explain why architectural change is necessary.
2. Provide migration impact analysis.
3. Identify risks.
4. Confirm backward compatibility.
5. Propose rollback strategy.

Only then generate code.

---

# Michelle-Specific Intent Alignment Layer

Every module must support:

* Structured memory
* Decision capture
* Clear retrieval
* Strategic clarity

This system should feel like:

* A calm executive assistant
* A disciplined architect
* A precise knowledge vault

It must never feel chaotic.

---

# Example Invocation

When starting classification module:

Replace:

`{MODULE_NAME}`

With:

`classification`

Then paste the full MASTER GENERATION PROMPT into the coding model.

---

# Why This Matters

You’re not building random AI tools.

You’re building:

A sovereign cognition layer
That supports enterprise systems
Without turning into a research experiment.

This file keeps you in execution mode.

---
