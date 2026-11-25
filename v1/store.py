"""SQLite store replacing JSON snapshot files (stdlib only).

Tables mirror the Postgres design from the build plan (brands, runs, ads,
status_history, diffs) so a later move to Postgres + Alembic is a driver
swap, not a redesign. Default database lives at ``snapshots/store.db``;
override with the ``DATABASE_URL`` env var (``sqlite:///path``).

Backfill replays existing ``snapshots/<brand>/YYYY-MM-DD.json`` files
oldest-first to reconstruct status history the old files never persisted.
"""

import json
import os
import sqlite3
import uuid
from datetime import date
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS brands (
    brand_id TEXT PRIMARY KEY,
    brand_name TEXT,
    country TEXT,
    search_query TEXT,
    alert_rules TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    brand_id TEXT NOT NULL REFERENCES brands(brand_id),
    day TEXT NOT NULL,
    payloads INTEGER DEFAULT 0,
    raw_records INTEGER DEFAULT 0,
    malformed INTEGER DEFAULT 0,
    unique_ads INTEGER DEFAULT 0,
    partial INTEGER DEFAULT 0,
    prev_run_id TEXT REFERENCES runs(id),
    UNIQUE (brand_id, day)
);
CREATE TABLE IF NOT EXISTS ads (
    ad_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    status TEXT,
    page_name TEXT,
    copy TEXT,
    destination_url TEXT,
    start_utc TEXT,
    platforms TEXT,
    media TEXT,
    raw TEXT,
    PRIMARY KEY (ad_id, run_id)
);
CREATE TABLE IF NOT EXISTS status_history (
    brand_id TEXT NOT NULL,
    ad_id TEXT NOT NULL,
    last_status TEXT,
    last_seen_day TEXT,
    absent_runs INTEGER DEFAULT 0,
    PRIMARY KEY (brand_id, ad_id)
);
CREATE TABLE IF NOT EXISTS diffs (
    run_id TEXT PRIMARY KEY REFERENCES runs(id),
    prev_run_id TEXT REFERENCES runs(id),
    new_ids TEXT,
    lost_ids TEXT,
    reactivated_ids TEXT,
    changed_ids TEXT,
    alerts TEXT,
    suppressed_lost INTEGER DEFAULT 0
);
"""


def db_path(database_url: str | None = None) -> str:
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///snapshots/store.db")
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    raise ValueError(f"Only sqlite:/// DATABASE_URLs are supported, got {url!r}")


def connect(database_url: str | None = None) -> sqlite3.Connection:
    path = db_path(database_url)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_brand(conn: sqlite3.Connection, brand: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO brands (brand_id, brand_name, country, search_query, alert_rules)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT (brand_id) DO UPDATE SET brand_name=excluded.brand_name,"
        " country=excluded.country, search_query=excluded.search_query,"
        " alert_rules=excluded.alert_rules",
        (
            brand["brand_id"],
            brand.get("brand_name"),
            brand.get("country"),
            (brand.get("search_queries") or [None])[0],
            json.dumps(brand.get("alert_rules", {})),
        ),
    )


def latest_run(conn: sqlite3.Connection, brand_id: str, day: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM runs WHERE brand_id = ? AND day < ? ORDER BY day DESC LIMIT 1",
        (brand_id, day),
    ).fetchone()
    return dict(row) if row else None


def save_run(
    conn: sqlite3.Connection,
    brand: dict[str, Any],
    day: str,
    ads: list[dict[str, Any]],
    diff: dict[str, list],
    alerts: list[str],
    payloads: int = 0,
    raw_records: int = 0,
    malformed: int = 0,
    partial: bool = False,
    suppressed_lost: bool = False,
) -> str:
    """Persist one brand-day run plus its ads, history and diff. Returns run id."""
    upsert_brand(conn, brand)
    prev = latest_run(conn, brand["brand_id"], day)
    run_id = uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO runs (id, brand_id, day, payloads, raw_records, malformed,"
        " unique_ads, partial, prev_run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (brand_id, day) DO UPDATE SET payloads=excluded.payloads,"
        " raw_records=excluded.raw_records, malformed=excluded.malformed,"
        " unique_ads=excluded.unique_ads, partial=excluded.partial",
        (run_id, brand["brand_id"], day, payloads, raw_records, malformed,
         len(ads), int(partial), prev["id"] if prev else None),
    )
    # Resolve the stored run id (re-runs of the same day keep the first id).
    row = conn.execute(
        "SELECT id FROM runs WHERE brand_id = ? AND day = ?", (brand["brand_id"], day)
    ).fetchone()
    run_id = row["id"]
    conn.execute("DELETE FROM ads WHERE run_id = ?", (run_id,))
    for ad in ads:
        conn.execute(
            "INSERT INTO ads (ad_id, run_id, status, page_name, copy,"
            " destination_url, start_utc, platforms, media, raw)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ad.get("ad_id"), run_id, ad.get("status"), ad.get("page_name"),
                ad.get("copy"), ad.get("destination_url"), ad.get("start_utc"),
                json.dumps(ad.get("platforms") or []),
                json.dumps(ad.get("media") or []),
                json.dumps(ad.get("raw") or {}),
            ),
        )
        seen = conn.execute(
            "SELECT absent_runs FROM status_history WHERE brand_id = ? AND ad_id = ?",
            (brand["brand_id"], ad.get("ad_id")),
        ).fetchone()
        conn.execute(
            "INSERT INTO status_history (brand_id, ad_id, last_status, last_seen_day,"
            " absent_runs) VALUES (?, ?, ?, ?, 0)"
            " ON CONFLICT (brand_id, ad_id) DO UPDATE SET last_status=excluded.last_status,"
            " last_seen_day=excluded.last_seen_day, absent_runs=0",
            (brand["brand_id"], ad.get("ad_id"), ad.get("status"), day),
        )
        _ = seen
    if prev:
        prev_ids = {r["ad_id"] for r in conn.execute(
            "SELECT ad_id FROM ads WHERE run_id = ?", (prev["id"],)).fetchall()}
        for missing in prev_ids - {a.get("ad_id") for a in ads}:
            conn.execute(
                "UPDATE status_history SET absent_runs = absent_runs + 1"
                " WHERE brand_id = ? AND ad_id = ?",
                (brand["brand_id"], missing),
            )
    conn.execute(
        "INSERT INTO diffs (run_id, prev_run_id, new_ids, lost_ids, reactivated_ids,"
        " changed_ids, alerts, suppressed_lost) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (run_id) DO UPDATE SET prev_run_id=excluded.prev_run_id,"
        " new_ids=excluded.new_ids, lost_ids=excluded.lost_ids,"
        " reactivated_ids=excluded.reactivated_ids, changed_ids=excluded.changed_ids,"
        " alerts=excluded.alerts, suppressed_lost=excluded.suppressed_lost",
        (
            run_id, prev["id"] if prev else None,
            json.dumps(diff.get("new", [])), json.dumps(diff.get("lost", [])),
            json.dumps(diff.get("reactivated", [])),
            json.dumps(diff.get("changed_creative_or_url", [])),
            json.dumps(alerts), int(suppressed_lost),
        ),
    )
    conn.commit()
    return run_id


def backfill_snapshots(
    conn: sqlite3.Connection, brand: dict[str, Any], snapshots_dir: str
) -> int:
    """Replay JSON snapshot files oldest-first into the store. Returns run count."""
    from v1.daily_check import diff_snapshots, is_run_complete

    brand_dir = os.path.join(snapshots_dir, brand["brand_id"])
    if not os.path.isdir(brand_dir):
        return 0
    files = sorted(f for f in os.listdir(brand_dir) if f.endswith(".json"))
    count = 0
    for filename in files:
        day = filename[:10]
        with open(os.path.join(brand_dir, filename)) as f:
            snap = json.load(f)
        ads = snap.get("ads", [])
        prev = latest_run(conn, brand["brand_id"], day + "\uffff")
        # Only backfill days not already stored.
        existing = conn.execute(
            "SELECT id FROM runs WHERE brand_id = ? AND day = ?",
            (brand["brand_id"], day),
        ).fetchone()
        if existing:
            continue
        prev_ads: list[dict[str, Any]] = []
        history: dict[str, Any] = {}
        if prev:
            prev_ads = [dict(r) for r in conn.execute(
                "SELECT ad_id, status, copy, destination_url FROM ads WHERE run_id = ?",
                (prev["id"],))]
            history = {r["ad_id"]: r["last_status"] for r in conn.execute(
                "SELECT ad_id, last_status FROM status_history WHERE brand_id = ?",
                (brand["brand_id"],))}
        diff = diff_snapshots(prev_ads, ads, status_history=history) if prev else {
            "new": [], "lost": [], "reactivated": [], "changed_creative_or_url": []}
        complete = is_run_complete(len(ads), len(prev_ads)) if prev else True
        save_run(conn, brand, day, ads, diff,
                 ["backfilled; no baseline"] if not prev else [],
                 payloads=snap.get("payloads", 0),
                 raw_records=snap.get("raw_records", 0),
                 malformed=snap.get("malformed", 0),
                 partial=not complete, suppressed_lost=bool(prev) and not complete)
        count += 1
    return count


def today_str() -> str:
    return date.today().isoformat()
