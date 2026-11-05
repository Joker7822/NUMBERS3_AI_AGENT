"""Advisory-only, one-ticket, pre-deadline issue ledger.

Writing this file does not demonstrate an independently timestamped GitHub
publication. No formal accuracy claim is made until a separate witness exists.
"""
from __future__ import annotations
from datetime import date, datetime, time
from hashlib import sha256
from pathlib import Path
import json

from .rules import validate_play
from .sources import JST, load_records, SourceError

FILE = "data/issued_forecasts.jsonl"
DEADLINE = time(18, 0)

def read_issued(root: Path) -> list[dict]:
    path = root / FILE
    if not path.is_file():
        return []
    entries = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        rnd = row.get("target_round")
        if type(rnd) is not int or rnd < 1 or rnd in seen:
            raise SourceError("duplicate or invalid issued forecast")
        seen.add(rnd)
        validate_play(row["number"], row["mode"])
        created = datetime.fromisoformat(row["issued_at_jst"])
        target_day = date.fromisoformat(row["draw_date"])
        if (created.utcoffset() is None or created.date() > target_day or
                created >= datetime.fromisoformat(row["deadline_jst"]) or
                row.get("actual_purchase") is not False or
                row.get("publication_witnessed") is not False):
            raise SourceError("unauthorized pre-draw issued record")
        entries.append(row)
    return entries

def issue(root: Path, target_round: int, draw_date: str, number: str,
          mode: str = "straight", now: datetime | None = None) -> dict:
    now = (now or datetime.now(JST)).astimezone(JST)
    number, mode = validate_play(number, mode)
    day = date.fromisoformat(draw_date)
    deadline = datetime.combine(day, DEADLINE, JST)
    if (now.date() != day or now >= deadline or day.weekday() > 4):
        raise ValueError("issue requires today's weekday draw and before 18:00 JST")
    verified = load_records(root, "verified")
    if not verified or target_round != verified[-1]["round"] + 1:
        raise ValueError("immediately preceding bank-plus-Rakuten verified round required")
    if date.fromisoformat(verified[-1]["draw_date"]) >= day:
        raise ValueError("draw date must be after the last officially verified draw")
    if any(x["target_round"] == target_round for x in read_issued(root)):
        raise ValueError("target round is already recorded")
    record = {
        "product": "Numbers3", "target_round": target_round,
        "draw_date": day.isoformat(), "number": number, "mode": mode.value,
        "issued_at_jst": now.isoformat(timespec="seconds"),
        "deadline_jst": deadline.isoformat(timespec="seconds"),
        "source_verified_last_round": verified[-1]["round"],
        "publication_witnessed": False, "actual_purchase": False,
        "official_grade_authorized": False
    }
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
