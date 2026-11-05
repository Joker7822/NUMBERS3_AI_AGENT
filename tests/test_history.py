"""Offline Numbers3 full-history research parity and provenance constraints."""
from pathlib import Path
import json
import tempfile
import unittest
from datetime import datetime

from numbers3_agent.history import (
    parse_full_archive, extend, load_extended, URL, STATUS
)
from numbers3_agent.sources import JST, SourceError, atomic_json
from numbers3_agent.learning import run_replay

NOW = datetime(2026, 11, 5, 11, 0, tzinfo=JST)
ROWS = [
    (1, "1994-10-07", "191"),
    (2, "1994-10-14", "988"),
    (3, "1994-10-21", "194"),
    (4, "1994-10-28", "105"),
    (5, "1994-11-04", "592"),
]

def api(rows=ROWS):
    return json.dumps([
        {"draw_no": rnd, "draw_date": day,
         "result": {"values": list(map(int,number)), "display": number}}
        for rnd,day,number in rows
    ]).encode()

def prepare(root):
    atomic_json(root / "data/secondary_history.json", {
        "product": "Numbers3",
        "status": "single_rakuten_publisher_not_officially_verified",
        "rows": [
            {"round": rnd, "draw_date": day, "winning_number": number}
            for rnd,day,number in ROWS[-3:]
        ],
        "official_draw_verified": False,
    })

class SecondaryFullHistoryTests(unittest.TestCase):
    def test_archive_game_identity_and_leading_zeros(self):
        data = parse_full_archive(api())
        self.assertEqual(len(data),5)
        altered=list(ROWS)
        altered[2]=(3,"1994-10-21","009")
        self.assertEqual(parse_full_archive(api(altered))[2]["winning_number"],"009")

    def test_requires_matching_rakuten_overlap_but_never_bank_verifies(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            prepare(root)
            result=extend(root,now=NOW,fetch=lambda:api())
            self.assertEqual(result["status"],
                             "extended_secondary_history_not_officially_verified")
            self.assertEqual(result["overlap_count"],3)
            self.assertFalse(result["official_bank_verified"])
            self.assertEqual(result["total_research_rows"],5)
            self.assertEqual(load_extended(root)[0]["round"],1)
            stored=json.loads((root/"data/secondary_extended.json").read_text())
            self.assertEqual(stored["status"],STATUS)
            self.assertFalse(stored["source_independence_proven"])
            report=run_replay(root,now=NOW)
            self.assertEqual(report["evaluated_draws"],4)
            self.assertEqual(report["data_scope"],STATUS)
            self.assertTrue(all(r["source_status"]==STATUS
                                for r in report["recent_rounds"]))
            self.assertFalse(report["officially_verified"])
            self.assertFalse(report["production_model_changed"])
            self.assertEqual(extend(root,now=NOW,fetch=lambda:api())["new_research_rows"],0)

    def test_never_silently_adopts_conflicting_numbers(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            prepare(root)
            original=list(ROWS)
            original[4]=(5,"1994-11-04","593")
            with self.assertRaisesRegex(SourceError,"disagree"):
                extend(root,now=NOW,fetch=lambda:api(original))
            self.assertFalse((root/"data/secondary_extended.json").exists())

    def test_missing_rounds_or_inconsistent_digit_array_rejected(self):
        altered=list(ROWS)
        altered[2]=(4,"1994-10-21","194")
        with self.assertRaisesRegex(SourceError,"continuous"):
            parse_full_archive(api(altered))
        doc=json.loads(api())
        doc[0]["result"]["values"]=[0,0,0]
        with self.assertRaisesRegex(SourceError,"digit array"):
            parse_full_archive(json.dumps(doc).encode())

    def test_network_unavailable_retains_existing_research(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            prepare(root)
            extend(root,now=NOW,fetch=lambda:api())
            before=(root/"data/secondary_extended.json").read_bytes()
            def unavailable():
                raise ConnectionError("offline")
            result=extend(root,now=NOW,fetch=unavailable)
            self.assertEqual(result["status"],
                             "secondary_archive_network_unavailable_preserved")
            self.assertEqual((root/"data/secondary_extended.json").read_bytes(),before)

    def test_no_rakuten_source_cannot_claim_full_history(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            result=extend(root,now=NOW,fetch=lambda:api())
            self.assertEqual(result["status"],
                             "no_rakuten_crosscheck_no_extension")
            self.assertFalse((root/"data/secondary_extended.json").exists())

if __name__=="__main__":
    unittest.main()
