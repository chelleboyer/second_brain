"""API routes for Second Brain dashboard."""

from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from src.api.deps import app_state, templates
from src.models.enums import TYPE_DISPLAY, CLASSIFIABLE_TYPES, EntryType

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
        "relative_time": _relative_time,
        "entry_types": list(EntryType),
        "classifiable_types": CLASSIFIABLE_TYPES,
        **extra,
    }


# ── Dashboard ────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    type: str = Query(default=""),
    show_archived: bool = Query(default=False),
) -> HTMLResponse:
    """Render the main dashboard with capture feed, filters, and digest."""
    if type:
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

    return templates.TemplateResponse(
        "dashboard.html",
        _shared_ctx(
            request,
            entries=entries,
            digest=digest,
            counts=counts,
            active_type=type,
            show_archived=show_archived,
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

    return templates.TemplateResponse(
        "dashboard.html",
        _shared_ctx(
            request,
            entries=entries,
            digest=digest,
            counts=counts,
            active_type="",
            show_archived=False,
        ),
    )


# ── Search ───────────────────────────────────────────────────────

@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query(default=""),
    type: str = Query(default=""),
) -> HTMLResponse:
    """Search entries via dual search (vector + keyword)."""
    if not q.strip():
        return HTMLResponse("")

    log.info("search_triggered", query=q, type_filter=type)

    results = await app_state.search.search(query=q, limit=20)

    if type:
        try:
            entry_type = EntryType(type)
            results = [r for r in results if r.entry.type == entry_type]
        except ValueError:
            pass

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
    """Manual capture from the dashboard — classify, embed, store."""
    log.info("manual_capture_triggered", text_length=len(text))

    entry = await app_state.pipeline.capture_manual(text)

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


# ── Eval Harness Results ─────────────────────────────────────────

@router.get("/eval", response_class=HTMLResponse)
async def eval_page(request: Request) -> HTMLResponse:
    """Evaluation harness results page."""
    import json
    from pathlib import Path

    results_path = Path(__file__).resolve().parent.parent.parent / "eval_results.json"
    eval_results = []
    if results_path.exists():
        try:
            eval_results = json.loads(results_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    running = (Path(__file__).resolve().parent.parent.parent / ".eval_running").exists()

    return templates.TemplateResponse(
        "eval.html",
        _shared_ctx(request, eval_results=eval_results, eval_running=running),
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
            ' hx-get="/eval/status" hx-trigger="every 3s" hx-swap="outerHTML">'
            '⏳ Evaluation already in progress...</div>'
        )

    lock_file.touch()

    args = [sys.executable, "-m", "scripts.eval_harness"]
    if mode == "classification":
        args.append("--classification-only")
    elif mode == "embedding":
        args.append("--embedding-only")

    subprocess.Popen(
        args,
        cwd=str(project_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return HTMLResponse(
        '<div id="eval-status" class="eval-status running"'
        ' hx-get="/eval/status" hx-trigger="every 3s" hx-swap="outerHTML">'
        '⏳ Evaluation running... this may take a few minutes.</div>'
    )


@router.get("/eval/status", response_class=HTMLResponse)
async def eval_status(request: Request) -> HTMLResponse:
    """Check if eval harness is still running."""
    from pathlib import Path

    lock_file = Path(__file__).resolve().parent.parent.parent / ".eval_running"
    if lock_file.exists():
        return HTMLResponse(
            '<div id="eval-status" class="eval-status running"'
            ' hx-get="/eval/status" hx-trigger="every 3s" hx-swap="outerHTML">'
            '⏳ Evaluation running... this may take a few minutes.</div>'
        )
    else:
        return HTMLResponse(
            '<div id="eval-status" class="eval-status done"'
            ' hx-get="/eval" hx-trigger="load" hx-target="body" hx-swap="outerHTML"'
            ' hx-push-url="true">'
            '✅ Evaluation complete! Loading results...</div>'
        )
