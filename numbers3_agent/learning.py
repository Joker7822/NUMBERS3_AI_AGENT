"""Strict past-only Numbers3 research replay: no prediction-skill claims."""
from __future__ import annotations
from collections import deque
from datetime import datetime
from hashlib import sha256
from math import log, prod
from pathlib import Path
import csv
import json
import random

from .rules import three_digits, OUTCOMES
from .sources import JST, SourceError, atomic_json, load_records

MODELS = (("positional_30_alpha5", 30, 5),
          ("positional_100_alpha10", 100, 10),
          ("positional_250_alpha20", 250, 20))
FIELDS = ("round", "draw_date", "actual", "data_cutoff_round",
          "research_number", "research_model", "research_hit",
          "uniform_number", "uniform_hit", "source_status")

def uniform_ticket(round_number: int) -> str:
    seed = sha256(f"Numbers3-uniform-v1:{round_number}".encode()).digest()
    return f"{random.Random(int.from_bytes(seed[:8], 'big')).randrange(OUTCOMES):03d}"

def positional_prob(numbers: list[str], alpha: int) -> list[list[float]]:
    if type(alpha) is not int or alpha <= 0:
        raise ValueError("alpha must be a positive integer")
    for number in numbers:
        three_digits(number)
    return [[(sum(int(n[pos]) == digit for n in numbers) + alpha) /
             (len(numbers) + 10 * alpha) for digit in range(10)]
            for pos in range(3)]

def best_ticket(prob: list[list[float]]) -> str:
    if len(prob) != 3 or any(len(line) != 10 for line in prob):
        raise ValueError("three digit-position distributions are required")
    return max((f"{n:03d}" for n in range(OUTCOMES)),
               key=lambda n: (prod(prob[pos][int(d)] for pos, d in enumerate(n)),
                              -int(n)))

def log_edge(prob: list[list[float]], actual: str) -> float:
    actual = three_digits(actual)
    return log(OUTCOMES * prod(prob[pos][int(n)] for pos, n in enumerate(actual)))

def _choose(scores: dict[str, deque], trained: int) -> str:
    if trained < 60:
        return "uniform"
    eligible = [(sum(trace) / len(trace), model) for model, trace in scores.items()
                if len(trace) >= 60 and sum(trace) / len(trace) > 0.02]
    return max(eligible)[1] if eligible else "uniform"

def replay(rows: list[dict]) -> tuple[dict, list[dict]]:
    """Every forecast is computed before consuming its actual winning number."""
    if not rows:
        return ({
            "product": "Numbers3", "status": "no_secondary_history",
            "data_scope": "research_only_not_preissued",
            "evaluated_draws": 0, "reference_straight_hits": 0,
            "research_straight_hits": 0, "next_research_candidate": None,
            "recent_rounds": [], "officially_verified": False,
            "prediction_skill_confirmed": False, "production_model_changed": False
        }, [])
    previous = None
    for row in rows:
        if type(row["round"]) is not int or row["round"] < 1:
            raise SourceError("invalid research round")
        if previous is not None and (row["round"] != previous["round"] + 1
                                     or row["draw_date"] <= previous["draw_date"]):
            raise SourceError("research history is incomplete or nonchronological")
        three_digits(row["winning_number"])
        previous = row
    histories = {name: deque(maxlen=window) for name, window, _ in MODELS}
    edges = {name: deque(maxlen=90) for name, _, _ in MODELS}
    grades = []
    for index, row in enumerate(rows):
        number = row["winning_number"]
        if index:
            model = _choose(edges, index)
            baseline = uniform_ticket(row["round"])
            current_probs = {name: positional_prob(list(histories[name]), alpha)
                             for name, _, alpha in MODELS}
            choice = (baseline if model == "uniform" else
                      best_ticket(current_probs[model]))
            grades.append({
                "round": row["round"], "draw_date": row["draw_date"],
                "actual": number, "data_cutoff_round": rows[index - 1]["round"],
                "research_number": choice, "research_model": model,
                "research_hit": int(choice == number),
                "uniform_number": baseline, "uniform_hit": int(baseline == number),
                "source_status": "single_rakuten_publisher_not_officially_verified"
            })
            # Only after the row is scored may its result affect future choices.
            for name, prob in current_probs.items():
                edges[name].append(log_edge(prob, number))
        for name in histories:
            histories[name].append(number)
    target = rows[-1]["round"] + 1
    chosen = _choose(edges, len(rows))
    next_num = (uniform_ticket(target) if chosen == "uniform" else
                best_ticket(positional_prob(list(histories[chosen]),
                                           next(a for name, _, a in MODELS if name == chosen))))
    summary = {
        "product": "Numbers3",
        "status": "historical_walk_forward_reconstruction_only",
        "data_scope": "single_rakuten_publisher_not_officially_verified",
        "first_recorded_round": rows[0]["round"],
        "last_recorded_round": rows[-1]["round"],
        "evaluated_draws": len(grades),
        "research_straight_hits": sum(x["research_hit"] for x in grades),
        "reference_straight_hits": sum(x["uniform_hit"] for x in grades),
        "theoretical_uniform_expected_straight_hits": round(len(grades) / 1000, 4),
        "research_model_counts": {name: sum(x["research_model"] == name for x in grades)
                                  for name in ("uniform", *(n for n, _, _ in MODELS))},
        "next_research_candidate": {
            "round": target, "draw_date": None, "number": next_num, "model": chosen,
            "training_last_round": rows[-1]["round"],
            "status": "research_only_not_issued_not_purchased",
            "officially_verified": False, "actual_purchase": False
        },
        "recent_rounds": list(reversed(grades[-25:])),
        "officially_verified": False,
        "prediction_skill_confirmed": False, "production_model_changed": False,
        "interpretation": "Retrospective selection repeatedly uses historical cohorts; no independent prospective evidence."
    }
    return summary, grades

def run_replay(root: Path, *, now: datetime | None = None) -> dict:
    stamp = (now or datetime.now(JST)).astimezone(JST)
    rows = load_records(root, "secondary")
    summary, grades = replay(rows)
    summary["generated_at_jst"] = stamp.isoformat(timespec="seconds")
    target = root / "research/round_predictions.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Historical replay may be rewritten when the model research algorithm
    # changes; unlike the original source ledger, it is NOT an immutable issue.
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(grades)
    summary["replay_sha256"] = sha256(target.read_bytes()).hexdigest()
    atomic_json(root / "research/replay.json", summary)
    return summary
