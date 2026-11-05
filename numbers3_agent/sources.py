"""Provenance-separated Numbers3 results from Mizuho and Rakuten.

Never call a secondary publisher official. Both independently parsed results
must have identical round/date/number before becoming a verified observation.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import json
import re
import urllib.error
import urllib.request

from .rules import three_digits

JST = timezone(timedelta(hours=9))
BANK = "https://www.mizuhobank.co.jp/takarakuji/check/numbers/numbers3/index.html"
RAKUTEN = "https://takarakuji.rakuten.co.jp/backnumber/numbers3/"
SECONDARY = "data/secondary_history.json"
VERIFIED = "data/verified_draws.json"
MAX_BYTES = 2_000_000

class SourceError(ValueError):
    pass

def safe_date(raw: str) -> str:
    m = re.fullmatch(r"\s*(\d{4})\s*(?:年|/|-)\s*(\d{1,2})\s*(?:月|/|-)\s*(\d{1,2})\s*日?\s*", raw)
    if not m:
        raise SourceError("invalid publisher draw date")
    result = date(int(m[1]), int(m[2]), int(m[3]))
    return result.isoformat()

def valid_rows(rows: list[dict], *, source: str) -> list[dict]:
    seen = set()
    output = []
    for item in rows:
        rnd = item.get("round")
        if type(rnd) is not int or rnd < 1 or rnd > 100_000 or rnd in seen:
            raise SourceError("invalid or repeated draw round")
        seen.add(rnd)
        day = safe_date(item["draw_date"])
        value = three_digits(item["winning_number"])
        output.append({"round": rnd, "draw_date": day, "winning_number": value})
    output.sort(key=lambda row: row["round"])
    for a, b in zip(output, output[1:]):
        if b["round"] != a["round"] + 1 or b["draw_date"] <= a["draw_date"]:
            raise SourceError("draw history has a gap or nonchronological dates")
    return output

class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.ignored = 0
        self.table = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.ignored += 1
        if self.ignored:
            return
        if tag == "tr":
            self.row = []
        if tag in ("th", "td") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.ignored = max(0, self.ignored - 1)
            return
        if self.ignored:
            return
        if tag in ("th", "td") and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None

    def handle_data(self, data):
        if not self.ignored and data.strip():
            value = " ".join(data.split())
            self.items.append(value)
            if self.cell is not None:
                self.cell.append(value)

def parse_rakuten(html: str) -> list[dict]:
    parser = Visible()
    parser.feed(html)
    stream = " ".join(parser.items)
    if not re.search(r"ナンバーズ3|NUMBERS3", stream, re.I):
        raise SourceError("not the Numbers3 Rakuten results page")
    pat = re.compile(
        r"回号\s*第\s*(\d{1,6})\s*回\s*抽せん日\s*"
        r"(\d{4}/\d{1,2}/\d{1,2})\s*当せん番号\s*([0-9]{3})(?![0-9])"
    )
    records = [{"round": int(m[1]), "draw_date": m[2],
                "winning_number": m[3]} for m in pat.finditer(stream)]
    if not records:
        raise SourceError("Rakuten page has no labeled draw results")
    return valid_rows(records, source="rakuten")

def parse_bank(html: str) -> list[dict]:
    parser = Visible()
    parser.feed(html)
    stream = " ".join(parser.items)
    if not re.search(r"ナンバーズ3|ナンバーズ３", stream):
        raise SourceError("not a Numbers3 Mizuho result page")
    pat = re.compile(
        r"回別\s*第\s*(\d{1,6})\s*回\s*抽せん日\s*"
        r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)\s*"
        r"抽せん数字\s*([0-9]{3})(?![0-9])"
    )
    rows = [{"round": int(m[1]), "draw_date": m[2],
             "winning_number": m[3]} for m in pat.finditer(stream)]
    # Older bank backnumber table: [round, date, Numbers3, Numbers4].
    for cells in parser.table:
        if len(cells) == 4:
            m = re.fullmatch(r"第\s*(\d{1,6})\s*回", cells[0])
            if m and re.fullmatch(r"[0-9]{3}", cells[2]) and re.fullmatch(r"[0-9]{4}", cells[3]):
                rows.append({"round": int(m[1]), "draw_date": cells[1],
                             "winning_number": cells[2]})
    if not rows:
        raise SourceError("Mizuho official rows not present; possibly JavaScript-only")
    return valid_rows(rows, source="bank")

def month_pairs(now: datetime, months_back: int) -> list[tuple[int, int]]:
    if type(months_back) is not int or not 1 <= months_back <= 12:
        raise ValueError("months_back must be 1..12")
    local = now.astimezone(JST)
    start = local.year * 12 + local.month - 1
    return [(n // 12, n % 12 + 1) for n in (start - i for i in range(months_back))]

def download(url: str, host: str, *, opener=None) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != host or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise SourceError("source URL is not allowlisted")
    req = urllib.request.Request(url, headers={
        "User-Agent": "NUMBERS3_AI_AGENT/0.1 (read-only evidence)", "Accept": "text/html"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=16) as resp:
            actual = urlparse(resp.geturl())
            if resp.status != 200 or actual.scheme != "https" or actual.hostname != host:
                raise SourceError("publisher redirect or HTTP status not approved")
            raw = resp.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise SourceError("HTML exceeds source size limit")
            charset = resp.headers.get_content_charset() or "utf-8"
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        raise SourceError("publisher request unavailable: " + type(exc).__name__) from exc
    try:
        return raw.decode(charset), sha256(raw).hexdigest()
    except (LookupError, UnicodeDecodeError) as exc:
        raise SourceError("publisher character encoding invalid") from exc

def browser_bank(url: str) -> tuple[str, str]:
    """Optional bounded fallback for the one allowlisted bank host only."""
    target = urlparse(url)
    if target.scheme != "https" or target.hostname != "www.mizuhobank.co.jp":
        raise SourceError("browser bank URL not approved")
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError as exc:
        raise SourceError("Chromium fallback is unavailable") from exc
    try:
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True)
            try:
                page = browser.new_page(locale="ja-JP")
                page.goto(url, wait_until="domcontentloaded", timeout=18_000)
                try:
                    page.wait_for_function(
                        "() => /第\\s*\\d+\\s*回/.test(document.body?.innerText || '')",
                        timeout=9_000)
                except PlaywrightTimeout:
                    pass
                if urlparse(page.url).hostname != "www.mizuhobank.co.jp":
                    raise SourceError("bank browser redirected outside approved host")
                html = page.content()
            finally:
                browser.close()
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError("bank renderer failed: " + type(exc).__name__) from exc
    raw = html.encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise SourceError("rendered bank DOM exceeds limit")
    return html, sha256(raw).hexdigest()

def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise SourceError("stored source evidence must be an object")
    return obj

def load_records(root: Path, kind: str) -> list[dict]:
    if kind not in ("secondary", "verified"):
        raise SourceError("unsupported source ledger")
    path = root / (SECONDARY if kind == "secondary" else VERIFIED)
    obj = read_json(path)
    if not obj:
        return []
    status = ("single_rakuten_publisher_not_officially_verified" if kind == "secondary"
              else "bank_primary_rakuten_publication_match")
    if (obj.get("product") != "Numbers3" or obj.get("status") != status or
            not isinstance(obj.get("rows"), list)):
        raise SourceError("stored result provenance is invalid")
    rows = valid_rows(obj["rows"], source=kind)
    if kind == "verified":
        for row in obj["rows"]:
            if (row.get("verification") != status or
                    not re.fullmatch("[a-f0-9]{64}", row.get("bank_sha256", "")) or
                    not re.fullmatch("[a-f0-9]{64}", row.get("rakuten_sha256", ""))):
                raise SourceError("bank verification provenance incomplete")
    return obj["rows"]

def atomic_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_suffix(".tmp")
    candidate.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    candidate.replace(path)

def merge_history(previous: list[dict], incoming: list[dict], *, strict: bool = True) -> list[dict]:
    merged = {r["round"]: r for r in previous}
    for row in incoming:
        rnd = row["round"]
        if rnd in merged:
            if any(merged[rnd][key] != row[key] for key in
                   ("round", "draw_date", "winning_number")):
                raise SourceError("publisher revised recorded draw; manual review required")
        else:
            merged[rnd] = row
    result = [merged[n] for n in sorted(merged)]
    valid_rows(result, source="merged")
    return result

def refresh(root: Path, *, now: datetime | None = None, months_back: int = 3,
            opener=None, browser_fallback: bool = False) -> dict:
    """Fetch, compare and record only actual matched Numbers3 results."""
    now = (now or datetime.now(JST)).astimezone(JST)
    previous_secondary = load_records(root, "secondary")
    previous_verified = load_records(root, "verified")
    bank, rakuten = {}, {}
    errors = []
    for year, month in month_pairs(now, months_back):
        targets = (
            ("bank", f"{BANK}?year={year}&month={month}", "www.mizuhobank.co.jp", parse_bank, bank),
            ("rakuten", f"{RAKUTEN}{year}{month:02d}/", "takarakuji.rakuten.co.jp", parse_rakuten, rakuten),
        )
        for label, url, host, parse, dest in targets:
            try:
                page, digest = download(url, host, opener=opener)
                try:
                    rows = parse(page)
                except SourceError:
                    if not (label == "bank" and browser_fallback):
                        raise
                    page, digest = browser_bank(url)
                    rows = parse(page)
                for row in rows:
                    if row["draw_date"][:7] != f"{year:04d}-{month:02d}":
                        raise SourceError("publisher returned results from unexpected month")
                    existing = dest.get(row["round"])
                    if existing and any(existing[k] != row[k] for k in
                                        ("round", "draw_date", "winning_number")):
                        raise SourceError("publisher internal month overlap conflict")
                    dest[row["round"]] = {**row, "url": url, "sha256": digest}
            except (SourceError, ValueError) as exc:
                errors.append({"publisher": label, "month": f"{year:04d}-{month:02d}",
                               "reason": str(exc)})
    for rnd in set(bank) & set(rakuten):
        b, r = bank[rnd], rakuten[rnd]
        if (b["draw_date"], b["winning_number"]) != (r["draw_date"], r["winning_number"]):
            raise SourceError("bank and Rakuten independently disagree for round " + str(rnd))
    now_release = now
    matched = []
    for rnd in sorted(set(bank) & set(rakuten)):
        b, r = bank[rnd], rakuten[rnd]
        # NEVER attach a bank verification to an outcome that has not happened.
        if now_release < datetime.fromisoformat(b["draw_date"] + "T18:30:00+09:00"):
            raise SourceError("bank result appears before plausible draw time")
        matched.append({
            "round": rnd, "draw_date": b["draw_date"],
            "winning_number": b["winning_number"],
            "verification": "bank_primary_rakuten_publication_match",
            "bank_url": b["url"], "rakuten_url": r["url"],
            "bank_sha256": b["sha256"], "rakuten_sha256": r["sha256"],
            "recorded_at_jst": now.isoformat(timespec="seconds"),
            "not_a_cryptographic_signature": True
        })
    secondary_rows = [
        {"round": k, "draw_date": r["draw_date"], "winning_number": r["winning_number"]}
        for k, r in sorted(rakuten.items())
    ]
    # Validate complete append-only prefixes before any write.
    combined_secondary = merge_history(previous_secondary, secondary_rows)
    combined_verified = merge_history(previous_verified, matched)
    for v in combined_verified:
        companion = next((r for r in combined_secondary if r["round"] == v["round"]), None)
        if companion and companion["winning_number"] != v["winning_number"]:
            raise SourceError("verified draw conflicts with stored research result")
    stamp = now.isoformat(timespec="seconds")
    if combined_secondary != previous_secondary:
        atomic_json(root / SECONDARY, {
            "product": "Numbers3", "status": "single_rakuten_publisher_not_officially_verified",
            "updated_at_jst": stamp, "rows": combined_secondary,
            "official_draw_verified": False, "training_scope": "retrospective_research_only",
        })
    if combined_verified != previous_verified:
        atomic_json(root / VERIFIED, {
            "product": "Numbers3", "status": "bank_primary_rakuten_publication_match",
            "updated_at_jst": stamp, "rows": combined_verified,
            "draws_verified_only_on_two_publisher_agreement": True,
        })
    result = {
        "product": "Numbers3", "checked_at_jst": stamp,
        "status": ("two_source_matches" if matched else
                   "secondary_only_not_officially_verified" if rakuten else
                   "sources_unavailable"),
        "bank_rows": len(bank), "rakuten_rows": len(rakuten),
        "matched_rows_seen": len(matched),
        "new_verified_rows": len(combined_verified) - len(previous_verified),
        "secondary_rows_available": len(combined_secondary),
        "verified_rows_available": len(combined_verified),
        "errors": errors, "production_model_promoted": False,
        "official_claim_requires_independent_matching": True
    }
    atomic_json(root / "research/last_source_audit.json", result)
    return result
