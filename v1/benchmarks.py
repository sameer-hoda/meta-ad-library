"""Same-scope category benchmarks from the store.

Compares only brands collected in the same country, period and depth,
and labels everything share-of-observed-activity — never market, spend
or impression share.
"""

import json
import sqlite3
from collections import Counter
from typing import Any


def benchmark_day(conn: sqlite3.Connection, day: str, country: str = "IN") -> dict[str, Any]:
    runs = conn.execute(
        "SELECT r.*, b.brand_name FROM runs r JOIN brands b ON b.brand_id = r.brand_id"
        " WHERE r.day = ? AND b.country = ?", (day, country)).fetchall()
    brands = []
    for run in runs:
        ads = conn.execute(
            "SELECT ad_id, status, platforms, media, copy FROM ads WHERE run_id = ?",
            (run["id"],)).fetchall()
        statuses = Counter(a["status"] for a in ads)
        formats = Counter("video" if '"video"' in (a["media"] or "") else "static"
                          for a in ads)
        diff = conn.execute(
            "SELECT new_ids FROM diffs WHERE run_id = ?", (run["id"],)).fetchone()
        new_7d = len(json.loads(diff["new_ids"])) if diff and diff["new_ids"] else 0
        brands.append({
            "brand_id": run["brand_id"],
            "brand_name": run["brand_name"],
            "ads_observed": len(ads),
            "active": statuses.get("active", 0),
            "inactive": statuses.get("inactive", 0),
            "unknown": statuses.get("unknown", 0),
            "new_today": new_7d,
            "format_mix": dict(formats),
            "partial": bool(run["partial"]),
        })
    return {
        "day": day,
        "country": country,
        "brands": brands,
        "coverage_gaps": [b["brand_id"] for b in brands if b["partial"]],
        "scope_stamp": ("Same country/day only; share of observed creative activity, "
                        "not market, spend or impression share."),
    }
