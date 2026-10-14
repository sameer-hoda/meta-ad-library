"""Decode intercepted GraphQL payloads into normalized ad records.

Usage:
    python -m v1.parse_ads RAW_JSON [--country IN] [--source scraper] [--out OUT]

RAW_JSON is the list of GraphQL response bodies saved by v1/local_scrape.js.
Extracts search_results_connection.edges[].node.collated_results[],
normalizes each record (see v1/normalize.py), dedupes by ad id, and writes
JSON. Prints a collection-health summary; a capped scrape is reported as
partial, never as full inventory.
"""

import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone

from v1.normalize import (
    ACTIVE,
    INACTIVE,
    UNKNOWN,
    normalize_record,
)


def extract_collated(payloads: list) -> tuple[list[dict], int]:
    records, malformed = [], 0
    for body in payloads:
        try:
            data = json.loads(body) if isinstance(body, str) else body
            edges = data["data"]["ad_library_main"]["search_results_connection"]["edges"]
        except (ValueError, KeyError, TypeError):
            malformed += 1
            continue
        for edge in edges or []:
            node = (edge or {}).get("node") or {}
            for result in node.get("collated_results") or []:
                if isinstance(result, dict):
                    records.append(result)
                else:
                    malformed += 1
    return records, malformed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_json", help="Raw payload list saved by local_scrape.js")
    parser.add_argument("--country", default=None)
    parser.add_argument("--source", default="scraper")
    parser.add_argument("--out", default=None, help="Write normalized records here")
    parser.add_argument("--query", default=None, help="Search query used (recorded in health)")
    args = parser.parse_args(argv)

    run_id = uuid.uuid4().hex[:12]
    collected_at = datetime.now(timezone.utc).isoformat()
    payloads = json.load(open(args.raw_json))

    raw_records, malformed = extract_collated(payloads)
    normalized, seen, skipped = [], set(), Counter()
    for raw in raw_records:
        rec, reason = normalize_record(raw, source_type=args.source, country_searched=args.country)
        if rec is None:
            skipped[reason or "unknown"] += 1
            continue
        if rec["ad_id"] in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(rec["ad_id"])
        normalized.append(rec)

    statuses = Counter(r["status"] for r in normalized)
    missing = {
        field: sum(1 for r in normalized if not r.get(field))
        for field in ("page_name", "start_utc", "copy", "destination_url", "platforms")
    }
    health = {
        "run_id": run_id,
        "collected_at": collected_at,
        "query": args.query,
        "country_searched": args.country,
        "source": args.source,
        "payloads": len(payloads),
        "raw_records": len(raw_records),
        "unique_ads": len(normalized),
        "active": statuses.get(ACTIVE, 0),
        "inactive": statuses.get(INACTIVE, 0),
        "unknown_status": statuses.get(UNKNOWN, 0),
        "malformed_or_skipped": malformed + sum(skipped.values()),
        "skip_reasons": dict(skipped),
        "missing_field_counts": missing,
        "partial": True,
        "note": "Capped local scrape: observed sample only, not full account inventory.",
    }
    output = {"health": health, "ads": normalized}
    if args.out:
        json.dump(output, open(args.out, "w"), indent=1, ensure_ascii=False, default=str)
    print(json.dumps(health, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
