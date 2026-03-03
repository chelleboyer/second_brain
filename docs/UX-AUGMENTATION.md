# Second Brain UX Augmentation: Scope + Requirements

## 1. Purpose

This UX scope defines the executive command-center experience for the Second Brain application.

The goal is:

* Frictionless capture
* Fast triage and review
* Structured recall
* Scalable object model (OOUX-aligned)
* Optional gamification layer (toggleable)

The design must feel modern, structured, and executive-grade — not playful, cluttered, or bubbly.

---

## 2. UX Philosophy

### 2.1 Primary Experience

The application is centered around one core object:

> **BrainEntry**

Everything in the UI is either:

* A list of BrainEntries
* A focused BrainEntry
* A transformation of BrainEntries (search, filter, digest)

The UX must guide attention in this order:

1. Capture / Search (orientation)
2. Inbox (what needs attention)
3. Priority Queue (what to process)
4. Focus Panel (deep work)
5. Optional Insights / Gamification

---

## 3. Core Navigation Structure

### 3.1 Global Top Bar

**Purpose:** Orientation + Primary Action

Must include:

* App name / logo
* Current scope selector (Today / This Week / All Time)
* Global search bar (dominant placement)
* Primary CTA button: `+ Capture`
* Notifications indicator
* Profile/settings access

Requirement:

* Capture must be accessible within 1 click from anywhere.
* Search must support keyboard focus shortcut.

---

### 3.2 Left Sidebar (Object Navigation)

**Section 1 – System States**

* Dashboard
* Inbox
* Pinned
* Snoozed
* Filed
* Archive

**Section 2 – Life Areas (optional layer)**

* Work
* Personal
* Finance
* Health
* Learning
* Travel

**Section 3 – Tools**

* Projects
* Goals
* Tasks
* Milestones
* Resources
* Notes
* Journal

Requirement:

* Sidebar must visually group sections.
* Only one active selection at a time.
* Active state must be visually clear.

---

## 4. Dashboard Layout

The main dashboard must follow a three-column executive layout.

---

### 4.1 KPI Summary Row (Top Section)

Displays live system state.

Required cards:

* New Entries (count)
* In Review (count)
* Pinned (count)
* Completed / Filed (progress bar)
* Optional: Daily XP (if gamification enabled)

Requirement:

* Cards must be scannable in under 3 seconds.
* No more than 5 summary cards.
* Must visually prioritize “New” and “In Review.”

---

### 4.2 Center Column – Priority Queue

This is the primary work surface.

Displays BrainEntry cards sorted by priority.

Each card must include:

* Type chip (Idea / Task / Decision / Note / Resource)
* Title (first line of content)
* Source (Slack channel / person)
* Timestamp
* Tag preview (max 2)
* Inline quick actions:

  * Review
  * Done / File
  * Pin
  * Snooze (contextual)

Requirements:

* Only one card may appear visually “selected.”
* Selected card must be visually highlighted.
* Scrolling must preserve context.

---

### 4.3 Right Panel – Entry Focus

Displays the selected BrainEntry in full.

Must include:

* Full content
* Metadata (author, source, replies, timestamp)
* Tag list
* Primary action row:

  * Open in Source
  * Copy
  * Reclassify
  * File
  * Snooze
  * Add to Project

Optional:

* Related Entries (based on tags or source)
* Linked Projects

Requirement:

* This panel must feel visually dominant.
* Primary action must be visually emphasized.
* Layout must support long-form content.

---

## 5. Object Model (OOUX-Aligned)

### 5.1 Core Object: BrainEntry

Attributes:

* id
* content
* entry_type
* created_at
* source_type
* source_reference
* author
* tags
* disposition
* linked_project_id
* linked_goal_id
* priority_score

Disposition values:

* inbox
* review
* pinned
* filed
* snoozed
* archived

---

### 5.2 Supporting Objects

* Project
* Goal
* Milestone
* SavedSearch
* CaptureSession
* Habit (optional layer)

Each supporting object must link to BrainEntry via relationships.

---

## 6. Search & Recall Requirements

### 6.1 Global Search

Must support:

* Keyword search
* Vector similarity search
* Combined search (default)
* Filter by:

  * Type
  * Date range
  * Source
  * Tags

Search must return BrainEntry objects only.

---

### 6.2 Saved Searches

Users must be able to:

* Save filtered queries
* Name saved searches
* Access saved searches in sidebar or right panel

---

## 7. Gamification Layer (Optional / Toggleable)

Must be disable-able via “Simple Mode.”

If enabled:

Include:

* Daily XP counter
* Streak tracking
* Habits War leaderboard
* Level indicator

Requirements:

* Gamification must not interfere with Inbox workflow.
* Must be visually secondary to Priority Queue.

---

## 8. Simple Mode

When enabled:

* Hides:

  * XP
  * Habits War
  * Leaderboards
  * Optional analytics
* Leaves:

  * Capture
  * Inbox
  * Priority Queue
  * Focus Panel
  * Search

Purpose:

* Provide minimal cognitive load mode.

---

## 9. Visual System Requirements

### 9.1 Tone

* Executive
* Structured
* Calm
* Intentional

### 9.2 Color

* Dark base (charcoal/graphite)
* One primary accent color
* Limited badge colors

### 9.3 Typography

* Clear hierarchy:

  * H1 (page)
  * H2 (section)
  * Body
  * Metadata

### 9.4 Attention Rules

* Only one dominant highlight at a time.
* Avoid multi-colored UI clutter.
* Use spacing to create order.

---

## 10. Non-Functional Requirements

* Fully responsive
* Keyboard navigation supported
* State persistence between sessions
* Load under 2 seconds for dashboard
* Works without gamification layer enabled

---

## 11. Out of Scope (Phase 1)

* Multi-user collaboration
* Marketplace or template sales
* Public sharing
* AI auto-planning engine
* Full life management system

---

## 12. Phase 1 MVP Boundary

Must include:

* Capture
* Inbox
* Disposition states
* Priority Queue
* Focus Panel
* Global Search
* Saved Searches
* Simple Mode toggle

Optional for MVP:

* XP / Habits War

---
