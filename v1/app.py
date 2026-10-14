"""Simple Meta Ad Library search + insights API.

Hybrid approach for India commercial competitor analysis:
- GET /search uses the official ads_archive API when META_ACCESS_TOKEN is set.
  Note: for IN commercial ads Meta returns creatives but no spend/impressions.
- POST /insights aggregates any ad list (official or NiksHacks scraper output).
- GET /nikshacks/run-info explains how to run the NiksHacks Apify actor for IN.
"""

import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from v1.normalize import active_ratio, normalize_record

GRAPH_VERSION = os.getenv("META_API_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}/ads_archive"

app = FastAPI(title="Meta Ad Library API (IN)", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search")
def search(
    query: str,
    country: str = "IN",
    limit: int = 10,
    active_status: str = "ALL",
) -> dict[str, Any]:
    """Search via the official Meta Ad Library API.

    Requires META_ACCESS_TOKEN env var. Works best for political/EU ads;
    for IN commercial ads expect creatives without spend/impressions.
    """
    token = os.getenv("META_ACCESS_TOKEN", "").strip()
    if not token:
        raise HTTPException(
            status_code=501,
            detail=(
                "META_ACCESS_TOKEN not set. "
                "Get a user token from Graph API Explorer, export it, "
                "then retry. For IN commercial creatives use the "
                "NiksHacks Apify actor (see /nikshacks/run-info)."
            ),
        )
    params = {
        "search_terms": query,
        "ad_reached_countries": country,
        "ad_active_status": active_status,
        "limit": min(max(limit, 1), 100),
        "fields": (
            "id,page_id,page_name,ad_creative_bodies,"
            "ad_snapshot_url,ad_delivery_start_time,"
            "ad_delivery_stop_time,impressions,spend"
        ),
        "access_token": token,
    }
    try:
        resp = httpx.get(GRAPH_BASE, params=params, timeout=30.0)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Graph request failed: {exc}") from exc
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
    data = resp.json()
    ads = data.get("data", [])
    return {"query": query, "country": country, "count": len(ads), "ads": ads}


class InsightsRequest(BaseModel):
    ads: list[dict[str, Any]] = Field(default_factory=list)


def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError):
            return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


@app.post("/insights")
def insights(req: InsightsRequest) -> dict[str, Any]:
    """Aggregate competitor insights from any ad list.

    Every record is normalized to schema v1 first, so official API,
    raw scraper, canonical, and sample shapes all work. Status is
    tri-state (active/inactive/unknown); the activity ratio only divides
    by known statuses and is null when none are known. Meta does not
    publish commercial spend/impressions, so insights are counts,
    activity, platforms, and recency — observed creative volume, never
    spend or performance.
    """
    normalized: list[dict[str, Any]] = []
    skipped = 0
    for ad in req.ads:
        rec, _ = normalize_record(ad if isinstance(ad, dict) else {}, source_type="mixed")
        if rec is None:
            skipped += 1
        else:
            normalized.append(rec)
    total = len(normalized)
    if total == 0:
        return {"total_ads": 0, "detail": "No usable ads provided.", "skipped": skipped}

    counts = Counter(r["status"] for r in normalized)
    pages = Counter(str(r.get("page_name") or "unknown") for r in normalized)
    platform_counts: Counter[str] = Counter()
    for r in normalized:
        for plat in r.get("platforms") or []:
            platform_counts[str(plat)] += 1

    starts = [_parse_date(r.get("start_utc")) for r in normalized]
    starts = [d for d in starts if d is not None]
    date_range = None
    if starts:
        date_range = {
            "earliest_start": min(starts).date().isoformat(),
            "latest_start": max(starts).date().isoformat(),
        }

    return {
        "scope": {
            "records": total,
            "skipped": skipped,
            "unknown_status": counts.get("unknown", 0),
            "coverage": "Observed sample only — not full account inventory. "
                        "Country fields record where ads were searched, not proven targeting.",
        },
        "total_ads": total,
        "active_ads": counts.get("active", 0),
        "inactive_ads": counts.get("inactive", 0),
        "unknown_status": counts.get("unknown", 0),
        "active_ratio": active_ratio(normalized),
        "top_pages": pages.most_common(5),
        "platforms": dict(platform_counts),
        "date_range": date_range,
        "note": "Commercial spend/impressions are not published by Meta; creative volume and longevity are observable signals, not performance.",
    }


@app.get("/coverage")
def coverage() -> dict[str, Any]:
    """Tested capability matrix: what each collection path actually returns.

    A token does NOT unlock Indian commercial competitor performance —
    the official API serves creatives without spend/impressions there.
    """
    return {
        "official_api_ads_archive": {
            "needs": "META_ACCESS_TOKEN + identity-verified developer account",
            "political_or_issue_ads": "Full detail incl. spend/impression ranges",
            "eu_targeted_ads": "Reach, targeting, payer data",
            "in_commercial_ads": "Creatives + page only; NO spend/impressions/targeting",
            "pagination": "Cursor paging supported; this service reads the first page",
        },
        "local_browser_scrape": {
            "needs": "Node 20+, Playwright Chromium, no token",
            "in_commercial_ads": "Creatives, copy, CTA, landing URL, video/image URLs, start dates",
            "not_available": "Spend, impressions, targeting, engagement — never published",
            "caveats": "Meta serves HTTP 403 to headless browsers but still streams GraphQL; "
                       "blocking behavior can change without notice. Keep runs small.",
        },
    }


@app.get("/nikshacks/run-info")
def nikshacks_run_info(query: str = "Nike", country: str = "IN") -> dict[str, Any]:
    """Return a ready-to-use Apify input for the NiksHacks actor."""
    return {
        "actor_repo": "NiksHacks/meta-ads-library-scraper",
        "how_to_run": [
            "1. Push this repo as an Apify Actor (apify push) or import it in Apify Console.",
            "2. Set APIFY_TOKEN env var, then POST the input below to your actor run.",
            "3. Download the dataset; POST its ads to /insights.",
        ],
        "apify_input": {
            "searchQuery": query,
            "country": country,
            "adType": "ALL",
            "maxAds": 50,
            "includeInactive": True,
            "scrapeDetails": True,
            "enableGraphQLInterception": True,
            "useAdvancedStealth": True,
            "headlessMode": True,
            "outputFormat": "detailed",
        },
        "local_note": (
            "Local runs need Node 20+, `npm install`, Playwright Chromium, "
            "and ideally residential proxies — Meta blocks most datacenter IPs."
        ),
    }
