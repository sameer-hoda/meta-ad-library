"""Focused tests for daily_check diff trust fixes.

Run:  python -m unittest v1.test_daily_check -v   (from repo root)
"""

import unittest

from v1.daily_check import diff_snapshots, is_run_complete
from v1.normalize import ACTIVE, INACTIVE, UNKNOWN


def ad(ad_id, status=ACTIVE, copy="c", url="https://x.example/"):
    return {"ad_id": ad_id, "status": status, "copy": copy,
            "destination_url": url}


class TestReactivation(unittest.TestCase):
    def test_inactive_to_active_fires(self):
        old = [ad("1", INACTIVE)]
        new = [ad("1", ACTIVE)]
        diff = diff_snapshots(old, new)
        self.assertEqual(diff["reactivated"], ["1"])
        self.assertEqual(diff["new"], [])
        self.assertEqual(diff["lost"], [])

    def test_stays_active_is_not_reactivation(self):
        diff = diff_snapshots([ad("1", ACTIVE)], [ad("1", ACTIVE)])
        self.assertEqual(diff["reactivated"], [])

    def test_unknown_to_active_is_not_reactivation(self):
        diff = diff_snapshots([ad("1", UNKNOWN)], [ad("1", ACTIVE)])
        self.assertEqual(diff["reactivated"], [])

    def test_reappeared_after_gap_counts_via_history(self):
        # Ad seen inactive two runs ago, missing last run, back and active now.
        old = []
        new = [ad("9", ACTIVE)]
        history = {"9": INACTIVE}
        diff = diff_snapshots(old, new, status_history=history)
        self.assertEqual(diff["reactivated"], ["9"])


class TestCompletenessGate(unittest.TestCase):
    def test_half_loaded_run_is_partial(self):
        # 39 ads yesterday, only 12 today -> partial, lost must be suppressed.
        self.assertFalse(is_run_complete(new_count=12, prev_count=39))

    def test_normal_dip_is_complete(self):
        self.assertTrue(is_run_complete(new_count=36, prev_count=39))

    def test_first_run_with_ads_is_complete(self):
        self.assertTrue(is_run_complete(new_count=8, prev_count=0))

    def test_empty_run_is_partial(self):
        self.assertFalse(is_run_complete(new_count=0, prev_count=39))
        self.assertFalse(is_run_complete(new_count=0, prev_count=0,
                                         payloads=0))


if __name__ == "__main__":
    unittest.main()
