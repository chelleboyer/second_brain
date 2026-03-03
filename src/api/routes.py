"""API routes for Second Brain dashboard."""

from datetime import datetime, timezone
import os
from uuid import UUID

import structlog
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.deps import app_state, templates
from src.models.enums import (
    TYPE_DISPLAY,
    PARA_DISPLAY,
    ENTITY_DISPLAY,
    VISIBILITY_DISPLAY,
    INITIATIVE_CATEGORY_DISPLAY,
    INITIATIVE_TYPE_DISPLAY,
    ASSET_CATEGORY_DISPLAY,
    CLASSIFIABLE_TYPES,
    EntryType,
    EntityType,
    NoveltyVerdict,
    PARACategory,
    VisibilityLevel,
    InitiativeCategory,
    InitiativeType,
    AssetCategory,
)

log = structlog.get_logger(__name__)

router = APIRouter()


# ── Shared template context ──────────────────────────────────────

def _relative_time(dt: datetime) -> str:
    """Convert datetime to human-readable relative time string."""
    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    elif seconds < 604800:
        days = seconds // 86400
        return f"{days}d ago"
    else:
        return dt.strftime("%b %d")


def _shared_ctx(request: Request, **extra) -> dict:
    """Build shared template context dict."""
    return {
        "request": request,
        "type_display": TYPE_DISPLAY,
        "para_display": PARA_DISPLAY,
        "entity_display": ENTITY_DISPLAY,
        "visibility_display": VISIBILITY_DISPLAY,
        "initiative_category_display": INITIATIVE_CATEGORY_DISPLAY,
        "initiative_type_display": INITIATIVE_TYPE_DISPLAY,
        "asset_category_display": ASSET_CATEGORY_DISPLAY,
        "relative_time": _relative_time,
        "entry_types": list(EntryType),
        "entity_types": list(EntityType),
        "para_categories": list(PARACategory),
        "visibility_levels": list(VisibilityLevel),
        "initiative_categories": list(InitiativeCategory),
        "initiative_types": list(InitiativeType),
        "asset_categories": list(AssetCategory),
        "classifiable_types": CLASSIFIABLE_TYPES,
        **extra,
    }


# ── Dashboard ────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    type: str = Query(default=""),
    show_archived: bool = Query(default=False),
    filter: str = Query(default=""),
) -> HTMLResponse:
    """Render the main dashboard with capture feed, filters, and digest."""
    if filter == "pinned":
        entries = await app_state.repository.get_pinned(limit=50)
    elif type:
        try:
            entry_type = EntryType(type)
            entries = await app_state.repository.get_by_type(
                entry_type, include_archived=show_archived
            )
        except ValueError:
            entries = await app_state.repository.get_recent(
                limit=50, include_archived=show_archived
            )
    elif show_archived:
        entries = await app_state.repository.get_archived(limit=100)
    else:
        entries = await app_state.repository.get_recent(limit=50)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = await app_state.repository.get_digest(today)
    counts = await app_state.repository.count_all()

    # KPI data for executive dashboard
    type_breakdown = await app_state.repository.get_type_breakdown()
    activity = await app_state.repository.get_activity_by_day(days=7)
    project_breakdown = await app_state.repository.get_project_breakdown()

    # Populate entity list for search filter dropdown
    all_entities = await app_state.entity_repo.get_all_entities()

    return templates.TemplateResponse(
        "dashboard.html",
        _shared_ctx(
            request,
            entries=entries,
            digest=digest,
            counts=counts,
            active_type=type,
            active_filter=filter,
            show_archived=show_archived,
            all_entities=all_entities,
            type_breakdown=type_breakdown,
            activity=activity,
            project_breakdown=project_breakdown,
        ),
    )


@router.post("/refresh", response_class=HTMLResponse)
async def refresh(request: Request) -> HTMLResponse:
    """Run catch-up and return updated dashboard."""
    log.info("manual_refresh_triggered")

    try:
        processed, failed = await app_state.pipeline.catch_up()
        log.info("refresh_complete", processed=processed, failed=failed)
    except Exception as e:
        log.error("refresh_failed", error=str(e), exc_info=True)

    entries = await app_state.repository.get_recent(limit=50)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = await app_state.repository.get_digest(today)
    counts = await app_state.repository.count_all()
    type_breakdown = await app_state.repository.get_type_breakdown()
    activity = await app_state.repository.get_activity_by_day(days=7)
    project_breakdown = await app_state.repository.get_project_breakdown()

    return templates.TemplateResponse(
        "dashboard.html",
        _shared_ctx(
            request,
            entries=entries,
            digest=digest,
            counts=counts,
            active_type="",
            show_archived=False,
            type_breakdown=type_breakdown,
            activity=activity,
            project_breakdown=project_breakdown,
        ),
    )


# ── Focus Panel & Badge Endpoints ────────────────────────────────

@router.get("/entry/{entry_id}/focus", response_class=HTMLResponse)
async def entry_focus_panel(request: Request, entry_id: UUID) -> HTMLResponse:
    """Render the focus panel partial for a selected entry."""
    entry = await app_state.repository.get_by_id(entry_id)
    if not entry:
        return HTMLResponse(
            '<div class="focus-empty"><p>Entry not found</p></div>'
        )
    return templates.TemplateResponse(
        "partials/focus_panel.html",
        _shared_ctx(request, focus_entry=entry),
    )


@router.get("/api/entry-count", response_class=HTMLResponse)
async def entry_count_badge(request: Request) -> HTMLResponse:
    """Return total entry count for the brand badge."""
    counts = await app_state.repository.count_all()
    return HTMLResponse(str(counts.get("total", 0)))


@router.get("/api/inbox-count", response_class=HTMLResponse)
async def inbox_count_badge(request: Request) -> HTMLResponse:
    """Return active entry count for the sidebar inbox badge."""
    counts = await app_state.repository.count_all()
    return HTMLResponse(str(counts.get("active", 0)))


# ── Search ───────────────────────────────────────────────────────

@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query(default=""),
    type: str = Query(default=""),
    entity: str = Query(default=""),
) -> HTMLResponse:
    """Search entries via multi-signal search (vector + keyword + entity + recency)."""
    if not q.strip():
        return HTMLResponse("")

    log.info("search_triggered", query=q, type_filter=type, entity_filter=entity)

    results = await app_state.search.search(
        query=q,
        limit=20,
        entity_filter=entity or None,
        type_filter=type or None,
        include_neighbors=True,
    )

    if not results:
        return templates.TemplateResponse(
            "partials/capture_prompt.html",
            _shared_ctx(request, query=q),
        )

    return templates.TemplateResponse(
        "partials/search_results.html",
        _shared_ctx(request, results=results, query=q),
    )


# ── Manual Capture ───────────────────────────────────────────────

@router.post("/capture", response_class=HTMLResponse)
async def capture(request: Request, text: str = Form(...)) -> HTMLResponse:
    """Manual capture from the dashboard — classify, embed, store.

    If the content is a near-duplicate, returns a duplicate notice instead
    of creating a new entry.
    """
    log.info("manual_capture_triggered", text_length=len(text))

    entry = await app_state.pipeline.capture_manual(text)

    # If duplicate was detected, return a notice linking to the existing entry
    if entry.novelty == NoveltyVerdict.DUPLICATE:
        return HTMLResponse(
            f'<div class="entry-card" style="border-left: 3px solid var(--gold); padding: 12px;">'
            f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">'
            f'<span class="novelty-badge novelty-duplicate">♻ Duplicate detected</span>'
            f'<span style="font-size: 0.85rem; color: var(--text-muted);">This thought is already captured.</span>'
            f'</div>'
            f'<a href="/entry/{entry.id}" class="entry-title" style="font-size: 0.88rem;">'
            f'{entry.title}</a>'
            f'<div class="entry-summary">{entry.summary}</div>'
            f'</div>'
        )

    return templates.TemplateResponse(
        "partials/entry_card.html",
        _shared_ctx(request, entry=entry),
    )


# ── Entry Detail ─────────────────────────────────────────────────

@router.get("/entry/{entry_id}", response_class=HTMLResponse)
async def entry_detail(request: Request, entry_id: str) -> HTMLResponse:
    """View full entry detail with raw content and metadata."""
    entry = await app_state.repository.get_by_id(UUID(entry_id))
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)

    return templates.TemplateResponse(
        "entry_detail.html",
        _shared_ctx(request, entry=entry),
    )


@router.get("/entry/{entry_id}/card", response_class=HTMLResponse)
async def entry_card(request: Request, entry_id: str) -> HTMLResponse:
    """Return a single entry card partial (used by edit cancel)."""
    entry = await app_state.repository.get_by_id(UUID(entry_id))
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/entry_card.html",
        _shared_ctx(request, entry=entry),
    )


# ── Archive / Unarchive ──────────────────────────────────────────

@router.post("/entry/{entry_id}/archive", response_class=HTMLResponse)
async def archive_entry(request: Request, entry_id: str) -> HTMLResponse:
    """Archive an entry (soft delete)."""
    entry = await app_state.repository.archive(UUID(entry_id))
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)
    # Return empty div to remove the card from view via htmx swap
    return HTMLResponse(f'<div id="entry-{entry_id}" class="entry-card archived-flash">Archived: {entry.title}</div>')


@router.post("/entry/{entry_id}/unarchive", response_class=HTMLResponse)
async def unarchive_entry(request: Request, entry_id: str) -> HTMLResponse:
    """Restore an archived entry."""
    entry = await app_state.repository.unarchive(UUID(entry_id))
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)
    return templates.TemplateResponse(
        "partials/entry_card.html",
        _shared_ctx(request, entry=entry),
    )


# ── Pin / Unpin ──────────────────────────────────────────────────

@router.post("/entry/{entry_id}/pin", response_class=HTMLResponse)
async def pin_entry(request: Request, entry_id: str) -> HTMLResponse:
    """Pin an entry for quick access."""
    entry = await app_state.repository.pin(UUID(entry_id))
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)
    return templates.TemplateResponse(
        "partials/entry_card.html",
        _shared_ctx(request, entry=entry),
    )


@router.post("/entry/{entry_id}/unpin", response_class=HTMLResponse)
async def unpin_entry(request: Request, entry_id: str) -> HTMLResponse:
    """Unpin an entry."""
    entry = await app_state.repository.unpin(UUID(entry_id))
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)
    return templates.TemplateResponse(
        "partials/entry_card.html",
        _shared_ctx(request, entry=entry),
    )


# ── Delete ───────────────────────────────────────────────────────

@router.delete("/entry/{entry_id}", response_class=HTMLResponse)
async def delete_entry(request: Request, entry_id: str) -> HTMLResponse:
    """Permanently delete an entry."""
    deleted = await app_state.repository.delete(UUID(entry_id))
    if not deleted:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)
    return HTMLResponse("")


# ── Reclassify ───────────────────────────────────────────────────

@router.post("/entry/{entry_id}/reclassify", response_class=HTMLResponse)
async def reclassify_entry(
    request: Request,
    entry_id: str,
    new_type: str = Form(...),
) -> HTMLResponse:
    """Change the type of an entry."""
    try:
        entry_type = EntryType(new_type)
    except ValueError:
        return HTMLResponse("<p>Invalid type</p>", status_code=400)

    entry = await app_state.repository.update(UUID(entry_id), entry_type=entry_type)
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/entry_card.html",
        _shared_ctx(request, entry=entry),
    )


# ── Edit Entry ───────────────────────────────────────────────────

@router.get("/entry/{entry_id}/edit", response_class=HTMLResponse)
async def edit_entry_form(request: Request, entry_id: str) -> HTMLResponse:
    """Return the inline edit form for an entry."""
    entry = await app_state.repository.get_by_id(UUID(entry_id))
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/entry_edit.html",
        _shared_ctx(request, entry=entry),
    )


@router.put("/entry/{entry_id}", response_class=HTMLResponse)
async def update_entry(
    request: Request,
    entry_id: str,
    title: str = Form(...),
    summary: str = Form(...),
    project: str = Form(default=""),
) -> HTMLResponse:
    """Save edits to an entry."""
    entry = await app_state.repository.update(
        UUID(entry_id),
        title=title,
        summary=summary,
        project=project or None,
    )
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/entry_card.html",
        _shared_ctx(request, entry=entry),
    )


# ── Reports ──────────────────────────────────────────────────────

@router.get("/reports/weekly", response_class=HTMLResponse)
async def weekly_report(
    request: Request,
    weeks_ago: int = Query(default=0, ge=0, le=12),
) -> HTMLResponse:
    """Weekly Digest Report: entries grouped by day and type for a given week."""
    import asyncio as _asyncio
    from collections import defaultdict

    # Calculate date range for the selected week
    today = datetime.now(timezone.utc).date()
    from datetime import timedelta

    week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks_ago)
    week_end = week_start + timedelta(days=6)

    entries, all_entities, activity_30d, type_breakdown, counts = await _asyncio.gather(
        app_state.repository.get_entries_in_date_range(
            week_start.isoformat(), week_end.isoformat()
        ),
        app_state.entity_repo.get_all_entities(),
        app_state.repository.get_activity_by_day(30),
        app_state.repository.get_type_breakdown(),
        app_state.repository.count_all(),
    )

    # Group entries by day
    by_day: dict[str, list] = defaultdict(list)
    for entry in entries:
        day_key = entry.created_at.strftime("%A, %b %d")
        by_day[day_key].append(entry)

    # Type counts for the week
    week_types: dict[str, int] = defaultdict(int)
    for entry in entries:
        week_types[entry.type.value] += 1

    # Extract entities mentioned this week
    week_entity_names: dict[str, int] = defaultdict(int)
    for entry in entries:
        for ent_name in entry.extracted_entities:
            week_entity_names[ent_name] += 1
    top_entities = sorted(week_entity_names.items(), key=lambda x: x[1], reverse=True)[:10]

    # Filter specific types for call-outs
    week_risks = [e for e in entries if e.type == EntryType.RISK]
    week_decisions = [e for e in entries if e.type == EntryType.DECISION]
    week_tasks = [e for e in entries if e.type == EntryType.TASK]

    return templates.TemplateResponse(
        "reports/weekly.html",
        _shared_ctx(
            request,
            entries=entries,
            by_day=dict(by_day),
            week_types=dict(week_types),
            top_entities=top_entities,
            week_risks=week_risks,
            week_decisions=week_decisions,
            week_tasks=week_tasks,
            activity_30d=activity_30d,
            type_breakdown=type_breakdown,
            counts=counts,
            week_start=week_start,
            week_end=week_end,
            weeks_ago=weeks_ago,
            total_entries=len(entries),
        ),
    )


@router.get("/reports/projects", response_class=HTMLResponse)
async def project_report(request: Request) -> HTMLResponse:
    """Project Breakdown Report: entries grouped by project with type distribution."""
    import asyncio as _asyncio

    project_breakdown, counts, all_entities = await _asyncio.gather(
        app_state.repository.get_project_breakdown(),
        app_state.repository.count_all(),
        app_state.entity_repo.get_all_entities(),
    )

    # Get entries with no project assigned
    all_active = await app_state.repository.get_recent(limit=500)
    unassigned = [e for e in all_active if not e.project]
    unassigned_types: dict[str, int] = {}
    from collections import defaultdict
    _ut: dict[str, int] = defaultdict(int)
    for e in unassigned:
        _ut[e.type.value] += 1
    unassigned_types = dict(_ut)

    return templates.TemplateResponse(
        "reports/projects.html",
        _shared_ctx(
            request,
            project_breakdown=project_breakdown,
            counts=counts,
            all_entities=all_entities,
            unassigned_count=len(unassigned),
            unassigned_types=unassigned_types,
        ),
    )


@router.get("/reports/project/{project_name}", response_class=HTMLResponse)
async def project_detail_report(
    request: Request,
    project_name: str,
) -> HTMLResponse:
    """Detail view for a single project: all entries grouped by type."""
    from collections import defaultdict
    from urllib.parse import unquote

    project_name = unquote(project_name)
    all_active = await app_state.repository.get_recent(limit=500)
    entries = [e for e in all_active if e.project == project_name]
    entries.sort(key=lambda e: e.created_at, reverse=True)

    by_type: dict[str, list] = defaultdict(list)
    for entry in entries:
        by_type[entry.type.value].append(entry)

    # PARA breakdown for this project
    para_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        para_counts[entry.para_category.value] += 1

    return templates.TemplateResponse(
        "reports/project_detail.html",
        _shared_ctx(
            request,
            project_name=project_name,
            entries=entries,
            by_type=dict(by_type),
            para_counts=dict(para_counts),
            total=len(entries),
        ),
    )


@router.get("/reports/trends", response_class=HTMLResponse)
async def trends_report(request: Request) -> HTMLResponse:
    """30-day trend analysis: activity patterns, type shifts, PARA distribution."""
    import asyncio as _asyncio

    activity_30d, type_breakdown, para_breakdown, counts = await _asyncio.gather(
        app_state.repository.get_activity_by_day(30),
        app_state.repository.get_type_breakdown(),
        app_state.repository.get_para_breakdown(),
        app_state.repository.count_all(),
    )

    # Get last 7d vs previous 7d for comparison
    all_activity = await app_state.repository.get_activity_by_day(14)
    recent_7 = sum(d["count"] for d in all_activity[-7:]) if len(all_activity) >= 7 else sum(d["count"] for d in all_activity)
    prev_7 = sum(d["count"] for d in all_activity[:-7]) if len(all_activity) > 7 else 0
    if prev_7 > 0:
        velocity_change = round(((recent_7 - prev_7) / prev_7) * 100, 1)
    else:
        velocity_change = 100.0 if recent_7 > 0 else 0.0

    all_entities = await app_state.entity_repo.get_all_entities()

    return templates.TemplateResponse(
        "reports/trends.html",
        _shared_ctx(
            request,
            activity_30d=activity_30d,
            type_breakdown=type_breakdown,
            para_breakdown=para_breakdown,
            counts=counts,
            recent_7=recent_7,
            prev_7=prev_7,
            velocity_change=velocity_change,
            all_entities=all_entities,
        ),
    )


# ── Insights ─────────────────────────────────────────────────────

@router.get("/insights", response_class=HTMLResponse)
async def insights(request: Request) -> HTMLResponse:
    """Reports page: classification health, unclassified queue, and type-specific backlogs."""
    # Run type-specific queries in parallel via gather
    import asyncio as _asyncio

    (
        unclassified,
        risks,
        tasks,
        decisions,
        strategy,
        ideas,
        counts,
        type_breakdown,
        activity,
    ) = await _asyncio.gather(
        app_state.repository.get_by_type(EntryType.UNCLASSIFIED),
        app_state.repository.get_by_type(EntryType.RISK),
        app_state.repository.get_by_type(EntryType.TASK),
        app_state.repository.get_by_type(EntryType.DECISION),
        app_state.repository.get_by_type(EntryType.STRATEGY),
        app_state.repository.get_by_type(EntryType.IDEA),
        app_state.repository.count_all(),
        app_state.repository.get_type_breakdown(),
        app_state.repository.get_activity_by_day(7),
    )

    total_all = sum(type_breakdown.values())
    unclassified_count = type_breakdown.get(EntryType.UNCLASSIFIED.value, 0)
    classified_count = total_all - unclassified_count
    classification_rate = classified_count / total_all if total_all else 0.0

    return templates.TemplateResponse(
        "insights.html",
        _shared_ctx(
            request,
            unclassified=unclassified,
            risks=risks,
            tasks=tasks,
            decisions=decisions,
            strategy=strategy,
            ideas=ideas,
            counts=counts,
            type_breakdown=type_breakdown,
            activity=activity,
            classification_rate=classification_rate,
            classified_count=classified_count,
            unclassified_count=unclassified_count,
            total_all=total_all,
        ),
    )


@router.get("/insights/unclassified-count", response_class=HTMLResponse)
async def insights_unclassified_count(request: Request) -> HTMLResponse:
    """Lightweight partial: returns an alert if there are unclassified entries."""
    entries = await app_state.repository.get_by_type(EntryType.UNCLASSIFIED)
    count = len(entries)
    if count == 0:
        return HTMLResponse("")
    return HTMLResponse(
        f'<a href="/insights" style="display:block; margin-top:0.5rem; padding:0.5rem 0.8rem; '
        f'background:rgba(239,83,80,0.1); border:1px solid var(--red); border-radius:6px; '
        f'color:var(--red); font-size:0.82rem; text-decoration:none;">'
        f'⚠️ {count} unclassified {"entry" if count == 1 else "entries"} need review → Insights</a>'
    )


# ── Eval Harness Results ─────────────────────────────────────────

def _enrich_eval_results(eval_results: list[dict]) -> tuple[list[dict], dict | None]:
    """Compute per-model scores and identify the recommended classifier."""
    for r in eval_results:
        if r.get("model_type") == "classification":
            acc = r.get("accuracy", 0)
            latency = r.get("avg_latency_ms", 99999)
            # 70% accuracy weight, 30% speed weight (10 s latency = zero speed points)
            speed_score = max(0.0, 1.0 - latency / 10000.0)
            r["score"] = round(acc * 0.7 + speed_score * 0.3, 4)
        else:
            r["score"] = None

    cls_results = [r for r in eval_results if r.get("model_type") == "classification"]
    recommendation: dict | None = None
    if cls_results:
        best = max(cls_results, key=lambda r: r.get("score", 0))
        if best.get("accuracy", 0) > 0:
            recommendation = {
                "model_name": best["model_name"],
                "model_short": best["model_name"].split("/")[-1],
                "accuracy": best["accuracy"],
                "avg_latency_ms": best["avg_latency_ms"],
                "score": best.get("score", 0),
            }

    return eval_results, recommendation


@router.get("/eval", response_class=HTMLResponse)
async def eval_page(request: Request) -> HTMLResponse:
    """Evaluation harness results page."""
    import json
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    results_path = project_root / "eval_results.json"
    history_path = project_root / "eval_history.json"

    eval_results = []
    if results_path.exists():
        try:
            eval_results = json.loads(results_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    eval_results, recommendation = _enrich_eval_results(eval_results)

    history: list[dict] = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    running = (project_root / ".eval_running").exists()

    return templates.TemplateResponse(
        "eval.html",
        _shared_ctx(
            request,
            eval_results=eval_results,
            eval_running=running,
            recommendation=recommendation,
            eval_history=history,
        ),
    )


@router.post("/eval/run", response_class=HTMLResponse)
async def run_eval(request: Request, mode: str = Form(default="all")) -> HTMLResponse:
    """Trigger the eval harness as a background subprocess."""
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    lock_file = project_root / ".eval_running"

    if lock_file.exists():
        return HTMLResponse(
            '<div id="eval-status" class="eval-status running"'
            ' hx-get="/eval/status" hx-trigger="every 2s" hx-swap="outerHTML">'
            'Evaluation already in progress...</div>'
        )

    lock_file.touch()

    args = [sys.executable, "-m", "scripts.eval_harness"]
    if mode == "classification":
        args.append("--classification-only")
    elif mode == "embedding":
        args.append("--embedding-only")

    # Pipe stdout/stderr to a log file so the UI can display it
    log_path = project_root / ".eval_log"
    log_handle = open(log_path, "w", encoding="utf-8")

    subprocess.Popen(
        args,
        cwd=str(project_root),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    return HTMLResponse(
        '<div id="eval-status" class="eval-status running"'
        ' hx-get="/eval/status" hx-trigger="every 2s" hx-swap="outerHTML">'
        'Evaluation starting...</div>'
    )


@router.get("/eval/status", response_class=HTMLResponse)
async def eval_status(request: Request) -> HTMLResponse:
    """Return live progress, log tail, and partial results while eval runs."""
    import html as html_mod
    import json
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    lock_file = project_root / ".eval_running"
    log_file = project_root / ".eval_log"

    if lock_file.exists():
        # Parse progress (first line may contain pid:NNNN)
        raw = ""
        try:
            raw = lock_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        lines = raw.splitlines()
        progress = lines[-1] if lines else "Starting..."

        # Read last 30 lines of the log file
        log_tail = ""
        try:
            if log_file.exists():
                all_lines = log_file.read_text(encoding="utf-8").splitlines()
                tail = all_lines[-30:] if len(all_lines) > 30 else all_lines
                log_tail = html_mod.escape("\n".join(tail))
        except OSError:
            pass

        # Load partial results for live model cards
        partial_html = ""
        results_path = project_root / "eval_results.json"
        try:
            if results_path.exists():
                partial = json.loads(results_path.read_text(encoding="utf-8"))
                if partial:
                    partial_html = _render_partial_results(partial)
        except (json.JSONDecodeError, OSError):
            pass

        return HTMLResponse(
            '<div id="eval-status" class="eval-status running"'
            ' hx-get="/eval/status" hx-trigger="every 2s" hx-swap="outerHTML">'
            f'<div style="display:flex; justify-content:space-between; align-items:center;">'
            f'<span><strong>Running:</strong> {html_mod.escape(progress)}</span>'
            f'<form hx-post="/eval/abort" hx-target="#eval-status" hx-swap="outerHTML" style="margin:0;">'
            f'<button type="submit" class="eval-run-btn" '
            f'style="background:var(--red); font-size:0.78rem; padding:0.3rem 0.7rem;">'
            f'Abort</button></form></div>'
            + (f'<pre class="eval-log-tail">{log_tail}</pre>' if log_tail else '')
            + (f'<div class="eval-partial-results">{partial_html}</div>' if partial_html else '')
            + '</div>'
        )
    else:
        return HTMLResponse(
            '<div id="eval-status" class="eval-status done"'
            ' hx-get="/eval" hx-trigger="load" hx-target="body" hx-swap="outerHTML"'
            ' hx-push-url="true">'
            'Evaluation complete! Loading results...</div>'
        )


def _render_partial_results(results: list[dict]) -> str:
    """Render compact partial-result cards for models that have finished so far."""
    import html as html_mod
    cards = []
    for r in results:
        name = html_mod.escape(r.get("model_name", "?"))
        acc = r.get("accuracy", 0)
        latency = r.get("avg_latency_ms", 0)
        errors = r.get("errors", 0)
        total = r.get("total_samples", 0)
        mtype = r.get("model_type", "")

        acc_pct = f"{acc * 100:.1f}%"
        color = "var(--green)" if acc >= 0.8 else "var(--gold)" if acc >= 0.5 else "var(--red)"
        label = "Accuracy" if mtype == "classification" else "Success"

        cards.append(
            f'<div style="display:inline-block; background:var(--bg); border:1px solid var(--border);'
            f' border-radius:6px; padding:0.5rem 0.8rem; margin:0.3rem 0.2rem; font-size:0.8rem;">'
            f'<strong>{name.split("/")[-1]}</strong><br>'
            f'{label}: <span style="color:{color}; font-weight:600;">{acc_pct}</span> &middot; '
            f'{latency:.0f}ms &middot; {errors}/{total} errors</div>'
        )
    return "".join(cards)


@router.post("/eval/abort", response_class=HTMLResponse)
async def abort_eval(request: Request) -> HTMLResponse:
    """Kill the running eval subprocess."""
    import signal
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    lock_file = project_root / ".eval_running"

    pid_file = project_root / ".eval_pid"
    killed = False
    try:
        if pid_file.exists():
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            try:
                os.kill(pid, signal.SIGTERM)
                killed = True
            except (ProcessLookupError, PermissionError):
                pass
            pid_file.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass
    lock_file.unlink(missing_ok=True)

    msg = "Evaluation aborted." if killed else "Evaluation stopped."
    return HTMLResponse(
        f'<div id="eval-status" class="eval-status" '
        f'style="background:rgba(239,68,68,0.1); border:1px solid var(--red); color:var(--red);">'
        f'{msg} <a href="/eval" style="color:var(--accent); margin-left:0.5rem;">Reload results</a>'
        f'</div>'
    )


# ── Phase 4: Entity Browser ─────────────────────────────────────

@router.get("/entities", response_class=HTMLResponse)
async def entities_page(
    request: Request,
    type: str = Query(default=""),
    q: str = Query(default=""),
) -> HTMLResponse:
    """Entity browser page — list all entities with type/search filters."""
    if q.strip():
        entities = await app_state.entity_repo.search_entities_by_name(q)
    else:
        entities = await app_state.entity_repo.get_all_entities()

    if type:
        try:
            et = EntityType(type)
            entities = [e for e in entities if e.entity_type == et]
        except ValueError:
            pass

    return templates.TemplateResponse(
        "entities.html",
        _shared_ctx(
            request,
            entities=entities,
            active_type=type,
            search_query=q,
        ),
    )


@router.get("/entity/{entity_id}", response_class=HTMLResponse)
async def entity_detail_page(request: Request, entity_id: str) -> HTMLResponse:
    """Entity detail page — description, aliases, linked entries, co-occurrence."""
    entity = await app_state.entity_repo.get_entity_by_id(UUID(entity_id))
    if not entity:
        return HTMLResponse("<p>Entity not found</p>", status_code=404)

    # Get linked entries
    entry_ids = await app_state.entity_repo.get_entries_for_entity(entity.id)
    entries = []
    for eid in entry_ids:
        entry = await app_state.repository.get_by_id(UUID(eid))
        if entry:
            entries.append(entry)
    entries.sort(key=lambda e: e.created_at, reverse=True)

    # Get co-occurring entities
    cooccurrence = []
    try:
        cooccurrence = await app_state.graph_service.get_entity_cooccurrence(
            entity.id
        )
    except Exception:
        log.debug("cooccurrence_fetch_failed", entity_id=entity_id)

    # Get entity summary
    summary = None
    try:
        summary = await app_state.summarization_service.get_entity_summary(
            entity.id
        )
    except Exception:
        log.debug("entity_summary_fetch_failed", entity_id=entity_id)

    return templates.TemplateResponse(
        "entity_detail_page.html",
        _shared_ctx(
            request,
            entity=entity,
            entries=entries,
            cooccurrence=cooccurrence,
            entity_summary=summary,
        ),
    )


@router.get("/api/entities", response_class=JSONResponse)
async def api_entities(
    type: str = Query(default=""),
    q: str = Query(default=""),
) -> JSONResponse:
    """JSON API: list entities with optional filters."""
    if q.strip():
        entities = await app_state.entity_repo.search_entities_by_name(q)
    else:
        entities = await app_state.entity_repo.get_all_entities()

    if type:
        try:
            et = EntityType(type)
            entities = [e for e in entities if e.entity_type == et]
        except ValueError:
            pass

    return JSONResponse([
        {
            "id": str(e.id),
            "name": e.name,
            "entity_type": e.entity_type.value,
            "aliases": e.aliases,
            "description": e.description,
            "entry_count": e.entry_count,
            "created_at": e.created_at.isoformat(),
            "updated_at": e.updated_at.isoformat(),
        }
        for e in entities
    ])


# ── Entity Edit / Delete ────────────────────────────────────────

@router.get("/entity/{entity_id}/edit", response_class=HTMLResponse)
async def edit_entity_form(request: Request, entity_id: str) -> HTMLResponse:
    """Return the inline edit form for an entity."""
    entity = await app_state.entity_repo.get_entity_by_id(UUID(entity_id))
    if not entity:
        return HTMLResponse("<p>Entity not found</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/entity_edit.html",
        _shared_ctx(request, entity=entity),
    )


@router.put("/entity/{entity_id}", response_class=HTMLResponse)
async def update_entity(
    request: Request,
    entity_id: str,
    name: str = Form(...),
    entity_type: str = Form(...),
    description: str = Form(default=""),
    aliases: str = Form(default=""),
) -> HTMLResponse:
    """Save edits to an entity."""
    try:
        et = EntityType(entity_type)
    except ValueError:
        return HTMLResponse("<p>Invalid entity type</p>", status_code=400)

    alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []

    entity = await app_state.entity_repo.update_entity(
        UUID(entity_id),
        name=name,
        entity_type=et,
        description=description,
        aliases=alias_list,
    )
    if not entity:
        return HTMLResponse("<p>Entity not found</p>", status_code=404)

    # Re-render the full entity detail page content
    entry_ids = await app_state.entity_repo.get_entries_for_entity(entity.id)
    entries = []
    for eid in entry_ids:
        entry = await app_state.repository.get_by_id(UUID(eid))
        if entry:
            entries.append(entry)
    entries.sort(key=lambda e: e.created_at, reverse=True)

    cooccurrence = []
    try:
        cooccurrence = await app_state.graph_service.get_entity_cooccurrence(entity.id)
    except Exception:
        pass

    summary = None
    try:
        summary = await app_state.summarization_service.get_entity_summary(entity.id)
    except Exception:
        pass

    return templates.TemplateResponse(
        "entity_detail_page.html",
        _shared_ctx(
            request,
            entity=entity,
            entries=entries,
            cooccurrence=cooccurrence,
            entity_summary=summary,
        ),
    )


@router.delete("/entity/{entity_id}", response_class=HTMLResponse)
async def delete_entity(request: Request, entity_id: str) -> HTMLResponse:
    """Permanently delete an entity and all its mentions."""
    deleted = await app_state.entity_repo.delete_entity(UUID(entity_id))
    if not deleted:
        return HTMLResponse("<p>Entity not found</p>", status_code=404)
    log.info("entity_deleted", entity_id=entity_id)
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = "/entities"
    return response


# ── Phase 4: Relationship Explorer ───────────────────────────────

@router.get("/entry/{entry_id}/relationships", response_class=HTMLResponse)
async def entry_relationships(request: Request, entry_id: str) -> HTMLResponse:
    """Show all relationships for an entry — outgoing and incoming links."""
    entry = await app_state.repository.get_by_id(UUID(entry_id))
    if not entry:
        return HTMLResponse("<p>Entry not found</p>", status_code=404)

    detail = await app_state.graph_service.get_entry_relationships_detail(
        UUID(entry_id)
    )

    # The graph service returns {"relationship": ..., "target": BrainEntry}
    # and {"relationship": ..., "source": BrainEntry}. Flatten for template.
    outgoing = []
    for rel in detail.get("outgoing", []):
        target = rel.get("target")
        if target:
            outgoing.append({
                "relationship_type": rel["relationship"].relationship_type,
                "confidence": rel["relationship"].confidence,
                "reason": rel["relationship"].reason,
                "target_entry": target,
            })

    incoming = []
    for rel in detail.get("incoming", []):
        source = rel.get("source")
        if source:
            incoming.append({
                "relationship_type": rel["relationship"].relationship_type,
                "confidence": rel["relationship"].confidence,
                "reason": rel["relationship"].reason,
                "source_entry": source,
            })

    return templates.TemplateResponse(
        "partials/relationships.html",
        _shared_ctx(
            request,
            entry=entry,
            outgoing=outgoing,
            incoming=incoming,
        ),
    )


# ── Phase 4: Knowledge Graph Data ────────────────────────────────

@router.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request) -> HTMLResponse:
    """Knowledge graph visualization page."""
    return templates.TemplateResponse(
        "graph.html",
        _shared_ctx(request),
    )


@router.get("/api/graph", response_class=JSONResponse)
async def api_graph_data(
    limit: int = Query(default=100),
) -> JSONResponse:
    """JSON API: graph data for visualization (nodes + edges)."""
    entities = await app_state.entity_repo.get_all_entities()
    entries = await app_state.repository.get_recent(limit=limit)

    nodes = []
    edges = []
    node_ids: set[str] = set()

    # Add entity nodes
    for entity in entities[:50]:
        nid = f"entity-{entity.id}"
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "label": entity.name,
            "type": "entity",
            "entity_type": entity.entity_type.value,
            "size": min(entity.entry_count * 3 + 5, 30),
        })

    # Add entry nodes + edges to entities
    for entry in entries:
        nid = f"entry-{entry.id}"
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "label": entry.title[:30],
            "type": "entry",
            "entry_type": entry.type.value,
            "para_category": entry.para_category.value,
            "size": 8,
        })

        # Entity mention edges
        for ent_name in (entry.extracted_entities or []):
            for entity in entities:
                if entity.name.lower() == ent_name.lower():
                    edges.append({
                        "source": nid,
                        "target": f"entity-{entity.id}",
                        "type": "mentions",
                    })
                    break

        # Relationship edges
        try:
            rels = await app_state.entity_repo.get_relationships_for_entry(
                entry.id
            )
            for rel in rels:
                target_nid = f"entry-{rel.target_entry_id}"
                source_nid = f"entry-{rel.source_entry_id}"
                if target_nid in node_ids or source_nid in node_ids:
                    edges.append({
                        "source": source_nid,
                        "target": target_nid,
                        "type": rel.relationship_type.value,
                    })
        except Exception:
            pass

    return JSONResponse({"nodes": nodes, "edges": edges})


# ── Phase 4: Suggestions API ─────────────────────────────────────

@router.get("/entry/{entry_id}/suggestions", response_class=HTMLResponse)
async def entry_suggestions(request: Request, entry_id: str) -> HTMLResponse:
    """Get smart suggestions for an entry (HTMX partial)."""
    entry = await app_state.repository.get_by_id(UUID(entry_id))
    if not entry:
        return HTMLResponse("")

    suggestions = await app_state.suggestion_engine.get_suggestions_for_entry(
        entry
    )

    if not suggestions:
        return HTMLResponse("")

    return templates.TemplateResponse(
        "partials/suggestions.html",
        _shared_ctx(request, suggestions=suggestions, entry=entry),
    )


# ── Phase 4: Summarization API ───────────────────────────────────

@router.post("/entity/{entity_id}/summarize", response_class=HTMLResponse)
async def summarize_entity(request: Request, entity_id: str) -> HTMLResponse:
    """Generate or refresh progressive summary for an entity."""
    entity = await app_state.entity_repo.get_entity_by_id(UUID(entity_id))
    if not entity:
        return HTMLResponse("<p>Entity not found</p>", status_code=404)

    summary = await app_state.summarization_service.summarize_entity(
        UUID(entity_id), force=False
    )

    if not summary:
        return HTMLResponse(
            '<p style="color:var(--text-muted);">Could not generate summary. '
            'Ensure an LLM provider is configured.</p>'
        )

    return HTMLResponse(
        f'<div class="entity-summary">'
        f'<h3>Summary</h3>'
        f'<p>{summary.summary_text}</p>'
        f'<div class="entry-meta">Based on {summary.entry_count_at_summary} entries '
        f'· Updated {_relative_time(summary.updated_at)}</div>'
        f'</div>'
    )


# ── Phase 3: Recall API ──────────────────────────────────────────

@router.get("/recall", response_class=HTMLResponse)
async def recall(
    request: Request,
    q: str = Query(default=""),
) -> HTMLResponse:
    """Contextual recall — citation-backed answers from stored knowledge."""
    if not q.strip():
        return HTMLResponse("")

    log.info("recall_triggered", query=q)

    result = await app_state.recall.recall_simple(question=q, limit=10)

    return templates.TemplateResponse(
        "partials/recall_results.html",
        _shared_ctx(
            request,
            recall_result=result,
            query=q,
        ),
    )


# ── Phase 3: Entity Timeline ─────────────────────────────────────

@router.get("/entity/{entity_id}/timeline", response_class=HTMLResponse)
async def entity_timeline(request: Request, entity_id: str) -> HTMLResponse:
    """Timeline view: chronological knowledge evolution for an entity."""
    entity = await app_state.entity_repo.get_entity_by_id(UUID(entity_id))
    if not entity:
        return HTMLResponse("<p>Entity not found</p>", status_code=404)

    results = await app_state.search.get_timeline(entity.name)
    entries = [r.entry for r in results]

    return templates.TemplateResponse(
        "partials/timeline.html",
        _shared_ctx(request, entity=entity, entries=entries),
    )


# ── Phase 4B: Slack Webhook ──────────────────────────────────────

@router.post("/slack/commands", response_class=JSONResponse)
async def slack_commands(
    request: Request,
    command: str = Form(default=""),
    text: str = Form(default=""),
) -> JSONResponse:
    """Handle incoming Slack slash commands (/brain)."""
    log.info("slack_command_received", command=command, text=text)
    result = await app_state.slack_commands.handle(text)
    return JSONResponse(result)


# ── Phase II: Strategic Positioning ──────────────────────────────

@router.get("/strategy", response_class=HTMLResponse)
async def strategy_dashboard(request: Request) -> HTMLResponse:
    """Render the strategic positioning dashboard."""
    summary = await app_state.strategy_repo.get_strategy_summary()
    initiatives = await app_state.strategy_repo.list_initiatives(status="active")
    stakeholders = await app_state.strategy_repo.list_stakeholders()
    assets = await app_state.strategy_repo.list_assets()
    influence_deltas = await app_state.strategy_repo.list_influence_deltas(limit=12)
    latest_sim = await app_state.strategy_repo.get_latest_simulation()
    influence_trend = await app_state.influence_tracker.get_trend()
    influence_insights = await app_state.influence_tracker.get_insights()

    return templates.TemplateResponse(
        "strategy/dashboard.html",
        _shared_ctx(
            request,
            summary=summary,
            initiatives=initiatives,
            stakeholders=stakeholders,
            assets=assets,
            influence_deltas=influence_deltas,
            latest_simulation=latest_sim,
            influence_trend=influence_trend,
            influence_insights=influence_insights,
            questions=app_state.evaluation_engine.get_questions(),
        ),
    )


# ── Initiatives ──────────────────────────────────────────────────

@router.get("/strategy/initiatives", response_class=HTMLResponse)
async def initiatives_page(
    request: Request,
    status: str = Query(default="active"),
    category: str = Query(default=""),
) -> HTMLResponse:
    """Render the initiatives browser."""
    cat_filter = InitiativeCategory(category) if category else None
    initiatives = await app_state.strategy_repo.list_initiatives(
        status=status, category=cat_filter,
    )
    breakdown = await app_state.evaluation_engine.get_category_breakdown()
    visibility_matrix = await app_state.evaluation_engine.get_visibility_matrix()

    # Gather link counts for all initiatives
    link_counts: dict[str, int] = {}
    for init in initiatives:
        link_counts[str(init.id)] = await app_state.strategy_repo.count_links_for_initiative(init.id)

    return templates.TemplateResponse(
        "strategy/initiatives.html",
        _shared_ctx(
            request,
            initiatives=initiatives,
            breakdown=breakdown,
            visibility_matrix=visibility_matrix,
            link_counts=link_counts,
            active_status=status,
            active_category=category,
            questions=app_state.evaluation_engine.get_questions(),
        ),
    )


@router.post("/strategy/initiatives", response_class=HTMLResponse)
async def create_initiative(
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    initiative_type: str = Form(default="scored"),
    authority: int = Form(default=0),
    asymmetric_info: int = Form(default=0),
    future_mobility: int = Form(default=0),
    reusable_leverage: int = Form(default=0),
    right_visibility: int = Form(default=0),
    visibility: str = Form(default="hidden"),
    risk_level: int = Form(default=0),
    notes: str = Form(default=""),
) -> HTMLResponse:
    """Create and evaluate a new initiative."""
    from src.models.strategy import InitiativeCreate

    create = InitiativeCreate(
        title=title,
        description=description,
        initiative_type=InitiativeType(initiative_type),
        authority=authority,
        asymmetric_info=asymmetric_info,
        future_mobility=future_mobility,
        reusable_leverage=reusable_leverage,
        right_visibility=right_visibility,
        visibility=VisibilityLevel(visibility),
        risk_level=risk_level,
        notes=notes,
    )
    initiative = await app_state.evaluation_engine.evaluate_initiative(create)
    link_count = await app_state.strategy_repo.count_links_for_initiative(initiative.id)
    log.info("initiative_created", id=str(initiative.id), category=initiative.category.value)

    # Return the initiative card partial for HTMX swap
    return templates.TemplateResponse(
        "strategy/partials/initiative_card.html",
        _shared_ctx(request, initiative=initiative, link_count=link_count),
    )


@router.get("/strategy/initiative/{initiative_id}", response_class=HTMLResponse)
async def initiative_detail(request: Request, initiative_id: str) -> HTMLResponse:
    """Render initiative detail page."""
    initiative = await app_state.strategy_repo.get_initiative(UUID(initiative_id))
    if initiative is None:
        return HTMLResponse("<p>Initiative not found</p>", status_code=404)

    links = await app_state.strategy_repo.get_links_for_initiative(UUID(initiative_id))

    return templates.TemplateResponse(
        "strategy/initiative_detail.html",
        _shared_ctx(request, initiative=initiative, links=links),
    )


@router.delete("/strategy/initiative/{initiative_id}", response_class=HTMLResponse)
async def delete_initiative(request: Request, initiative_id: str) -> HTMLResponse:
    """Delete an initiative."""
    await app_state.strategy_repo.delete_initiative(UUID(initiative_id))
    return HTMLResponse("")


@router.get("/strategy/initiative/{initiative_id}/edit", response_class=HTMLResponse)
async def edit_initiative_form(request: Request, initiative_id: str) -> HTMLResponse:
    """Return the inline edit form for an initiative."""
    initiative = await app_state.strategy_repo.get_initiative(UUID(initiative_id))
    if initiative is None:
        return HTMLResponse("<p>Initiative not found</p>", status_code=404)
    return templates.TemplateResponse(
        "strategy/partials/initiative_edit.html",
        _shared_ctx(request, initiative=initiative),
    )


@router.put("/strategy/initiative/{initiative_id}", response_class=HTMLResponse)
async def update_initiative(
    request: Request,
    initiative_id: str,
    title: str = Form(...),
    description: str = Form(default=""),
    initiative_type: str = Form(default="scored"),
    authority: int = Form(default=0),
    asymmetric_info: int = Form(default=0),
    future_mobility: int = Form(default=0),
    reusable_leverage: int = Form(default=0),
    right_visibility: int = Form(default=0),
    visibility: str = Form(default="hidden"),
    risk_level: int = Form(default=0),
    status: str = Form(default="active"),
    notes: str = Form(default=""),
) -> HTMLResponse:
    """Update an existing initiative."""
    from src.models.strategy import Initiative, InitiativeScores

    existing = await app_state.strategy_repo.get_initiative(UUID(initiative_id))
    if existing is None:
        return HTMLResponse("<p>Initiative not found</p>", status_code=404)

    scores = InitiativeScores(
        authority=authority,
        asymmetric_info=asymmetric_info,
        future_mobility=future_mobility,
        reusable_leverage=reusable_leverage,
        right_visibility=right_visibility,
    )
    existing.title = title
    existing.description = description
    existing.initiative_type = InitiativeType(initiative_type)
    existing.scores = scores
    existing.category = scores.category
    existing.visibility = VisibilityLevel(visibility)
    existing.risk_level = risk_level
    existing.status = status
    existing.notes = notes
    existing.updated_at = datetime.now(timezone.utc)

    await app_state.strategy_repo.save_initiative(existing)
    link_count = await app_state.strategy_repo.count_links_for_initiative(existing.id)

    return templates.TemplateResponse(
        "strategy/partials/initiative_card.html",
        _shared_ctx(request, initiative=existing, link_count=link_count),
    )


@router.get("/strategy/initiative/{initiative_id}/card", response_class=HTMLResponse)
async def initiative_card(request: Request, initiative_id: str) -> HTMLResponse:
    """Return the initiative card partial (used by edit cancel)."""
    initiative = await app_state.strategy_repo.get_initiative(UUID(initiative_id))
    if initiative is None:
        return HTMLResponse("")
    link_count = await app_state.strategy_repo.count_links_for_initiative(initiative.id)
    return templates.TemplateResponse(
        "strategy/partials/initiative_card.html",
        _shared_ctx(request, initiative=initiative, link_count=link_count),
    )


# ── Initiative Links ─────────────────────────────────────────────

@router.post("/strategy/initiative/{initiative_id}/links", response_class=HTMLResponse)
async def add_initiative_link(
    request: Request,
    initiative_id: str,
    linked_type: str = Form(...),
    linked_id: str = Form(...),
    link_note: str = Form(default=""),
) -> HTMLResponse:
    """Add a link from an initiative to an entry or entity."""
    from src.models.strategy import InitiativeLink

    # Resolve the title for the linked item
    linked_title = ""
    if linked_type == "entry":
        entry = await app_state.repository.get_by_id(UUID(linked_id))
        if entry:
            linked_title = entry.title
    elif linked_type == "entity":
        entity = await app_state.entity_repo.get_entity_by_id(UUID(linked_id))
        if entity:
            linked_title = entity.name

    link = InitiativeLink(
        initiative_id=UUID(initiative_id),
        linked_type=linked_type,
        linked_id=linked_id,
        linked_title=linked_title,
        link_note=link_note,
    )
    await app_state.strategy_repo.save_initiative_link(link)

    return templates.TemplateResponse(
        "strategy/partials/link_item.html",
        _shared_ctx(request, link=link, initiative_id=initiative_id),
    )


@router.delete("/strategy/link/{link_id}", response_class=HTMLResponse)
async def delete_initiative_link(request: Request, link_id: str) -> HTMLResponse:
    """Delete an initiative link."""
    await app_state.strategy_repo.delete_initiative_link(UUID(link_id))
    return HTMLResponse("")


@router.get("/api/strategy/search-linkable", response_class=JSONResponse)
async def search_linkable_items(
    q: str = Query(default=""),
) -> JSONResponse:
    """Search brain entries and entities for linking to an initiative."""
    if not q or len(q) < 2:
        return JSONResponse([])

    results: list[dict] = []

    # Search entries
    entries = await app_state.repository.search_keyword(q, limit=5)
    for entry, score in entries:
        results.append({
            "id": str(entry.id),
            "type": "entry",
            "title": entry.title,
            "subtitle": f"{TYPE_DISPLAY[entry.type]['emoji']} {entry.type.value}",
        })

    # Search entities
    entities = await app_state.entity_repo.search_entities_by_name(q)
    for entity in entities[:5]:
        results.append({
            "id": str(entity.id),
            "type": "entity",
            "title": entity.name,
            "subtitle": f"{ENTITY_DISPLAY[entity.entity_type]['emoji']} {entity.entity_type.value}",
        })

    return JSONResponse(results)


# ── Stakeholders ─────────────────────────────────────────────────

@router.get("/strategy/stakeholders", response_class=HTMLResponse)
async def stakeholders_page(request: Request) -> HTMLResponse:
    """Render the stakeholder landscape page."""
    stakeholders = await app_state.strategy_repo.list_stakeholders()
    return templates.TemplateResponse(
        "strategy/stakeholders.html",
        _shared_ctx(request, stakeholders=stakeholders),
    )


@router.post("/strategy/stakeholders", response_class=HTMLResponse)
async def create_stakeholder(
    request: Request,
    name: str = Form(...),
    role: str = Form(default=""),
    influence_level: int = Form(default=5),
    incentives: str = Form(default=""),
    alignment_score: int = Form(default=0),
    dependency_on_you: int = Form(default=0),
    trust_score: int = Form(default=5),
    notes: str = Form(default=""),
) -> HTMLResponse:
    """Create a new stakeholder."""
    from src.models.strategy import Stakeholder

    stakeholder = Stakeholder(
        name=name,
        role=role,
        influence_level=influence_level,
        incentives=incentives,
        alignment_score=alignment_score,
        dependency_on_you=dependency_on_you,
        trust_score=trust_score,
        notes=notes,
    )
    saved = await app_state.strategy_repo.save_stakeholder(stakeholder)

    return templates.TemplateResponse(
        "strategy/partials/stakeholder_card.html",
        _shared_ctx(request, stakeholder=saved),
    )


@router.delete("/strategy/stakeholder/{stakeholder_id}", response_class=HTMLResponse)
async def delete_stakeholder(request: Request, stakeholder_id: str) -> HTMLResponse:
    """Delete a stakeholder."""
    await app_state.strategy_repo.delete_stakeholder(UUID(stakeholder_id))
    return HTMLResponse("")


@router.get("/strategy/stakeholder/{stakeholder_id}/edit", response_class=HTMLResponse)
async def edit_stakeholder_form(request: Request, stakeholder_id: str) -> HTMLResponse:
    """Return the inline edit form for a stakeholder."""
    stakeholder = await app_state.strategy_repo.get_stakeholder(UUID(stakeholder_id))
    if stakeholder is None:
        return HTMLResponse("<p>Stakeholder not found</p>", status_code=404)
    return templates.TemplateResponse(
        "strategy/partials/stakeholder_edit.html",
        _shared_ctx(request, stakeholder=stakeholder),
    )


@router.put("/strategy/stakeholder/{stakeholder_id}", response_class=HTMLResponse)
async def update_stakeholder(
    request: Request,
    stakeholder_id: str,
    name: str = Form(...),
    role: str = Form(default=""),
    influence_level: int = Form(default=5),
    incentives: str = Form(default=""),
    alignment_score: int = Form(default=0),
    dependency_on_you: int = Form(default=0),
    trust_score: int = Form(default=5),
    notes: str = Form(default=""),
) -> HTMLResponse:
    """Update an existing stakeholder."""
    from src.models.strategy import Stakeholder

    existing = await app_state.strategy_repo.get_stakeholder(UUID(stakeholder_id))
    if existing is None:
        return HTMLResponse("<p>Stakeholder not found</p>", status_code=404)

    existing.name = name
    existing.role = role
    existing.influence_level = influence_level
    existing.incentives = incentives
    existing.alignment_score = alignment_score
    existing.dependency_on_you = dependency_on_you
    existing.trust_score = trust_score
    existing.notes = notes
    existing.updated_at = datetime.now(timezone.utc)

    await app_state.strategy_repo.save_stakeholder(existing)

    return templates.TemplateResponse(
        "strategy/partials/stakeholder_card.html",
        _shared_ctx(request, stakeholder=existing),
    )


@router.get("/strategy/stakeholder/{stakeholder_id}/card", response_class=HTMLResponse)
async def stakeholder_card(request: Request, stakeholder_id: str) -> HTMLResponse:
    """Return the stakeholder card partial (used by edit cancel)."""
    stakeholder = await app_state.strategy_repo.get_stakeholder(UUID(stakeholder_id))
    if stakeholder is None:
        return HTMLResponse("")
    return templates.TemplateResponse(
        "strategy/partials/stakeholder_card.html",
        _shared_ctx(request, stakeholder=stakeholder),
    )


# ── Strategic Assets ─────────────────────────────────────────────

@router.get("/strategy/assets", response_class=HTMLResponse)
async def assets_page(
    request: Request,
    asset_type: str = Query(default=""),
) -> HTMLResponse:
    """Render the strategic assets page."""
    type_filter = AssetCategory(asset_type) if asset_type else None
    assets = await app_state.strategy_repo.list_assets(asset_type=type_filter)
    return templates.TemplateResponse(
        "strategy/assets.html",
        _shared_ctx(request, assets=assets, active_type=asset_type),
    )


@router.post("/strategy/assets", response_class=HTMLResponse)
async def create_asset(
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    asset_type: str = Form(default="reputation"),
    visibility: str = Form(default="hidden"),
    reusability_score: int = Form(default=0),
    signaling_strength: int = Form(default=0),
    market_relevance: int = Form(default=0),
    compounding_potential: int = Form(default=0),
    portability_score: int = Form(default=0),
    market_demand: int = Form(default=0),
    monetization_potential: int = Form(default=0),
    time_to_deploy: int = Form(default=0),
    notes: str = Form(default=""),
) -> HTMLResponse:
    """Create a new strategic asset."""
    from src.models.strategy import StrategicAsset

    asset = StrategicAsset(
        title=title,
        description=description,
        asset_type=AssetCategory(asset_type),
        visibility=VisibilityLevel(visibility),
        reusability_score=reusability_score,
        signaling_strength=signaling_strength,
        market_relevance=market_relevance,
        compounding_potential=compounding_potential,
        portability_score=portability_score,
        market_demand=market_demand,
        monetization_potential=monetization_potential,
        time_to_deploy=time_to_deploy,
        notes=notes,
    )
    saved = await app_state.strategy_repo.save_asset(asset)

    return templates.TemplateResponse(
        "strategy/partials/asset_card.html",
        _shared_ctx(request, asset=saved),
    )


@router.delete("/strategy/asset/{asset_id}", response_class=HTMLResponse)
async def delete_asset(request: Request, asset_id: str) -> HTMLResponse:
    """Delete a strategic asset."""
    await app_state.strategy_repo.delete_asset(UUID(asset_id))
    return HTMLResponse("")


@router.get("/strategy/asset/{asset_id}/edit", response_class=HTMLResponse)
async def edit_asset_form(request: Request, asset_id: str) -> HTMLResponse:
    """Return the inline edit form for a strategic asset."""
    asset = await app_state.strategy_repo.get_asset(UUID(asset_id))
    if asset is None:
        return HTMLResponse("<p>Asset not found</p>", status_code=404)
    return templates.TemplateResponse(
        "strategy/partials/asset_edit.html",
        _shared_ctx(request, asset=asset),
    )


@router.put("/strategy/asset/{asset_id}", response_class=HTMLResponse)
async def update_asset(
    request: Request,
    asset_id: str,
    title: str = Form(...),
    description: str = Form(default=""),
    asset_type: str = Form(default="reputation"),
    visibility: str = Form(default="hidden"),
    reusability_score: int = Form(default=0),
    signaling_strength: int = Form(default=0),
    market_relevance: int = Form(default=0),
    compounding_potential: int = Form(default=0),
    portability_score: int = Form(default=0),
    market_demand: int = Form(default=0),
    monetization_potential: int = Form(default=0),
    time_to_deploy: int = Form(default=0),
    notes: str = Form(default=""),
) -> HTMLResponse:
    """Update an existing strategic asset."""
    existing = await app_state.strategy_repo.get_asset(UUID(asset_id))
    if existing is None:
        return HTMLResponse("<p>Asset not found</p>", status_code=404)

    existing.title = title
    existing.description = description
    existing.asset_type = AssetCategory(asset_type)
    existing.visibility = VisibilityLevel(visibility)
    existing.reusability_score = reusability_score
    existing.signaling_strength = signaling_strength
    existing.market_relevance = market_relevance
    existing.compounding_potential = compounding_potential
    existing.portability_score = portability_score
    existing.market_demand = market_demand
    existing.monetization_potential = monetization_potential
    existing.time_to_deploy = time_to_deploy
    existing.notes = notes
    existing.updated_at = datetime.now(timezone.utc)

    await app_state.strategy_repo.save_asset(existing)

    return templates.TemplateResponse(
        "strategy/partials/asset_card.html",
        _shared_ctx(request, asset=existing),
    )


@router.get("/strategy/asset/{asset_id}/card", response_class=HTMLResponse)
async def asset_card(request: Request, asset_id: str) -> HTMLResponse:
    """Return the asset card partial (used by edit cancel)."""
    asset = await app_state.strategy_repo.get_asset(UUID(asset_id))
    if asset is None:
        return HTMLResponse("")
    return templates.TemplateResponse(
        "strategy/partials/asset_card.html",
        _shared_ctx(request, asset=asset),
    )


# ── Influence Tracking ───────────────────────────────────────────

@router.post("/strategy/influence", response_class=HTMLResponse)
async def log_influence(
    request: Request,
    week_start: str = Form(...),
    stakeholder_id: str = Form(default=""),
    advice_sought: bool = Form(default=False),
    decision_changed: bool = Form(default=False),
    framing_adopted: bool = Form(default=False),
    consultation_count: int = Form(default=0),
    notes: str = Form(default=""),
) -> HTMLResponse:
    """Log weekly influence interactions."""
    from src.models.strategy import InfluenceDeltaCreate

    create = InfluenceDeltaCreate(
        week_start=week_start,
        stakeholder_id=stakeholder_id if stakeholder_id else None,
        advice_sought=advice_sought,
        decision_changed=decision_changed,
        framing_adopted=framing_adopted,
        consultation_count=consultation_count,
        notes=notes,
    )
    delta = await app_state.influence_tracker.log_week(create)

    return templates.TemplateResponse(
        "strategy/partials/influence_row.html",
        _shared_ctx(request, delta=delta),
    )


# ── Weekly Simulation ────────────────────────────────────────────

@router.post("/strategy/simulate", response_class=HTMLResponse)
async def run_simulation(
    request: Request,
    week_start: str = Form(default=""),
) -> HTMLResponse:
    """Run the weekly strategic simulation protocol."""
    if not week_start:
        # Default to current week's Monday
        from datetime import timedelta
        today = datetime.now(timezone.utc).date()
        monday = today - timedelta(days=today.weekday())
        week_start = monday.isoformat()

    simulation = await app_state.strategic_simulator.run_simulation(week_start)

    return templates.TemplateResponse(
        "strategy/partials/simulation_result.html",
        _shared_ctx(request, latest_simulation=simulation),
    )


# ── Strategy JSON APIs ──────────────────────────────────────────

@router.get("/api/strategy/summary", response_class=JSONResponse)
async def api_strategy_summary() -> JSONResponse:
    """JSON API for strategy summary data."""
    summary = await app_state.strategy_repo.get_strategy_summary()
    return JSONResponse(summary)


@router.get("/api/strategy/visibility-matrix", response_class=JSONResponse)
async def api_visibility_matrix() -> JSONResponse:
    """JSON API for initiative visibility distribution."""
    matrix = await app_state.evaluation_engine.get_visibility_matrix()
    return JSONResponse(matrix)


@router.get("/api/strategy/influence-trend", response_class=JSONResponse)
async def api_influence_trend() -> JSONResponse:
    """JSON API for influence trend data."""
    trend = await app_state.influence_tracker.get_trend()
    return JSONResponse(trend)


@router.get("/api/strategy/influence-insights", response_class=JSONResponse)
async def api_influence_insights() -> JSONResponse:
    """JSON API for deep influence insights."""
    insights = await app_state.influence_tracker.get_insights()
    return JSONResponse(insights)


@router.get("/strategy/influence-insights", response_class=HTMLResponse)
async def influence_insights_panel(request: Request) -> HTMLResponse:
    """Return the influence insights panel partial (lazy-loaded via HTMX)."""
    insights = await app_state.influence_tracker.get_insights()
    return templates.TemplateResponse(
        "strategy/partials/influence_insights.html",
        _shared_ctx(request, insights=insights),
    )


@router.post("/strategy/load-examples", response_class=HTMLResponse)
async def load_example_dataset(
    request: Request,
    dataset: str = Form(default="personal"),
) -> HTMLResponse:
    """Load an example dataset into the strategy engine, replacing existing data."""
    from src.core.example_datasets import load_example_dataset as _load, DATASETS

    if dataset not in DATASETS:
        dataset = "personal"

    counts = await _load(app_state.strategy_repo, dataset, clear_existing=True)
    label = DATASETS[dataset]["label"]

    return HTMLResponse(
        f'<div style="padding:0.75rem;background:rgba(16,185,129,0.15);border-radius:6px;font-size:0.85rem;">'
        f'✅ Loaded <strong>{label}</strong> dataset: '
        f'{counts["stakeholders"]} stakeholders, {counts["initiatives"]} initiatives, '
        f'{counts["assets"]} assets, {counts["influence_deltas"]} influence records. '
        f'<a href="/strategy" style="color:var(--color-emerald);font-weight:600;">Refresh to see results →</a>'
        f'</div>'
    )


# ── Admin: Reset Everything ──────────────────────────────────────

@router.post("/admin/reset", response_class=HTMLResponse)
async def nuke_all(request: Request) -> HTMLResponse:
    """Delete ALL data from every table — complete factory reset.

    Also clears the Qdrant vector collection.
    """
    counts = await app_state.database.nuke_all()

    # Clear Qdrant vectors
    try:
        vs = app_state.pipeline.vector_store
        for coll in [vs.collection_name, vs.entity_collection_name]:
            try:
                vs.client.delete_collection(coll)
            except Exception:
                pass
        await vs.init_collection()
        log.info("qdrant_collections_reset")
    except Exception as e:
        log.warning("qdrant_reset_failed", error=str(e))

    total = sum(counts.values())
    log.info("factory_reset_complete", total_deleted=total, counts=counts)

    return HTMLResponse(
        f'<div style="padding:0.75rem;background:rgba(239,68,68,0.15);border-radius:6px;font-size:0.85rem;">'
        f'🗑️ Factory reset complete — <strong>{total}</strong> records deleted across '
        f'{len([t for t, c in counts.items() if c > 0])} tables. '
        f'<a href="/" style="color:var(--color-red);font-weight:600;">Go to Dashboard →</a>'
        f'</div>'
    )
