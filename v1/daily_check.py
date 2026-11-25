"""Daily watchlist check: scrape due brands, diff vs yesterday, print digest.

Usage:
    python -m v1.daily_check [--brand ID] [--no-scrape --raw FILE] [--snapshots DIR]

For each due brand: run the conservative local scrape, normalize via
parse_ads, persist a dated snapshot, and diff against the previous one.
New / lost / reactivated ads are reported; a failed or partial run is
flagged as unknown and NEVER treated as a competitor shutdown.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date

from v1.parse_ads import extract_collated
from v1.normalize import ACTIVE, INACTIVE, normalize_record

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_watchlist(path):
    with open(path) as f:
        return json.load(f).get("brands", [])


def snapshot_path(snapshots_dir, brand_id, day):
    d = os.path.join(snapshots_dir, brand_id)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{day}.json")


def previous_snapshot(snapshots_dir, brand_id, day):
    d = os.path.join(snapshots_dir, brand_id)
    if not os.path.isdir(d):
        return None, None
    prior = sorted(f for f in os.listdir(d) if f.endswith(".json") and f[:10] < day)
    if not prior:
        return None, None
    with open(os.path.join(d, prior[-1])) as f:
        return prior[-1][:10], json.load(f)


def run_scrape(query, country, raw_out):
    node_modules = os.path.join(REPO_ROOT, "third_party", "meta-ads-library-scraper", "node_modules")
    scraper = os.path.join(REPO_ROOT, "v1", "local_scrape.js")
    env = dict(os.environ, NODE_PATH=node_modules)
    proc = subprocess.run(
        ["node", scraper, query, country, raw_out],
        env=env, cwd=REPO_ROOT, capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"scraper failed: {proc.stderr[-500:]}")
    return raw_out


def normalize_all(payloads, country):
    raw_records, _ = extract_collated(payloads)
    ads, seen = [], set()
    for raw in raw_records:
        rec, _ = normalize_record(raw, source_type="scraper", country_searched=country)
        if rec is None or rec["ad_id"] in seen:
            continue
        seen.add(rec["ad_id"])
        ads.append(rec)
    return ads


def is_run_complete(new_count, prev_count, payloads=None, min_records=5,
                    ratio=0.5):
    """Decide whether a run loaded enough to trust 'lost' diffs.

    A half-loaded scroll must never manufacture a competitor shutdown:
    empty runs are always partial, and runs below both an absolute floor
    and a share of the previous baseline are partial too.
    """
    if new_count == 0:
        return False
    if prev_count >= 10 and new_count < max(min_records, ratio * prev_count):
        return False
    return True


def diff_snapshots(old_ads, new_ads, status_history=None):
    old = {a["ad_id"]: a for a in old_ads}
    new = {a["ad_id"]: a for a in new_ads}
    history = dict(status_history or {})
    for ad_id, rec in old.items():
        history.setdefault(ad_id, rec.get("status"))
    new_ids = [i for i in new if i not in old]
    lost_ids = [i for i in old if i not in new]
    reactivated = [
        i for i in set(old) & set(new)
        if old[i].get("status") == INACTIVE and new[i].get("status") == ACTIVE
    ]
    # Reappeared after a gap: absent last run, but history says it went
    # inactive before disappearing and it is active now.
    reactivated += [
        i for i in new_ids
        if new[i].get("status") == ACTIVE and history.get(i) == INACTIVE
        and i not in reactivated
    ]
    changed = [i for i in set(old) & set(new)
               if (old[i].get("copy"), old[i].get("destination_url"))
               != (new[i].get("copy"), new[i].get("destination_url"))]
    return {"new": new_ids, "lost": lost_ids, "reactivated": reactivated,
            "changed_creative_or_url": changed}


def check_brand(brand, snapshots_dir, raw_file=None):
    day = date.today().isoformat()
    if raw_file is None:
        raw_file = os.path.join("/tmp", f"watch_{brand['brand_id']}_{day}.json")
        run_scrape(brand["search_queries"][0], brand["country"], raw_file)
    payloads = json.load(open(raw_file))
    raw_records, malformed = extract_collated(payloads)
    ads = normalize_all(payloads, brand["country"])
    prev_day, prev = previous_snapshot(snapshots_dir, brand["brand_id"], day)
    prev_ads = (prev or {}).get("ads", [])
    history = dict((prev or {}).get("status_history", {}))
    for rec in prev_ads:
        history.setdefault(rec["ad_id"], rec.get("status"))
    for rec in ads:
        history[rec["ad_id"]] = rec.get("status")
    snap = {"brand_id": brand["brand_id"], "day": day,
            "query": brand["search_queries"][0], "country": brand["country"],
            "payloads": len(payloads), "raw_records": len(raw_records),
            "malformed": malformed,
            "status_history": history,
            "ads": ads}
    dest = snapshot_path(snapshots_dir, brand["brand_id"], day)
    tmp = dest + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snap, f, ensure_ascii=False, default=str)
    os.replace(tmp, dest)
    result = {"brand": brand["brand_id"], "day": day, "ads": len(ads),
              "previous_day": prev_day, "diff": None, "alerts": [],
              "payloads": len(payloads), "raw_records": len(raw_records),
              "partial": False}
    if payloads and not raw_records:
        result["alerts"].append("SHAPE ALERT: payloads loaded but the expected "
                                "search_results_connection path yielded zero "
                                "records — the scraper key path may have changed")
    if prev is None:
        result["alerts"].append("first snapshot stored; no baseline yet")
        _publish_run(brand, snapshots_dir, day, ads,
                     {"new": [], "lost": [], "reactivated": [],
                      "changed_creative_or_url": []},
                     result, len(payloads), len(raw_records), malformed, False)
        return result
    complete = is_run_complete(len(ads), len(prev_ads), payloads=len(payloads))
    result["partial"] = not complete
    diff = diff_snapshots(prev_ads, ads,
                          status_history=(prev or {}).get("status_history"))
    result["diff"] = {k: len(v) for k, v in diff.items()}
    rules = brand.get("alert_rules", {})
    if len(diff["new"]) >= rules.get("new_launch_cluster", 3):
        result["alerts"].append(f"launch cluster: {len(diff['new'])} new ads in one day")
    elif diff["new"]:
        result["alerts"].append(f"{len(diff['new'])} new ad(s)")
    if diff["reactivated"] and rules.get("reactivation"):
        result["alerts"].append(f"{len(diff['reactivated'])} reactivated ad(s)")
    if complete:
        if diff["lost"]:
            result["alerts"].append(f"{len(diff['lost'])} no longer observed "
                                    "(disappearance is not proof of a pause)")
    else:
        result["alerts"].append("PARTIAL RUN — 'lost' diff suppressed, treat as "
                                "unknown, not as competitor dark")
    if diff["changed_creative_or_url"]:
        result["alerts"].append(f"{len(diff['changed_creative_or_url'])} ad(s) changed copy/URL")
    try:
        from v1.creative import build_hook_library, detect_offer_url_changes

        offer_url = detect_offer_url_changes(prev_ads, ads)
        if offer_url:
            result["alerts"].append(
                f"{len(offer_url)} offer/landing-page change(s) with before/after evidence")
        result["offer_url_changes"] = offer_url
        result["hooks"] = build_hook_library(ads)
    except Exception:
        pass
    _publish_run(brand, snapshots_dir, day, ads, diff, result,
                 len(payloads), len(raw_records), malformed, not complete)
    return result


def _publish_run(brand, snapshots_dir, day, ads, diff, result,
                 payloads, raw_records, malformed, partial):
    """Best-effort store save + digest HTML. Never fails the run."""
    try:
        from v1 import store as store_mod
        from v1.digest import brand_rollup, build_digest, render_digest_html

        conn = store_mod.connect()
        try:
            store_mod.save_run(
                conn, brand, day, ads, diff, result["alerts"],
                payloads=payloads, raw_records=raw_records,
                malformed=malformed, partial=partial,
                suppressed_lost=partial and bool(diff.get("lost")),
            )
        finally:
            conn.close()
        digest = build_digest(
            brand, day, ads, [], diff, result["alerts"],
            {"query": brand["search_queries"][0], "country": brand["country"],
             "payloads": payloads, "raw_records": raw_records,
             "malformed": malformed},
            partial=partial,
        )
        digest_html = render_digest_html(digest, brand_rollup(ads, diff))
        brand_dir = os.path.join(snapshots_dir, brand["brand_id"])
        with open(os.path.join(brand_dir, f"{day}.digest.html"), "w") as f:
            f.write(digest_html)
        result["digest_html"] = os.path.join(brand_dir, f"{day}.digest.html")
    except Exception as exc:  # store/digest are additive, never fatal
        result["alerts"].append(f"PUBLISH SKIPPED ({type(exc).__name__}): store/digest unavailable")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brand", default=None)
    parser.add_argument("--no-scrape", action="store_true")
    parser.add_argument("--raw", default=None, help="With --no-scrape: raw payload file")
    parser.add_argument("--snapshots", default=os.path.join(REPO_ROOT, "snapshots"))
    parser.add_argument("--watchlist", default=os.path.join(REPO_ROOT, "watchlist.json"))
    args = parser.parse_args(argv)

    results = []
    for brand in load_watchlist(args.watchlist):
        if args.brand and brand["brand_id"] != args.brand:
            continue
        try:
            if args.no_scrape:
                if not args.raw:
                    raise RuntimeError("--no-scrape needs --raw FILE")
                results.append(check_brand(brand, args.snapshots, raw_file=args.raw))
            else:
                results.append(check_brand(brand, args.snapshots))
        except Exception as exc:  # failed run -> unknown, never a shutdown signal
            results.append({"brand": brand["brand_id"], "error": str(exc)[:300],
                            "partial": True,
                            "alerts": ["RUN FAILED OR PARTIAL — treat as unknown, not as competitor dark"]})
    print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
