"""Evaluation harness for testing classification and embedding models.

Usage:
    python -m scripts.eval_harness [--classification-only] [--embedding-only]

Tests models against a labeled dataset and outputs results to eval_results.json.
View results at http://localhost:8000/eval
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import structlog

log = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "eval_results.json"
PROGRESS_FILE = PROJECT_ROOT / ".eval_running"
PID_FILE = PROJECT_ROOT / ".eval_pid"
LOG_FILE = PROJECT_ROOT / ".eval_log"
HISTORY_PATH = PROJECT_ROOT / "eval_history.json"
MAX_HISTORY_RUNS = 10

# Ring-buffer log: keep last N lines in file so the UI can poll it
_LOG_MAX_LINES = 200
_log_lines: list[str] = []


def _emit(msg: str) -> None:
    """Print to console (ASCII-safe) AND append to the eval log file."""
    # Console print - safe for cp1252
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode())

    _log_lines.append(msg)
    # Trim to last N lines
    if len(_log_lines) > _LOG_MAX_LINES:
        del _log_lines[: len(_log_lines) - _LOG_MAX_LINES]
    try:
        LOG_FILE.write_text("\n".join(_log_lines), encoding="utf-8")
    except OSError:
        pass


def _update_progress(msg: str) -> None:
    """Write current progress to the lock file for UI polling."""
    try:
        PROGRESS_FILE.write_text(msg, encoding="utf-8")
    except OSError:
        pass


def _save_incremental(results: list[dict]) -> None:
    """Save results after each model so the UI can show partial data."""
    try:
        RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    except OSError:
        pass


def _save_history(results: list[dict]) -> None:
    """Append a compact run record to eval_history.json (keeps last MAX_HISTORY_RUNS runs)."""
    try:
        history: list[dict] = []
        if HISTORY_PATH.exists():
            try:
                history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                history = []

        from datetime import datetime, timezone

        run = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "models": {
                r["model_name"]: {
                    "model_type": r["model_type"],
                    "accuracy": r["accuracy"],
                    "avg_latency_ms": r["avg_latency_ms"],
                    "p50_latency_ms": r.get("p50_latency_ms", 0),
                    "errors": r["errors"],
                    "total_samples": r["total_samples"],
                }
                for r in results
            },
        }
        history.append(run)
        if len(history) > MAX_HISTORY_RUNS:
            history = history[-MAX_HISTORY_RUNS:]
        HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except OSError:
        pass


# ── Labeled test dataset ─────────────────────────────────────────
# Each sample: (text, expected_type, description)
# These represent the kinds of messages the system should classify correctly.

EVAL_SAMPLES = [
    {
        "text": "We should build a mobile app for the project tracker",
        "expected_type": "idea",
        "description": "Feature suggestion",
    },
    {
        "text": "I think we could use Redis for caching the API responses",
        "expected_type": "idea",
        "description": "Technical idea",
    },
    {
        "text": "Update the deployment docs before Friday",
        "expected_type": "task",
        "description": "Clear action item with deadline",
    },
    {
        "text": "Need to fix the login bug in production ASAP",
        "expected_type": "task",
        "description": "Urgent bug fix task",
    },
    {
        "text": "We decided to go with PostgreSQL instead of MySQL for the new service",
        "expected_type": "decision",
        "description": "Technology decision",
    },
    {
        "text": "After discussion, the team agreed to use two-week sprints going forward",
        "expected_type": "decision",
        "description": "Process decision",
    },
    {
        "text": "If we don't upgrade the database soon, we might hit scaling issues in Q3",
        "expected_type": "risk",
        "description": "Technical risk with timeline",
    },
    {
        "text": "The vendor contract expires next month and we have no backup plan",
        "expected_type": "risk",
        "description": "Business risk",
    },
    {
        "text": "The API gateway uses a fan-out pattern to distribute requests to microservices",
        "expected_type": "arch_note",
        "description": "Architecture pattern description",
    },
    {
        "text": "We use event sourcing for the order management system with CQRS for reads",
        "expected_type": "arch_note",
        "description": "Architecture approach",
    },
    {
        "text": "Our go-to-market strategy focuses on enterprise customers first, then SMBs in Q4",
        "expected_type": "strategy",
        "description": "Business strategy",
    },
    {
        "text": "We should pivot to a platform model to increase recurring revenue",
        "expected_type": "strategy",
        "description": "Strategic pivot",
    },
    {
        "text": "The meeting is at 3pm today in the main conference room",
        "expected_type": "note",
        "description": "General informational message",
    },
    {
        "text": "Here's the link to the design doc: https://docs.example.com/design",
        "expected_type": "note",
        "description": "Link sharing",
    },
]

# ── Models to evaluate ───────────────────────────────────────────

CLASSIFICATION_MODELS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "meta-llama/Meta-Llama-3-8B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
]

EMBEDDING_MODELS = [
    "BAAI/bge-small-en-v1.5",
    "BAAI/bge-base-en-v1.5",
    "BAAI/bge-large-en-v1.5",
]

CHAT_URL = "https://router.huggingface.co/v1/chat/completions"
EMBED_URL = "https://router.huggingface.co/hf-inference/models"

CLASSIFICATION_PROMPT = """Analyze the following message and return a JSON object with exactly three fields:
1. "type": one of [idea, task, decision, risk, arch_note, strategy, note]
2. "title": a concise title (max 10 words)
3. "summary": a 1-2 sentence summary

Respond with ONLY valid JSON, no other text.

Message: {text}"""


@dataclass
class ClassificationResult:
    """Result of a single classification test."""

    sample_text: str
    expected_type: str
    predicted_type: str
    correct: bool
    latency_ms: float
    raw_response: str
    error: str | None = None
    description: str = ""


@dataclass
class EmbeddingResult:
    """Result of a single embedding test."""

    sample_text: str
    dimensions: int
    latency_ms: float
    error: str | None = None


@dataclass
class ModelEvaluation:
    """Full evaluation results for one model."""

    model_name: str
    model_type: str  # "classification" or "embedding"
    results: list = field(default_factory=list)
    accuracy: float = 0.0
    avg_latency_ms: float = 0.0
    total_samples: int = 0
    errors: int = 0
    timestamp: str = ""

    def to_dict(self) -> dict:
        from collections import defaultdict

        # Latency percentiles (exclude errored samples)
        good_latencies = sorted(r.latency_ms for r in self.results if not r.error)

        def _pct(data: list, p: float) -> float:
            if not data:
                return 0.0
            return data[min(int(len(data) * p), len(data) - 1)]

        p50 = _pct(good_latencies, 0.50)
        p95 = _pct(good_latencies, 0.95)

        # Per-type accuracy breakdown (classification only)
        per_type_accuracy: dict = {}
        if self.model_type == "classification":
            type_correct: dict = defaultdict(int)
            type_total: dict = defaultdict(int)
            for r in self.results:
                expected = getattr(r, "expected_type", None)
                if expected:
                    type_total[expected] += 1
                    if getattr(r, "correct", False):
                        type_correct[expected] += 1
            per_type_accuracy = {
                t: {
                    "correct": type_correct[t],
                    "total": type_total[t],
                    "pct": round(type_correct[t] / type_total[t], 3) if type_total[t] else 0,
                }
                for t in type_total
            }

        return {
            "model_name": self.model_name,
            "model_type": self.model_type,
            "accuracy": round(self.accuracy, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "p50_latency_ms": round(p50, 1),
            "p95_latency_ms": round(p95, 1),
            "total_samples": self.total_samples,
            "errors": self.errors,
            "timestamp": self.timestamp,
            "per_type_accuracy": per_type_accuracy,
            "results": [
                {
                    "text": r.sample_text[:80],
                    "description": getattr(r, "description", ""),
                    "expected": r.expected_type if hasattr(r, "expected_type") else None,
                    "predicted": r.predicted_type if hasattr(r, "predicted_type") else None,
                    "correct": r.correct if hasattr(r, "correct") else None,
                    "latency_ms": round(r.latency_ms, 1),
                    "dimensions": getattr(r, "dimensions", None),
                    "error": r.error,
                }
                for r in self.results
            ],
        }


import re


def _extract_type_from_response(response_text: str) -> str | None:
    """Extract the type field from an LLM response."""
    # Try JSON parse
    try:
        data = json.loads(response_text)
        if isinstance(data, dict) and "type" in data:
            return data["type"].strip().lower()
    except json.JSONDecodeError:
        pass

    # Try to find JSON in text
    json_match = re.search(r"\{[^{}]+\}", response_text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if "type" in data:
                return data["type"].strip().lower()
        except json.JSONDecodeError:
            pass

    # Regex fallback
    valid_types = ["idea", "task", "decision", "risk", "arch_note", "strategy", "note"]
    for t in valid_types:
        if t in response_text.lower():
            return t

    return None


async def evaluate_classification_model(
    model: str, api_token: str
) -> ModelEvaluation:
    """Run all eval samples through a classification model."""
    from datetime import datetime, timezone

    _emit(f"\n{'='*60}")
    _emit(f"Evaluating classification: {model}")
    _emit(f"{'='*60}")

    evaluation = ModelEvaluation(
        model_name=model,
        model_type="classification",
        total_samples=len(EVAL_SAMPLES),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    headers = {"Authorization": f"Bearer {api_token}"}
    correct = 0

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i, sample in enumerate(EVAL_SAMPLES):
            _update_progress(f"Classification: {model.split('/')[-1]} - sample {i+1}/{len(EVAL_SAMPLES)}")
            prompt = CLASSIFICATION_PROMPT.format(text=sample["text"])
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
            }

            start = time.perf_counter()
            try:
                response = await client.post(
                    CHAT_URL, json=payload, headers=headers
                )
                elapsed_ms = (time.perf_counter() - start) * 1000

                if response.status_code != 200:
                    result = ClassificationResult(
                        sample_text=sample["text"],
                        expected_type=sample["expected_type"],
                        predicted_type="",
                        correct=False,
                        latency_ms=elapsed_ms,
                        raw_response=response.text[:200],
                        error=f"HTTP {response.status_code}",
                        description=sample.get("description", ""),
                    )
                    evaluation.results.append(result)
                    evaluation.errors += 1
                    _emit(f"  [{i+1}/{len(EVAL_SAMPLES)}] ERROR: HTTP {response.status_code}")
                    continue

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                predicted = _extract_type_from_response(content)

                is_correct = predicted == sample["expected_type"]
                if is_correct:
                    correct += 1

                result = ClassificationResult(
                    sample_text=sample["text"],
                    expected_type=sample["expected_type"],
                    predicted_type=predicted or "PARSE_FAIL",
                    correct=is_correct,
                    latency_ms=elapsed_ms,
                    raw_response=content[:200],
                    description=sample.get("description", ""),
                )
                evaluation.results.append(result)

                status = "OK" if is_correct else "FAIL"
                _emit(
                    f"  [{i+1}/{len(EVAL_SAMPLES)}] {status:4s} "
                    f"expected={sample['expected_type']:<12} "
                    f"got={predicted or 'FAIL':<12} "
                    f"({elapsed_ms:.0f}ms) "
                    f"- {sample['description']}"
                )

            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                result = ClassificationResult(
                    sample_text=sample["text"],
                    expected_type=sample["expected_type"],
                    predicted_type="",
                    correct=False,
                    latency_ms=elapsed_ms,
                    raw_response="",
                    error=str(e),
                    description=sample.get("description", ""),
                )
                evaluation.results.append(result)
                evaluation.errors += 1
                _emit(f"  [{i+1}/{len(EVAL_SAMPLES)}] ERROR: {e}")

            # Rate limit: small delay between requests
            await asyncio.sleep(0.5)

    latencies = [r.latency_ms for r in evaluation.results if r.error is None]
    evaluation.accuracy = correct / len(EVAL_SAMPLES) if EVAL_SAMPLES else 0
    evaluation.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0

    _emit(f"\n  Accuracy: {evaluation.accuracy:.1%} ({correct}/{len(EVAL_SAMPLES)})")
    _emit(f"  Avg latency: {evaluation.avg_latency_ms:.0f}ms")
    _emit(f"  Errors: {evaluation.errors}")

    return evaluation


async def evaluate_embedding_model(
    model: str, api_token: str
) -> ModelEvaluation:
    """Run eval samples through an embedding model to test availability and latency."""
    from datetime import datetime, timezone

    _emit(f"\n{'='*60}")
    _emit(f"Evaluating embedding: {model}")
    _emit(f"{'='*60}")

    # Use a subset of samples for embedding eval
    samples = EVAL_SAMPLES[:5]

    evaluation = ModelEvaluation(
        model_name=model,
        model_type="embedding",
        total_samples=len(samples),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    headers = {"Authorization": f"Bearer {api_token}"}
    successful = 0
    url = f"{EMBED_URL}/{model}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, sample in enumerate(samples):
            _update_progress(f"Embedding: {model.split('/')[-1]} - sample {i+1}/{len(samples)}")
            payload = {"inputs": sample["text"][:500]}

            start = time.perf_counter()
            try:
                response = await client.post(url, json=payload, headers=headers)
                elapsed_ms = (time.perf_counter() - start) * 1000

                if response.status_code != 200:
                    result = EmbeddingResult(
                        sample_text=sample["text"],
                        dimensions=0,
                        latency_ms=elapsed_ms,
                        error=f"HTTP {response.status_code}: {response.text[:100]}",
                    )
                    evaluation.results.append(result)
                    evaluation.errors += 1
                    _emit(f"  [{i+1}/{len(samples)}] ERROR: HTTP {response.status_code}")
                    continue

                data = response.json()
                # Determine dimensions
                if isinstance(data, list) and len(data) > 0:
                    if isinstance(data[0], float):
                        dims = len(data)
                    elif isinstance(data[0], list):
                        dims = len(data[0])
                    else:
                        dims = 0
                else:
                    dims = 0

                result = EmbeddingResult(
                    sample_text=sample["text"],
                    dimensions=dims,
                    latency_ms=elapsed_ms,
                )
                evaluation.results.append(result)
                successful += 1
                _emit(f"  [{i+1}/{len(samples)}] OK   {dims}d ({elapsed_ms:.0f}ms)")

            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                result = EmbeddingResult(
                    sample_text=sample["text"],
                    dimensions=0,
                    latency_ms=elapsed_ms,
                    error=str(e),
                )
                evaluation.results.append(result)
                evaluation.errors += 1
                _emit(f"  [{i+1}/{len(samples)}] ERROR: {e}")

            await asyncio.sleep(0.3)

    latencies = [r.latency_ms for r in evaluation.results if r.error is None]
    evaluation.accuracy = successful / len(samples) if samples else 0
    evaluation.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0

    _emit(f"\n  Success rate: {evaluation.accuracy:.1%} ({successful}/{len(samples)})")
    _emit(f"  Avg latency: {evaluation.avg_latency_ms:.0f}ms")

    return evaluation


async def run_full_eval(
    api_token: str,
    classification_only: bool = False,
    embedding_only: bool = False,
) -> list[dict]:
    """Run the full evaluation harness."""
    all_results: list[dict] = []

    if not embedding_only:
        for mi, model in enumerate(CLASSIFICATION_MODELS):
            _update_progress(f"Classification model {mi+1}/{len(CLASSIFICATION_MODELS)}: {model.split('/')[-1]}")
            try:
                evaluation = await evaluate_classification_model(model, api_token)
                all_results.append(evaluation.to_dict())
                _save_incremental(all_results)
            except Exception as e:
                _emit(f"  FATAL error evaluating {model}: {e}")

    if not classification_only:
        for mi, model in enumerate(EMBEDDING_MODELS):
            _update_progress(f"Embedding model {mi+1}/{len(EMBEDDING_MODELS)}: {model.split('/')[-1]}")
            try:
                evaluation = await evaluate_embedding_model(model, api_token)
                all_results.append(evaluation.to_dict())
                _save_incremental(all_results)
            except Exception as e:
                _emit(f"  FATAL error evaluating {model}: {e}")

    # Final save
    _save_incremental(all_results)
    _save_history(all_results)
    _emit(f"\n{'='*60}")
    _emit(f"Results saved to {RESULTS_PATH}")
    _emit(f"View at http://localhost:8000/eval")
    _emit(f"{'='*60}")

    return all_results


def main():
    import argparse
    import os

    lock_file = PROJECT_ROOT / ".eval_running"

    parser = argparse.ArgumentParser(description="Second Brain Model Evaluation Harness")
    parser.add_argument("--classification-only", action="store_true", help="Only evaluate classification models")
    parser.add_argument("--embedding-only", action="store_true", help="Only evaluate embedding models")
    args = parser.parse_args()

    # Load token from .env
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    api_token = os.environ.get("HF_API_TOKEN")
    if not api_token:
        _emit("ERROR: HF_API_TOKEN not found in .env")
        lock_file.unlink(missing_ok=True)
        return

    # Write PID to a dedicated file (separate from progress so updates don't clobber it)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    lock_file.write_text("Starting...", encoding="utf-8")

    # Clear previous log
    _log_lines.clear()
    LOG_FILE.write_text("", encoding="utf-8")

    _emit("Second Brain -- Model Evaluation Harness")
    _emit(f"Classification models: {len(CLASSIFICATION_MODELS)}")
    _emit(f"Embedding models: {len(EMBEDDING_MODELS)}")
    _emit(f"Eval samples: {len(EVAL_SAMPLES)}")

    try:
        asyncio.run(run_full_eval(
            api_token,
            classification_only=args.classification_only,
            embedding_only=args.embedding_only,
        ))
    finally:
        lock_file.unlink(missing_ok=True)
        PID_FILE.unlink(missing_ok=True)
        _emit("Evaluation complete.")


if __name__ == "__main__":
    main()
