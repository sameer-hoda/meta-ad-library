"""Creative + benchmark tests.

Run:  python -m unittest v1.test_creative -v   (from repo root)
"""

import os
import tempfile
import unittest

from v1.creative import (
    build_hook_library,
    detect_offer_url_changes,
    extract_hook,
    extract_offer_tags,
)


def _ad(ad_id, copy="Pure Magnesium ₹999, 20% off today", url="https://e.example/a"):
    return {"ad_id": ad_id, "copy": copy, "headline": "H",
            "destination_url": url, "media": []}


class TestOfferTags(unittest.TestCase):
    def test_price_and_discount_found(self):
        tags = extract_offer_tags("Magnesium ₹999, 20% off today")
        self.assertEqual(tags["price"], "₹999")
        self.assertIn("20% off", tags["discount"])

    def test_missing_is_not_in_creative(self):
        tags = extract_offer_tags("Clean supplements, no hype")
        self.assertEqual(tags["price"], "not_in_creative")
        self.assertEqual(tags["discount"], "not_in_creative")


class TestHooks(unittest.TestCase):
    def test_hook_links_ad_and_quote(self):
        hook = extract_hook(_ad("1"))
        self.assertEqual(hook["ad_ids"], ["1"])
        self.assertTrue(hook["hook_text"])
        self.assertIn(hook["hook_type"],
                      ("proof", "authority", "contrarian", "confession", "expose"))
        self.assertNotEqual(hook.get("hook_type"), "hook rate")

    def test_library_covers_ads(self):
        lib = build_hook_library([_ad("1"), _ad("2")])
        self.assertEqual(len(lib), 2)


class TestOfferUrlChanges(unittest.TestCase):
    def test_url_change_detected_with_evidence(self):
        old = [_ad("1", url="https://e.example/old")]
        new = [_ad("1", url="https://e.example/new")]
        changes = detect_offer_url_changes(old, new)
        self.assertTrue(any(c["day_field"] == "destination_url" for c in changes))
        hit = next(c for c in changes if c["day_field"] == "destination_url")
        self.assertEqual(hit["before"], "https://e.example/old")

    def test_no_change_no_alert(self):
        self.assertEqual(detect_offer_url_changes([_ad("1")], [_ad("1")]), [])


class TestBenchmarks(unittest.TestCase):
    def test_same_scope_benchmark(self):
        from v1 import store as store_mod
        from v1.benchmarks import benchmark_day

        with tempfile.TemporaryDirectory() as tmp:
            conn = store_mod.connect("sqlite:///" + os.path.join(tmp, "s.db"))
            brand = {"brand_id": "b", "brand_name": "B", "country": "IN",
                     "search_queries": ["B"], "alert_rules": {}}
            ads = [dict(_ad("1"), status="active")]
            diff = {"new": ["1"], "lost": [], "reactivated": [],
                    "changed_creative_or_url": []}
            store_mod.save_run(conn, brand, "2026-10-26", ads, diff, [])
            bench = benchmark_day(conn, "2026-10-26", country="IN")
            self.assertEqual(len(bench["brands"]), 1)
            self.assertIn("share of observed", bench["scope_stamp"])
            self.assertNotIn("market share", bench["scope_stamp"])
            conn.close()


if __name__ == "__main__":
    unittest.main()
