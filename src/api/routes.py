"""API routes for Second Brain dashboard."""

from datetime import datetime, timezone
import os
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


# ── Insights & Reports ───────────────────────────────────────────

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
