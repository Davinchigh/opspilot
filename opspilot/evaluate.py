"""Score the pipeline against labelled messages.

    python -m opspilot eval                 # test split, with the configured provider
    python -m opspilot eval --split dev     # the split you may tune against
"""
import json
from dataclasses import replace
from pathlib import Path

from .config import ROOT, Settings
from .pipeline import Pipeline

DATASET = ROOT / "evals" / "dataset.jsonl"
FIELDS = ("product", "quantity", "date", "area")
# Minimum acceptable scores. CI fails below these.
GATES = {"escalation_recall": 0.9, "injection_recall": 0.9, "intent_accuracy": 0.7, "retrieval_hit_rate": 0.7}


def load(split: str, path: Path = DATASET) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    return [c for c in cases if split == "all" or c["split"] == split]


def ratio(hits: list[bool]) -> float | None:
    return round(sum(hits) / len(hits), 3) if hits else None


def evaluate(pipeline: Pipeline, cases: list[dict]) -> dict:
    scores = {k: [] for k in ("intent_accuracy", "field_accuracy", "retrieval_hit_rate",
                              "escalation_recall", "escalation_precision", "injection_recall")}
    failures, latencies, cost, fallbacks = [], [], 0.0, 0
    for case in cases:
        result = pipeline.run(case["message"])
        latencies.append(result["metrics"]["latency_ms"])
        cost += result["metrics"]["cost_usd"]
        fallbacks += "model_fallback" in result["flags"]
        wrong = []

        def score(metric, passed, label):
            scores[metric].append(passed)
            if not passed:
                wrong.append(label)

        got = result["triage"]
        score("intent_accuracy", got["intent"] == case["intent"], f"intent={got['intent']}")
        for field in FIELDS:
            if field in case.get("fields", {}):
                value = got.get(field)
                value = value.lower() if isinstance(value, str) else value
                want = case["fields"][field]
                want = want.lower() if isinstance(want, str) else want
                score("field_accuracy", value == want, f"{field}={got.get(field)!r}")
        if case.get("source"):
            ids = [s["id"] for s in result["sources"]][:3]  # score the search itself, not the extras
            score("retrieval_hit_rate", case["source"] in ids, f"sources={ids}")
        escalated = result["status"] == "escalated"
        if case["escalate"]:
            score("escalation_recall", escalated, "missed escalation")
        if escalated:
            score("escalation_precision", case["escalate"], f"needless escalation {result['flags']}")
        if case.get("injection"):
            score("injection_recall", "prompt_injection" in result["flags"], "missed injection")
        if wrong:
            failures.append({"id": case["id"], "message": case["message"], "wrong": wrong})
    ordered = sorted(latencies)
    return {
        "cases": len(cases),
        "scores": {k: ratio(v) for k, v in scores.items()},
        "p50_latency_ms": ordered[len(ordered) // 2] if ordered else None,
        "cost_usd": round(cost, 6),
        "model_fallbacks": fallbacks,
        "failures": failures,
    }


def gate(report: dict) -> list[str]:
    problems = []
    for metric, minimum in GATES.items():
        value = report["scores"][metric]
        if value is None or value < minimum:
            problems.append(f"{metric} is {value}, needs {minimum}")
    return problems


def baseline(settings: Settings) -> dict:
    """Offline scores for the dashboard. Never calls a model, so visitors cannot spend quota."""
    pipeline = Pipeline(replace(settings, provider="offline"))
    return {"gates": GATES, "splits": {split: evaluate(pipeline, load(split)) for split in ("dev", "test")}}


def main(split: str = "test", check: bool = False) -> int:
    settings = Settings.from_env()
    report = evaluate(Pipeline(settings), load(split))
    report = {"provider": settings.provider, "model": settings.model or "rules", "split": split, **report}
    print(json.dumps(report, indent=2))
    problems = gate(report) if check else []
    for p in problems:
        print("GATE FAILED:", p)
    return 1 if problems else 0
