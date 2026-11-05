"""Full Numbers3 historical research extension, explicitly NOT bank verification.

Read the game-specific Numbers3 V2 archive from a public GitHub Pages feed.
Corroborate every overlapping draw against separately fetched Rakuten rows.
An agreement of secondary publishers does not establish source independence,
official verification, or genuine prospective prediction skill.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse
import json
import urllib.error
import urllib.request

from .rules import three_digits
from .sources import (JST, SourceError, safe_date, valid_rows, load_records,
                      read_json, merge_history, atomic_json)

URL = "https://hazimekom.github.io/numbers4-api/api/v2/games/numbers3/draws.min.json"
EXTENDED_PATH = "data/secondary_extended.json"
AUDIT_PATH = "research/historical_extension_audit.json"
STATUS = "two_secondary_publishers_overlap_checked_not_bank_verified"
MAX_BYTES = 2_000_000

def parse_full_archive(raw: bytes) -> list[dict]:
    if not isinstance(raw, bytes) or not (3 <= len(raw) <= MAX_BYTES):
        raise SourceError("Numbers3 secondary full archive size invalid")
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise SourceError("Numbers3 V2 historical JSON invalid") from exc
    if not isinstance(parsed, list) or not 2 <= len(parsed) <= 20_000:
        raise SourceError("Numbers3 history is not a bounded draw list")
    rows = []
    for expected, item in enumerate(parsed, 1):
        if not isinstance(item, dict) or item.get("draw_no") != expected:
            raise SourceError("Numbers3 V2 archive lacks a continuous original round")
        result = item.get("result")
        if not isinstance(result, dict):
            raise SourceError("Numbers3 result structure invalid")
        digits = result.get("values")
        number = three_digits(result.get("display"))
        if (not isinstance(digits, list) or len(digits) != 3 or
            any(type(d) is not int or not 0 <= d <= 9 for d in digits) or
            "".join(str(d) for d in digits) != number):
            raise SourceError("Numbers3 result's digit array does not match displayed result")
        rows.append({
            "round": expected, "draw_date": safe_date(item.get("draw_date")),
            "winning_number": number
        })
    return valid_rows(rows, source="numbers3_v2_github_pages_only")

def download_full(url: str = URL) -> bytes:
    parsed = urlparse(url)
    if (url != URL or parsed.scheme != "https" or
        parsed.hostname != "hazimekom.github.io"):
        raise SourceError("unapproved Numbers3-only historical API URL")
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "NUMBERS3_AI_AGENT/0.1 (research-only archive crosscheck)"
    })
    try:
        with urllib.request.urlopen(req, timeout=18) as response:
            resolved = urlparse(response.geturl())
            if (response.status != 200 or resolved.scheme != "https" or
                resolved.hostname != "hazimekom.github.io"):
                raise SourceError("Numbers3 historical source redirect or status not allowed")
            raw = response.read(MAX_BYTES + 1)
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise ConnectionError("Numbers3 secondary archive temporarily unavailable") from exc
    if len(raw) > MAX_BYTES:
        raise SourceError("Numbers3 secondary archive exceeds bounded input size")
    return raw

def load_extended(root: Path) -> list[dict]:
    obj = read_json(root / EXTENDED_PATH)
    if not obj:
        return []
    if (obj.get("product") != "Numbers3" or obj.get("status") != STATUS or
        obj.get("official_bank_verified") is not False or
        obj.get("production_promotion_allowed") is not False or
        type(obj.get("overlap_count")) is not int or
        obj["overlap_count"] < 1 or
        not isinstance(obj.get("rows"), list)):
        raise SourceError("secondary historical extension lacks honest provenance")
    rows = valid_rows(obj["rows"], source="secondary_research_extended")
    if rows[0]["round"] != 1 or rows != obj["rows"]:
        raise SourceError("secondary full history is unordered or missing initial round")
    companion = {r["round"]: r for r in load_records(root, "secondary")}
    for row in rows:
        overlap = companion.get(row["round"])
        if overlap and (row["draw_date"], row["winning_number"]) != (
                overlap["draw_date"], overlap["winning_number"]):
            raise SourceError("stored full history conflicts with Rakuten")
    return rows

def extend(root: Path, *, now: datetime | None = None, fetch=download_full) -> dict:
    now = (now or datetime.now(JST)).astimezone(JST)
    rakuten = load_records(root, "secondary")
    old = load_extended(root)
    result = {
        "product": "Numbers3", "status": "pending",
        "checked_at_jst": now.isoformat(timespec="seconds"),
        "archive_url": URL, "previous_research_rows": len(old),
        "rakuten_rows": len(rakuten), "overlap_count": 0,
        "official_bank_verified": False,
        "prediction_skill_confirmed": False,
        "production_promotion_allowed": False,
        "new_research_rows": 0
    }
    if not rakuten:
        result["status"] = "no_rakuten_crosscheck_no_extension"
        atomic_json(root / AUDIT_PATH, result)
        return result
    try:
        raw = fetch()
    except (ConnectionError, TimeoutError, OSError, urllib.error.URLError) as exc:
        result["status"] = "secondary_archive_network_unavailable_preserved"
        result["reason"] = type(exc).__name__
        atomic_json(root / AUDIT_PATH, result)
        return result
    full = parse_full_archive(raw)
    by_github = {r["round"]: r for r in full}
    overlapping = [r for r in rakuten if r["round"] in by_github]
    # Realistically, a months-long Rakuten window overlaps hundreds of rows.
    # Require at least 50 matches when available; small fixtures use all rows.
    minimum = min(50, len(rakuten))
    if len(overlapping) < minimum:
        raise SourceError("full secondary source lacks sufficient Rakuten overlap")
    for row in overlapping:
        counterpart = by_github[row["round"]]
        if ((counterpart["draw_date"], counterpart["winning_number"]) !=
            (row["draw_date"], row["winning_number"])):
            raise SourceError("Numbers3 full archive and Rakuten disagree on a draw")
    combined = merge_history(full, rakuten)
    if combined[0]["round"] != 1 or combined[-1]["round"] != len(combined):
        raise SourceError("original Numbers3 history missing a round")
    combined = merge_history(old, combined)
    result.update({
        "status": "extended_secondary_history_not_officially_verified",
        "overlap_count": len(overlapping),
        "github_archive_rows": len(full),
        "total_research_rows": len(combined),
        "new_research_rows": len(combined) - len(old),
        "github_archive_response_sha256": sha256(raw).hexdigest()
    })
    if combined != old:
        atomic_json(root / EXTENDED_PATH, {
            "product": "Numbers3", "status": STATUS,
            "official_bank_verified": False,
            "production_promotion_allowed": False,
            "overlap_count": len(overlapping),
            "updated_at_jst": now.isoformat(timespec="seconds"),
            "github_archive_url": URL,
            "github_archive_sha256": sha256(raw).hexdigest(),
            "source_independence_proven": False,
            "rows": combined
        })
    atomic_json(root / AUDIT_PATH, result)
    return result
