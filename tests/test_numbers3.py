"""Safe Numbers3 implementation regression tests: no internet required."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import tempfile
import unittest

from numbers3_agent.rules import (three_digits, validate_play, grade, odds, permutations)
from numbers3_agent.sources import (parse_bank, parse_rakuten, refresh, SourceError,
                                    load_records, month_pairs, merge_history, download, JST)
from numbers3_agent.learning import replay, uniform_ticket, run_replay
from numbers3_agent.issuance import issue, read_issued
from numbers3_agent.dashboard import write_dashboard
from numbers3_agent.research import discover

NOW = datetime(2026, 11, 5, 9, 50, tzinfo=JST)
BANK_HTML = '''<html><body><h1>ナンバーズ3</h1>
<div>回別 第7105回 抽せん日 2026年11月2日 抽せん数字 110</div>
<div>回別 第7106回 抽せん日 2026年11月3日 抽せん数字 753</div>
</body></html>'''
RAKUTEN_HTML = '''<html><body><h1>ナンバーズ3(NUMBERS3) 当せん番号案内</h1>
<div>回号 第7105回 抽せん日 2026/11/02 当せん番号 110</div>
<div>回号 第7106回 抽せん日 2026/11/03 当せん番号 753</div>
</body></html>'''

class FakeResponse:
    def __init__(self, url, raw):
        self.url = url
        self.raw = raw
        self.status = 200
        self.headers = self
    def get_content_charset(self): return "utf-8"
    def geturl(self): return self.url
    def read(self, n): return self.raw[:n]
    def __enter__(self): return self
    def __exit__(self, *args): return False

def mock_fetch(bank=BANK_HTML, rakuten=RAKUTEN_HTML):
    def opener(request, timeout=16):
        url = request.full_url
        if "mizuhobank.co.jp" in url:
            if bank is None: raise OSError("bank offline")
            return FakeResponse(url, bank.encode())
        if "takarakuji.rakuten.co.jp" in url:
            if rakuten is None: raise OSError("rakuten offline")
            return FakeResponse(url, rakuten.encode())
        raise AssertionError("unapproved URL")
    return opener

class Numbers3RulesTests(unittest.TestCase):
    def test_strict_digits_and_modes(self):
        self.assertEqual(three_digits("007"), "007")
        for bad in ("07", "0007", "a07", 7):
            with self.assertRaises(ValueError): three_digits(bad)
        self.assertEqual(validate_play("07", "mini")[0], "07")
        self.assertEqual(permutations("112"), 3)
        self.assertEqual(permutations("123"), 6)
        with self.assertRaises(ValueError): validate_play("111", "box")
        with self.assertRaises(ValueError): validate_play("111", "set")
        with self.assertRaises(ValueError): validate_play("007", "mini")

    def test_straight_box_set_mini_grades_and_odds(self):
        self.assertEqual(grade("007", "007", "straight"), "straight")
        self.assertEqual(grade("070", "007", "straight"), "miss")
        self.assertEqual(grade("070", "007", "box"), "box")
        self.assertEqual(grade("070", "007", "set"), "set_box")
        self.assertEqual(grade("007", "007", "set"), "set_straight")
        self.assertEqual(grade("07", "807", "mini"), "mini")
        self.assertEqual(grade("70", "807", "mini"), "miss")
        self.assertEqual(odds("007", "straight").any_win, .001)
        self.assertEqual(odds("07", "mini").any_win, .01)
        self.assertEqual(odds("012", "box").any_win, .006)

class SourceTests(unittest.TestCase):
    def test_two_independent_number3_sources(self):
        self.assertEqual([r["winning_number"] for r in parse_bank(BANK_HTML)],
                         ["110", "753"])
        self.assertEqual(parse_bank(BANK_HTML), parse_rakuten(RAKUTEN_HTML))
        self.assertEqual(month_pairs(NOW, 3), [(2026,11),(2026,10),(2026,9)])
        with self.assertRaises(SourceError):
            parse_bank(BANK_HTML.replace("ナンバーズ3", "ナンバーズ4"))
        with self.assertRaises(SourceError):
            parse_rakuten(RAKUTEN_HTML.replace("ナンバーズ3", "ナンバーズ4").replace("NUMBERS3","NUMBERS4"))

    def test_bank_plus_rakuten_only_verified_and_append_only(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            got = refresh(root, now=NOW, months_back=1, opener=mock_fetch())
            self.assertEqual(got["new_verified_rows"], 2)
            self.assertEqual(got["status"], "two_source_matches")
            self.assertEqual([r["winning_number"] for r in load_records(root,"verified")],
                             ["110", "753"])
            self.assertEqual(got["verified_rows_available"], 2)
            self.assertEqual(refresh(root, now=NOW, months_back=1, opener=mock_fetch())
                             ["new_verified_rows"], 0)
            corrupted = RAKUTEN_HTML.replace("753", "751")
            with self.assertRaisesRegex(SourceError, "disagree"):
                refresh(root, now=NOW, months_back=1,
                        opener=mock_fetch(rakuten=corrupted))
            self.assertEqual(load_records(root,"verified")[-1]["winning_number"], "753")

    def test_single_source_never_grades(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            report = refresh(root, now=NOW, months_back=1,
                             opener=mock_fetch(bank=None))
            self.assertEqual(report["status"], "secondary_only_not_officially_verified")
            self.assertEqual(load_records(root,"verified"), [])
            self.assertEqual(len(load_records(root,"secondary")), 2)
            learning = run_replay(root, now=NOW)
            self.assertEqual(learning["evaluated_draws"], 1)
            self.assertFalse(learning["prediction_skill_confirmed"])
            self.assertEqual(learning["recent_rounds"][0]["source_status"],
                             "single_rakuten_publisher_not_officially_verified")
            dashboard = write_dashboard(root, now=NOW)
            self.assertEqual(dashboard["verified_draws"], 0)
            self.assertEqual(dashboard["formally_graded_forecasts"], 0)
            self.assertEqual(dashboard["recent_week"]["research_straight_hits"],
                             learning["recent_rounds"][0]["research_hit"])

    def test_history_changes_and_invalid_numbers_are_rejected(self):
        previous = [{"round": 1, "draw_date": "1994-10-07", "winning_number": "001"}]
        with self.assertRaisesRegex(SourceError, "revised"):
            merge_history(previous, [
                {"round": 1, "draw_date": "1994-10-07", "winning_number": "009"}])
        with self.assertRaisesRegex(SourceError, "gap"):
            merge_history(previous, [
                {"round": 3, "draw_date": "1994-10-21", "winning_number": "123"}])
        with self.assertRaises(ValueError):
            parse_rakuten(RAKUTEN_HTML.replace("110", "1110"))
        with self.assertRaises(SourceError):
            download("http://evil.example/results", "evil.example")

    def test_no_future_bank_attestation(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(SourceError, "plausible draw time"):
                refresh(Path(t), now=datetime(2026,11,3,10,tzinfo=JST),
                        months_back=1, opener=mock_fetch())

class OnlineLearningTests(unittest.TestCase):
    def test_no_lookahead_when_future_outcome_changes(self):
        rows = [{"round": 7105+i,
                 "draw_date": (datetime(2026,11,2,tzinfo=JST)+timedelta(days=i)).date().isoformat(),
                 "winning_number": f"{(i * 37) % 1000:03d}"}
                for i in range(120)]
        before, grades = replay(rows)
        self.assertEqual(grades[0]["data_cutoff_round"], 7105)
        self.assertEqual(before["evaluated_draws"], 119)
        original = grades[-1]["research_number"]
        rows[-1]["winning_number"] = ("123" if rows[-1]["winning_number"]!="123" else "321")
        _, after = replay(rows)
        self.assertEqual(after[:-1], grades[:-1])
        self.assertEqual(after[-1]["research_number"], original)
        self.assertTrue(all(len(g["research_number"])==3 for g in grades))
        self.assertEqual(uniform_ticket(7107), uniform_ticket(7107))
        self.assertFalse(before["production_model_changed"])

    def test_empty_history_does_not_fabricate_predictions(self):
        result, grades = replay([])
        self.assertEqual(grades, [])
        self.assertIsNone(result["next_research_candidate"])
        self.assertFalse(result["prediction_skill_confirmed"])

class IssuanceTests(unittest.TestCase):
    def test_cannot_issue_without_official_history_or_after_deadline(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            with self.assertRaises(ValueError):
                issue(root,7107,"2026-11-04","007",
                      now=datetime(2026,11,4,10,tzinfo=JST))
            refresh(root,now=NOW,months_back=1,opener=mock_fetch())
            record = issue(root,7107,"2026-11-04","007",
                           now=datetime(2026,11,4,10,tzinfo=JST))
            self.assertFalse(record["publication_witnessed"])
            self.assertFalse(record["actual_purchase"])
            self.assertEqual(len(read_issued(root)),1)
            with self.assertRaises(ValueError):
                issue(root,7107,"2026-11-04","007",
                      now=datetime(2026,11,4,11,tzinfo=JST))
            with self.assertRaises(ValueError):
                issue(root,7108,"2026-11-04","007",
                      now=datetime(2026,11,4,19,tzinfo=JST))
            self.assertEqual(len(read_issued(root)),1)

class ResearchTests(unittest.TestCase):
    def test_research_is_never_automatic_production_upgrade(self):
        payload={"message":{"items":[
            {"DOI":"10.1000/xyz","title":["Proper Scoring Rules"]},
            {"DOI":"not-a-doi","title":["Discard"]}]}}
        report = discover(now=NOW, fetch=lambda url: json.dumps(payload).encode())
        self.assertEqual(report["sources_found"], 1)
        self.assertEqual(report["queries"], 2)
        self.assertFalse(report["external_code_executed"])
        self.assertFalse(report["search_results_changed_model_weights"])
        self.assertFalse(report["prediction_skill_confirmed"])

if __name__ == "__main__":
    unittest.main()
