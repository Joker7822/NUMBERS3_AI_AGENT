"""Bounded academic search for hypothesis generation, never executable code."""
from datetime import datetime
from pathlib import Path
import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse

from .sources import JST, atomic_json

ENDPOINT = "https://api.crossref.org/works"
TOPICS = (
    "sequential probability forecasting proper scoring rule",
    "time series calibration online learning"
)

def discover(*, now: datetime | None = None, fetch=None) -> dict:
    now = (now or datetime.now(JST)).astimezone(JST)
    items = {}
    errors = []
    for topic in TOPICS:
        url = ENDPOINT + "?" + urlencode({
            "query.title": topic, "rows": 5, "select": "DOI,title,published,URL",
            "sort": "published", "order": "desc"
        })
        if urlparse(url).hostname != "api.crossref.org":
            raise ValueError("academic discovery attempted untrusted host")
        try:
            if fetch is None:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "NUMBERS3_AI_AGENT/0.1 (read-only method discovery)"
                })
                with urllib.request.urlopen(req, timeout=10) as response:
                    if urlparse(response.geturl()).hostname != "api.crossref.org":
                        raise ValueError("Crossref redirected outside approved host")
                    raw = response.read(300_001)
            else:
                raw = fetch(url)
            if not isinstance(raw, bytes) or len(raw) > 300_000:
                raise ValueError("Crossref response is missing or oversized")
            records = json.loads(raw)["message"]["items"]
            if not isinstance(records, list):
                raise ValueError("Crossref works list invalid")
            for record in records[:5]:
                doi = record.get("DOI")
                title = record.get("title")
                if (not isinstance(doi, str) or not (1 <= len(doi) <= 200)
                        or not re.fullmatch(r"10\.[0-9]{4,9}/[^\s]+", doi)
                        or not isinstance(title, list) or not title or
                        not isinstance(title[0], str)):
                    continue
                items[doi] = {
                    "doi": doi, "title": title[0][:240],
                    "url": "https://doi.org/" + doi,
                    "hypothesis_only": True
                }
        except (ValueError, TypeError, KeyError, IndexError, UnicodeError,
                urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append({"topic": topic, "reason": type(exc).__name__})
    return {
        "version": "numbers3-academic-discovery-v1",
        "generated_at_jst": now.isoformat(timespec="seconds"),
        "queries": len(TOPICS),
        "sources_found": len(items), "items": list(items.values())[:10],
        "errors": errors, "external_code_executed": False,
        "search_results_changed_model_weights": False,
        "prediction_skill_confirmed": False,
        "status": "search_completed" if items else "no_usable_sources",
    }

def save(root: Path, *, now: datetime | None = None, fetch=None) -> dict:
    report = discover(now=now, fetch=fetch)
    atomic_json(root / "research/academic_discovery.json", report)
    return report
