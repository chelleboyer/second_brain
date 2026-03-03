## Component Architecture

This is structured so you can hand it to:

* yourself
* a frontend agent
* or your future AI factory that you absolutely will build 😄

---

# 1. Layout Components

## 1.1 `AppShell`

**Responsibility:**
Provides global structure and layout grid.

**Contains:**

* `TopBar`
* `Sidebar`
* `MainContentArea`
* `RightPanel` (conditionally rendered)

**Requirements:**

* 3-column layout on desktop
* Collapsible sidebar
* Responsive collapse to stacked layout on tablet/mobile

---

## 1.2 `TopBar`

**Purpose:** Orientation + primary action

**Subcomponents:**

* `AppLogo`
* `ScopeSelector` (Today / Week / All Time)
* `GlobalSearchInput`
* `PrimaryCaptureButton`
* `NotificationIcon`
* `UserMenu`

**Events:**

* `onCaptureClick`
* `onSearchSubmit`
* `onScopeChange`

---

## 1.3 `Sidebar`

### Sections:

* `SystemStateNav`
* `LifeAreaNav` (optional)
* `ToolsNav`
* `SimpleModeToggle`

---

### 1.3.1 `NavItem`

Props:

* label
* icon
* active
* badgeCount
* route

Must visually support:

* active state
* unread count badge

---

# 2. Dashboard Components

## 2.1 `DashboardView`

Composed of:

* `KpiSummaryRow`
* `PriorityQueue`
* `FocusPanel`
* `OptionalInsightsPanel` (gamification, quick add, etc.)

---

## 2.2 `KpiSummaryRow`

### Subcomponent: `KpiCard`

Props:

* label
* value
* subtext
* trendIndicator (optional)
* highlight (boolean)

Used for:

* New Entries
* In Review
* Pinned
* Completed
* Daily XP (optional)

---

# 3. Priority Queue (Core Work Surface)

## 3.1 `PriorityQueue`

Props:

* entries[]
* activeEntryId
* filterState

Subcomponents:

* `QueueFilterTabs`
* `BrainEntryCard[]`

---

## 3.2 `QueueFilterTabs`

Tabs:

* All
* Ideas
* Tasks
* Decisions
* Notes
* Resources

Must show count per tab.

---

## 3.3 `BrainEntryCard`

This is your core reusable object component.

Props:

* id
* entry_type
* title
* preview
* source
* timestamp
* tags[]
* disposition
* isSelected
* priorityScore

Must render:

Header:

* TypeChip
* Timestamp

Body:

* Title
* Preview (1–2 lines max)
* Source

Footer:

* QuickActions

---

### 3.3.1 `TypeChip`

Variants:

* Idea
* Task
* Decision
* Note
* Resource
* Reminder

Must use consistent color mapping.

---

### 3.3.2 `QuickActions`

Buttons:

* Review
* File / Done
* Pin
* Snooze
* Start (if task)

Must be inline and minimal.

---

# 4. Focus Panel

## 4.1 `FocusPanel`

Props:

* entry (BrainEntry)

Subcomponents:

* `FocusHeader`
* `FocusContent`
* `TagList`
* `PrimaryActionRow`
* `LinkedObjectsSection`
* `RelatedEntriesSection`

---

## 4.2 `FocusHeader`

Displays:

* Title
* TypeChip
* Source
* Timestamp
* ReplyCount (if Slack)

---

## 4.3 `PrimaryActionRow`

Buttons:

* OpenInSource
* Copy
* Reclassify
* File
* Snooze
* AddToProject

One action must be styled as primary.

---

## 4.4 `LinkedObjectsSection`

Displays:

* LinkedProjectCard
* LinkedGoalCard
* LinkedMilestoneCard

---

## 4.5 `RelatedEntriesSection`

Auto-suggested entries based on:

* tags
* source
* time proximity

---

# 5. Capture Components

## 5.1 `CaptureModal`

Modes:

* Quick Capture
* Structured Capture

Fields:

* Content
* Entry Type
* Tags
* Link to Project
* Priority

Actions:

* Save
* Save & Review

---

## 5.2 `QuickAddPanel`

Optional right-side widget.

Buttons:

* Note
* Task
* Goal
* Milestone

---

# 6. Search System

## 6.1 `GlobalSearchInput`

Supports:

* keyword
* vector search
* auto-suggest
* recent searches

---

## 6.2 `SearchResultsView`

Displays:

* `BrainEntryCard[]`
* Filter panel

---

## 6.3 `FilterPanel`

Filters:

* Entry Type
* Date Range
* Source
* Tags
* Disposition

---

## 6.4 `SavedSearchList`

Props:

* savedSearches[]

Actions:

* Run
* Edit
* Delete

---

# 7. Gamification Layer (Optional)

## 7.1 `DailyXpCard`

Displays:

* XP earned
* Streak
* Level

---

## 7.2 `HabitsWarLeaderboard`

Displays:

* User ranking
* XP values
* Trend chart

---

## 7.3 `SimpleModeToggle`

State:

* simpleMode: boolean

If true:

* Hide XP
* Hide leaderboard
* Hide streak visuals

---

# 8. Supporting Components

## 8.1 `ProjectCard`

## 8.2 `GoalCard`

## 8.3 `MilestoneCard`

Used in:

* LinkedObjectsSection
* Dashboard widgets

---

## 8.4 `DispositionBadge`

Values:

* Inbox
* Review
* Pinned
* Filed
* Snoozed
* Archived

---

# 9. State Management Domains

You should separate state into domains:

### BrainEntryDomain

* entries
* activeEntry
* filters
* searchQuery

### CaptureDomain

* captureMode
* draftEntry

### NavigationDomain

* activeRoute
* sidebarState
* simpleMode

### GamificationDomain (optional)

* xp
* streak
* level

---

# 10. MVP Component Set (If You Want Discipline)

If we strip this down to pure power:

Required:

* AppShell
* TopBar
* Sidebar
* PriorityQueue
* BrainEntryCard
* FocusPanel
* CaptureModal
* GlobalSearchInput
* SavedSearchList
* SimpleModeToggle

Everything else is phase 2.

---

