"""Public Numbers3 dashboard projection: bounded, evidenced and read-only."""
from datetime import date, datetime, timedelta
from pathlib import Path

from .sources import JST, atomic_json, read_json, load_records
from .issuance import read_issued

def snapshot(root: Path, *, now: datetime | None = None) -> dict:
    now = (now or datetime.now(JST)).astimezone(JST)
    verified = load_records(root, "verified")
    secondary = load_records(root, "secondary")
    source = read_json(root / "research/last_source_audit.json")
    research = read_json(root / "research/replay.json")
    academic = read_json(root / "research/academic_discovery.json")
    issued = read_issued(root)
    end = now.date()
    start = end - timedelta(days=6)
    recent = [r for r in research.get("recent_rounds", [])
              if start.isoformat() <= r["draw_date"] <= end.isoformat()]
    pending = [{
        "round": r["target_round"], "draw_date": r["draw_date"],
        "number": r["number"], "mode": r["mode"],
        "issued_at_jst": r["issued_at_jst"],
        "status": "unwitnessed_not_formally_graded",
        "winning_number": next((d["winning_number"] for d in verified
                                if d["round"] == r["target_round"]), None)
    } for r in issued if start.isoformat() <= r["draw_date"] <= end.isoformat()]
    latest_verified = verified[-1] if verified else None
    latest_secondary = secondary[-1] if secondary else None
    warnings = []
    if not verified:
        warnings.append("みずほ銀行と楽天の照合済み結果がありません。正式な的中判定や本番AI昇格は停止しています。")
    if latest_secondary and (not latest_verified or
                              latest_secondary["round"] > latest_verified["round"]):
        warnings.append("楽天のみの参考結果は銀行未照合です。研究目的以外で採点しません。")
    if source.get("errors"):
        warnings.append("公式取得に未解決エラーがあります。ソース監査ログを確認してください。")
    if not secondary:
        warnings.append("オンライン学習用のNumbers3履歴はまだ取得されていません。")
    return {
        "version": "numbers3-dashboard-v1",
        "product": "Numbers3", "generated_at_jst": now.isoformat(timespec="seconds"),
        "latest_verified_draw": latest_verified,
        "latest_secondary_draw": latest_secondary,
        "verified_draws": len(verified),
        "secondary_research_draws": len(secondary),
        "issued_forecasts": len(issued),
        "formally_graded_forecasts": 0,
        "source_audit": source,
        "research": research,
        "academic_discovery": academic,
        "recent_week": {
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "retrospective_rows": recent, "issued_rows": pending,
            "research_straight_hits": sum(r["research_hit"] for r in recent)
        },
        "prediction_skill_confirmed": False,
        "automatic_production_promotion": False,
        "actual_purchase_profit_yen": None,
        "warnings": warnings
    }

def write_dashboard(root: Path, *, now: datetime | None = None) -> dict:
    obj = snapshot(root, now=now)
    atomic_json(root / "docs/data/status.json", obj)
    return obj
