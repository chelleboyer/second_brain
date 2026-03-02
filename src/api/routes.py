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
    CLASSIFIABLE_TYPES,
    EntryType,
    EntityType,
    NoveltyVerdict,
    PARACategory,
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
        "relative_time": _relative_time,
        "entry_types": list(EntryType),
        "entity_types": list(EntityType),
        "para_categories": list(PARACategory),
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
            show_archived=show_archived,
            all_entities=all_entities,
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
