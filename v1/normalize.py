"""Canonical ad schema + normalization (schema v1).

Raw records arrive in three shapes: official Graph API (`id`, `page_name`,
`ad_delivery_start_time`, ...), raw scraper GraphQL (`ad_archive_id`,
`page_name`, `start_date` epoch, `publisher_platform` singular list, ...),
and the hand-built sample shape (`id`, `start`, `link`, `title`, `body`).
This module maps all three onto one versioned record. Missing data stays
unknown (None / "unknown") — never zero, never invented.
"""

from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA_VERSION = 1

CANONICAL_FIELDS = [
    "schema_version", "ad_id", "page_id", "page_name", "source_url",
    "source_type", "country_searched", "start_utc", "stop_utc", "status",
    "platforms", "copy", "headline", "description", "cta",
    "destination_url", "media", "raw",
]

ACTIVE = "active"
INACTIVE = "inactive"
UNKNOWN = "unknown"


def _first(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(d, dict) and d.get(key) is not None:
            return d[key]
    return default


def parse_status(value: Any) -> str:
    """Strict tri-state parse. Anything ambiguous -> unknown.

    In particular the string "false" is inactive, not truthy.
    """
    if value is True or value == 1:
        return ACTIVE
    if value is False or value == 0:
        return INACTIVE
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "active", "yes", "1"):
            return ACTIVE
        if low in ("false", "inactive", "no", "0"):
            return INACTIVE
    return UNKNOWN


def parse_date_utc(value: Any) -> Optional[str]:
    """Epoch or ISO input -> ISO UTC string. Invalid/missing -> None.

    Naive datetimes are assumed UTC (source gives no offset); the output
    is always timezone-aware. Source launch date only — collection time
    is recorded separately in run health.
    """
    if value is None or value is False:
        return None
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        text = str(value).strip()
        if not text:
            return None
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def parse_platforms(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(p) for p in value if p is not None]
    except TypeError:
        return []


def _snapshot_media(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    media: list[dict[str, str]] = []
    if not isinstance(snapshot, dict):
        return media
    for img in snapshot.get("images") or []:
        url = _first(img, "original_image_url", "resized_image_url", default=None)
        if url:
            media.append({"type": "image", "url": str(url)})
    for vid in snapshot.get("videos") or []:
        url = _first(vid, "video_hd_url", "video_sd_url", default=None)
        if url:
            media.append({"type": "video", "url": str(url)})
    return media


def normalize_record(
    raw: dict[str, Any],
    source_type: str = "scraper",
    country_searched: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Map one raw record to the canonical schema.

    Returns (record, None) on success or (None, skip_reason). Records
    without any usable ad id are skipped, never zero-filled.
    """
    if not isinstance(raw, dict):
        return None, "not_a_dict"
    if raw.get("schema_version") == SCHEMA_VERSION and raw.get("ad_id"):
        record = dict(raw)
        record["status"] = parse_status(raw.get("status"))
        record["platforms"] = parse_platforms(raw.get("platforms"))
        return record, None
    snap = raw.get("snapshot")
    if not isinstance(snap, dict):
        snap = {}

    ad_id = _first(raw, "ad_archive_id", "adId", "ad_id", "id", default=None)
    if ad_id is None or (isinstance(ad_id, str) and not ad_id.strip()):
        return None, "missing_ad_id"

    bodies = _first(raw, "ad_creative_bodies", default=None)
    if isinstance(bodies, list):
        copy_text = " ".join(str(b.get("body", "")) for b in bodies if isinstance(b, dict))
    else:
        copy_text = _first(raw, "copy", "body", default=None)
    if copy_text is None:
        copy_text = _first(snap.get("body", {}), "text", default=None)

    record = {
        "schema_version": SCHEMA_VERSION,
        "ad_id": str(ad_id),
        "page_id": _first(raw, "page_id", "pageId", default=None),
        "page_name": _first(raw, "page_name", "pageName", default=None),
        "source_url": _first(raw, "ad_snapshot_url", default=None),
        "source_type": source_type,
        "country_searched": country_searched or _first(raw, "country_searched", default=None),
        "start_utc": parse_date_utc(_first(raw, "start_date", "startDate", "start",
                                            "ad_delivery_start_time", default=None)),
        "stop_utc": parse_date_utc(_first(raw, "end_date", "endDate", "end",
                                           "ad_delivery_stop_time", default=None)),
        "status": parse_status(_first(raw, "is_active", "isActive", "is_active_str", default=None)),
        "platforms": parse_platforms(_first(raw, "publisher_platform", "platforms",
                                             "publisher_platforms", default=[])),
        "copy": copy_text,
        "headline": _first(raw, "headline", "title", default=None) or snap.get("title"),
        "description": _first(raw, "link_description", default=None) or snap.get("link_description"),
        "cta": _first(raw, "cta_text", default=None) or snap.get("cta_text"),
        "destination_url": _first(raw, "destination_url", "link", "link_url", default=None) or snap.get("link_url"),
        "media": _snapshot_media(snap),
        "raw": raw,
    }
    # Country searched is where we looked, not proven targeting.
    return record, None


def active_ratio(records: list[dict[str, Any]]) -> Optional[float]:
    """active / (active + inactive). None when no known statuses."""
    known = [r for r in records if r.get("status") in (ACTIVE, INACTIVE)]
    if not known:
        return None
    active = sum(1 for r in known if r["status"] == ACTIVE)
    return round(active / len(known), 3)
