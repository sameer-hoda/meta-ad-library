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


def diff_snapshots(old_ads, new_ads):
    old = {a["ad_id"]: a for a in old_ads}
    new = {a["ad_id"]: a for a in new_ads}
    new_ids = [i for i in new if i not in old]
    lost_ids = [i for i in old if i not in new]
    reactivated = [i for i in new_ids if new[i].get("status") == ACTIVE
                   and old.get(i, {}).get("status") == INACTIVE]
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
    ads = normalize_all(payloads, brand["country"])
    prev_day, prev = previous_snapshot(snapshots_dir, brand["brand_id"], day)
    snap = {"brand_id": brand["brand_id"], "day": day,
            "query": brand["search_queries"][0], "country": brand["country"],
            "ads": ads}
    with open(snapshot_path(snapshots_dir, brand["brand_id"], day), "w") as f:
        json.dump(snap, f, ensure_ascii=False, default=str)
    result = {"brand": brand["brand_id"], "day": day, "ads": len(ads),
              "previous_day": prev_day, "diff": None, "alerts": [],
              "partial": False}
    if prev is None:
        result["alerts"].append("first snapshot stored; no baseline yet")
        return result
    diff = diff_snapshots(prev.get("ads", []), ads)
    result["diff"] = {k: len(v) for k, v in diff.items()}
    rules = brand.get("alert_rules", {})
    if len(diff["new"]) >= rules.get("new_launch_cluster", 3):
        result["alerts"].append(f"launch cluster: {len(diff['new'])} new ads in one day")
    elif diff["new"]:
        result["alerts"].append(f"{len(diff['new'])} new ad(s)")
    if diff["reactivated"] and rules.get("reactivation"):
        result["alerts"].append(f"{len(diff['reactivated'])} reactivated ad(s)")
    if diff["lost"]:
        result["alerts"].append(f"{len(diff['lost'])} no longer observed "
                                "(disappearance is not proof of a pause)")
    if diff["changed_creative_or_url"]:
        result["alerts"].append(f"{len(diff['changed_creative_or_url'])} ad(s) changed copy/URL")
    return result


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
