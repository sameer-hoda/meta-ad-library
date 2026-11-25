"""Robustness + digest + store tests.

Run:  python -m unittest v1.test_robustness -v   (from repo root)
"""

import json
import os
import tempfile
import unittest

from v1.digest import brand_rollup, build_digest, render_digest_html
from v1.normalize import ACTIVE, INACTIVE, SCHEMA_VERSION
from v1.parse_ads import EXPECTED_PATH, EXPECTED_SHAPE, extract_collated


class TestShapeGuard(unittest.TestCase):
    def test_expected_shape_versioned(self):
        self.assertEqual(EXPECTED_SHAPE, 1)
        self.assertIn("search_results_connection", EXPECTED_PATH)

    def test_renamed_path_counts_malformed(self):
        payloads = [json.dumps({"data": {"ad_library_main": {"renamed": {}}}})]
        records, malformed = extract_collated(payloads)
        self.assertEqual(records, [])
        self.assertEqual(malformed, 1)


class TestStore(unittest.TestCase):
    def test_save_and_backfill_roundtrip(self):
        from v1 import store as store_mod
        from v1.daily_check import diff_snapshots

        with tempfile.TemporaryDirectory() as tmp:
            db_url = "sqlite:///" + os.path.join(tmp, "store.db")
            conn = store_mod.connect(db_url)
            brand = {"brand_id": "b", "brand_name": "B", "country": "IN",
                     "search_queries": ["B"], "alert_rules": {}}
            ads = [{"ad_id": "1", "status": ACTIVE, "page_name": "P",
                    "copy": "c", "destination_url": "https://e.example/",
                    "start_utc": None, "platforms": [], "media": [], "raw": {}}]
            diff = {"new": [], "lost": [], "reactivated": [],
                    "changed_creative_or_url": []}
            run_id = store_mod.save_run(conn, brand, "2026-10-20", ads, diff, [])
            self.assertTrue(run_id)
            latest = store_mod.latest_run(conn, "b", "2026-10-21")
            self.assertEqual(latest["day"], "2026-10-20")
            # Second day: ad goes inactive -> active history works via SQL rows.
            ads2 = [dict(ads[0], status=INACTIVE)]
            d2 = diff_snapshots(ads, ads2)
            self.assertEqual(d2["reactivated"], [])
            conn.close()


class TestDigest(unittest.TestCase):
    def test_digest_honesty_strings(self):
        brand = {"brand_id": "b", "brand_name": "B"}
        digest = build_digest(brand, "2026-10-26", [], [], {
            "new": [], "lost": [], "reactivated": [], "changed_creative_or_url": []},
            ["PARTIAL RUN — suppressed"], {"query": "B", "country": "IN"},
            partial=True)
        html_out = render_digest_html(digest, brand_rollup([], digest["diff"]))
        self.assertIn("PARTIAL RUN", html_out)
        self.assertIn("not performance proof", html_out)
        self.assertNotIn("ROAS", html_out)
        self.assertNotIn("shutdown", html_out)
        self.assertIn(".board", html_out)


class TestApp(unittest.TestCase):
    def test_health_and_ready_need_no_token(self):
        from fastapi.testclient import TestClient

        from v1.app import app

        client = TestClient(app, raise_server_exceptions=False)
        self.assertEqual(client.get("/health").json(), {"status": "ok"})
        body = client.get("/ready").json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["schema_version"], SCHEMA_VERSION)
        self.assertIn("token_configured", body)

    def test_search_without_token_is_501(self):
        from fastapi.testclient import TestClient

        from v1 import settings as settings_mod
        from v1.app import app

        old = settings_mod.settings.meta_access_token
        settings_mod.settings.meta_access_token = ""
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/search", params={"query": "x"})
            self.assertEqual(resp.status_code, 501)
        finally:
            settings_mod.settings.meta_access_token = old


if __name__ == "__main__":
    unittest.main()
