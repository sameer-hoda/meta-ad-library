"""P0 regression tests: schema, status, dates, dedupe, sample adapter.

Run:  python -m unittest v1.test_normalize -v   (from repo root)
"""

import json
import unittest

from v1.normalize import (
    ACTIVE,
    INACTIVE,
    SCHEMA_VERSION,
    UNKNOWN,
    active_ratio,
    normalize_record,
    parse_date_utc,
    parse_status,
)
from v1.parse_ads import extract_collated

SCRAPER_RAW = {
    "ad_archive_id": "2127168801471114",
    "page_id": "269617286730030",
    "page_name": "Meesho",
    "is_active": True,
    "start_date": 1790146800,
    "publisher_platform": ["FACEBOOK", "INSTAGRAM"],
    "spend": None,
    "snapshot": {
        "body": {"text": "Link in bio"},
        "title": "T",
        "cta_text": "Shop now",
        "link_url": "https://example.com/p",
        "images": [{"original_image_url": "https://img/x.jpg"}],
        "videos": [{"video_hd_url": "https://vid/x.mp4"}],
    },
}

OFFICIAL_RAW = {
    "id": "111",
    "page_id": "222",
    "page_name": "Brand",
    "ad_creative_bodies": [{"body": "Hello world"}],
    "ad_delivery_start_time": "2026-09-01T00:00:00+00:00",
    "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=111",
}

SAMPLE_RAW = {
    "id": "1465000198804887",
    "start": 1790406000,
    "link": "https://thestack.club/products/x",
    "title": "Pure Magnesium",
    "body": "Some copy",
    "platforms": ["Facebook"],
}


class TestStatus(unittest.TestCase):
    def test_strict_tristate(self):
        self.assertEqual(parse_status(True), ACTIVE)
        self.assertEqual(parse_status(False), INACTIVE)
        self.assertEqual(parse_status("false"), INACTIVE)  # string is not truthy
        self.assertEqual(parse_status("True"), ACTIVE)
        self.assertEqual(parse_status(1), ACTIVE)
        self.assertEqual(parse_status(0), INACTIVE)
        for ambiguous in (None, "", "maybe", [], {}):
            self.assertEqual(parse_status(ambiguous), UNKNOWN)


class TestDates(unittest.TestCase):
    def test_epoch_is_utc_aware(self):
        out = parse_date_utc(1790146800)
        self.assertTrue(out.endswith("+00:00"))
        self.assertIn("2026", out)
    def test_naive_iso_assumed_utc(self):
        self.assertTrue(parse_date_utc("2026-09-01").endswith("+00:00"))
    def test_invalid_is_none(self):
        for bad in (None, "", "not-a-date", False, 10**20):
            self.assertIsNone(parse_date_utc(bad))


class TestNormalize(unittest.TestCase):
    def test_scraper_shape(self):
        rec, reason = normalize_record(dict(SCRAPER_RAW), source_type="scraper",
                                       country_searched="IN")
        self.assertIsNone(reason)
        self.assertEqual(rec["schema_version"], SCHEMA_VERSION)
        self.assertEqual(rec["ad_id"], "2127168801471114")
        self.assertEqual(rec["status"], ACTIVE)
        self.assertEqual(rec["platforms"], ["FACEBOOK", "INSTAGRAM"])
        self.assertTrue(rec["start_utc"].endswith("+00:00"))
        self.assertEqual(rec["country_searched"], "IN")
        self.assertEqual(len(rec["media"]), 2)
        self.assertEqual(rec["copy"], "Link in bio")

    def test_official_shape(self):
        rec, _ = normalize_record(dict(OFFICIAL_RAW), source_type="official")
        self.assertEqual(rec["ad_id"], "111")
        self.assertEqual(rec["copy"], "Hello world")
        self.assertEqual(rec["status"], UNKNOWN)  # no status field -> unknown, not inactive

    def test_sample_shape_adapter(self):
        rec, _ = normalize_record(dict(SAMPLE_RAW), source_type="sample")
        self.assertEqual(rec["ad_id"], "1465000198804887")
        self.assertEqual(rec["destination_url"], "https://thestack.club/products/x")
        self.assertEqual(rec["headline"], "Pure Magnesium")
        self.assertEqual(rec["status"], UNKNOWN)

    def test_missing_id_skipped(self):
        rec, reason = normalize_record({"page_name": "X"})
        self.assertIsNone(rec)
        self.assertEqual(reason, "missing_ad_id")

    def test_canonical_passthrough(self):
        rec, _ = normalize_record(dict(SCRAPER_RAW))
        rec2, reason2 = normalize_record(rec)
        self.assertIsNone(reason2)
        self.assertEqual(rec2["ad_id"], rec["ad_id"])
        self.assertEqual(rec2["start_utc"], rec["start_utc"])


class TestRatio(unittest.TestCase):
    def test_unknown_only_is_none(self):
        recs = [{"status": UNKNOWN}, {"status": UNKNOWN}]
        self.assertIsNone(active_ratio(recs))
        self.assertIsNone(active_ratio([]))

    def test_divides_by_known_only(self):
        recs = [{"status": ACTIVE}, {"status": INACTIVE}, {"status": UNKNOWN}]
        self.assertEqual(active_ratio(recs), 0.5)


class TestExtract(unittest.TestCase):
    def test_collated_path_and_malformed_counted(self):
        payloads = [
            json.dumps({"data": {"ad_library_main": {"search_results_connection": {
                "edges": [{"node": {"collated_results": [SCRAPER_RAW, "junk"]}}]}}}}),
            "not json at all",
        ]
        records, malformed = extract_collated(payloads)
        self.assertEqual(len(records), 1)
        self.assertEqual(malformed, 2)


if __name__ == "__main__":
    unittest.main()
