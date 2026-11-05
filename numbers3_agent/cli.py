"""CLI for Numbers3-only evidence, adaptive research and safe publication."""
from __future__ import annotations
from argparse import ArgumentParser
from pathlib import Path
import json
import sys

from .sources import refresh
from .learning import run_replay
from .dashboard import write_dashboard, snapshot
from .issuance import issue
from .research import save as run_academic_search

def parser() -> ArgumentParser:
    ap = ArgumentParser(prog="numbers3-agent")
    ap.add_argument("--root", type=Path, default=Path("."))
    sub = ap.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="compare Numbers3 official bank and Rakuten sources")
    fetch.add_argument("--months-back", type=int, default=3)
    fetch.add_argument("--bank-browser-fallback", action="store_true")
    sub.add_parser("replay", help="past-only walk-forward research replay")
    sub.add_parser("dashboard", help="create a safe public dashboard snapshot")
    sub.add_parser("audit", help="read-only current evidence status")
    cycle = sub.add_parser("cycle", help="fetch, learn and refresh public evidence")
    cycle.add_argument("--months-back", type=int, default=3)
    cycle.add_argument("--bank-browser-fallback", action="store_true")
    published = sub.add_parser("issue", help="explicit one-ticket advisory; not a purchase")
    published.add_argument("--round", type=int, required=True)
    published.add_argument("--date", required=True)
    published.add_argument("--number", required=True)
    published.add_argument("--mode", choices=["straight","box","set","mini"], default="straight")
    return ap

def main(args: list[str] | None = None) -> int:
    parsed = parser().parse_args(args)
    root = parsed.root.resolve()
    try:
        if parsed.command == "fetch":
            report = refresh(root, months_back=parsed.months_back,
                             browser_fallback=parsed.bank_browser_fallback)
        elif parsed.command == "replay":
            report = run_replay(root)
        elif parsed.command == "dashboard":
            report = write_dashboard(root)
        elif parsed.command == "audit":
            report = snapshot(root)
        elif parsed.command == "cycle":
            evidence = refresh(root, months_back=parsed.months_back,
                               browser_fallback=parsed.bank_browser_fallback)
            model = run_replay(root)
            academic = run_academic_search(root)
            public = write_dashboard(root)
            report = {
                "product": "Numbers3", "source": evidence,
                "learning": {k: model.get(k) for k in
                             ("status","evaluated_draws","research_straight_hits",
                              "reference_straight_hits","next_research_candidate")},
                "academic_search": {
                    "status": academic["status"],
                    "sources_found": academic["sources_found"],
                    "external_code_executed": False
                },
                "dashboard_generated_at_jst": public["generated_at_jst"]
            }
        elif parsed.command == "issue":
            report = issue(root, target_round=parsed.round,
                           draw_date=parsed.date, number=parsed.number, mode=parsed.mode)
        else:
            raise ValueError("invalid command")
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("監査・検証エラー: " + str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
