"""Evaluation harness for testing classification and embedding models.

Usage:
    python -m scripts.eval_harness [--classification-only] [--embedding-only]

Tests models against a labeled dataset and outputs results to eval_results.json.
View results at http://localhost:8000/eval
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import structlog

log = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "eval_results.json"

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
    "sentence-transformers/all-MiniLM-L6-v2",
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
        return {
            "model_name": self.model_name,
            "model_type": self.model_type,
            "accuracy": round(self.accuracy, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "total_samples": self.total_samples,
            "errors": self.errors,
            "timestamp": self.timestamp,
            "results": [
                {
                    "text": r.sample_text[:80],
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

    print(f"\n{'='*60}")
    print(f"Evaluating classification: {model}")
    print(f"{'='*60}")

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
                    )
                    evaluation.results.append(result)
                    evaluation.errors += 1
                    print(f"  [{i+1}/{len(EVAL_SAMPLES)}] ERROR: HTTP {response.status_code}")
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
                )
                evaluation.results.append(result)

                status = "✅" if is_correct else "❌"
                print(
                    f"  [{i+1}/{len(EVAL_SAMPLES)}] {status} "
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
                )
                evaluation.results.append(result)
                evaluation.errors += 1
                print(f"  [{i+1}/{len(EVAL_SAMPLES)}] ERROR: {e}")

            # Rate limit: small delay between requests
            await asyncio.sleep(0.5)

    latencies = [r.latency_ms for r in evaluation.results if r.error is None]
    evaluation.accuracy = correct / len(EVAL_SAMPLES) if EVAL_SAMPLES else 0
    evaluation.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0

    print(f"\n  Accuracy: {evaluation.accuracy:.1%} ({correct}/{len(EVAL_SAMPLES)})")
    print(f"  Avg latency: {evaluation.avg_latency_ms:.0f}ms")
    print(f"  Errors: {evaluation.errors}")

    return evaluation


async def evaluate_embedding_model(
    model: str, api_token: str
) -> ModelEvaluation:
    """Run eval samples through an embedding model to test availability and latency."""
    from datetime import datetime, timezone

    print(f"\n{'='*60}")
    print(f"Evaluating embedding: {model}")
    print(f"{'='*60}")

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
                    print(f"  [{i+1}/{len(samples)}] ERROR: HTTP {response.status_code}")
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
                print(f"  [{i+1}/{len(samples)}] ✅ {dims}d ({elapsed_ms:.0f}ms)")

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
                print(f"  [{i+1}/{len(samples)}] ERROR: {e}")

            await asyncio.sleep(0.3)

    latencies = [r.latency_ms for r in evaluation.results if r.error is None]
    evaluation.accuracy = successful / len(samples) if samples else 0
    evaluation.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0

    print(f"\n  Success rate: {evaluation.accuracy:.1%} ({successful}/{len(samples)})")
    print(f"  Avg latency: {evaluation.avg_latency_ms:.0f}ms")

    return evaluation


async def run_full_eval(
    api_token: str,
    classification_only: bool = False,
    embedding_only: bool = False,
) -> list[dict]:
    """Run the full evaluation harness."""
    all_results: list[dict] = []

    if not embedding_only:
        for model in CLASSIFICATION_MODELS:
            try:
                evaluation = await evaluate_classification_model(model, api_token)
                all_results.append(evaluation.to_dict())
            except Exception as e:
                print(f"  FATAL error evaluating {model}: {e}")

    if not classification_only:
        for model in EMBEDDING_MODELS:
            try:
                evaluation = await evaluate_embedding_model(model, api_token)
                all_results.append(evaluation.to_dict())
            except Exception as e:
                print(f"  FATAL error evaluating {model}: {e}")

    # Save results
    RESULTS_PATH.write_text(json.dumps(all_results, indent=2))
    print(f"\n{'='*60}")
    print(f"Results saved to {RESULTS_PATH}")
    print(f"View at http://localhost:8000/eval")
    print(f"{'='*60}")

    return all_results


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Second Brain Model Evaluation Harness")
    parser.add_argument("--classification-only", action="store_true", help="Only evaluate classification models")
    parser.add_argument("--embedding-only", action="store_true", help="Only evaluate embedding models")
    args = parser.parse_args()

    # Load token from .env
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    api_token = os.environ.get("HF_API_TOKEN")
    if not api_token:
        print("ERROR: HF_API_TOKEN not found in .env")
        return

    print("🧠 Second Brain — Model Evaluation Harness")
    print(f"Classification models: {len(CLASSIFICATION_MODELS)}")
    print(f"Embedding models: {len(EMBEDDING_MODELS)}")
    print(f"Eval samples: {len(EVAL_SAMPLES)}")

    asyncio.run(run_full_eval(
        api_token,
        classification_only=args.classification_only,
        embedding_only=args.embedding_only,
    ))


if __name__ == "__main__":
    main()
