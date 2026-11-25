"""Creative intelligence: offer tags, hook library, change detection.

Text-only (no media downloads): every tag links back to ad ids + quoted
evidence. Missing information is "not_in_creative", never invented.
ASR/OCR hookup (faster-whisper, PaddleOCR) plugs into the same shapes
via ``transcript_src`` — see the hook model below.
"""

import re
from typing import Any

PRICE_RE = re.compile(r"(₹\s?\d(?:[\d,]*\d)?|\bRs\.?\s?\d(?:[\d,]*\d)?|\bINR\s?\d(?:[\d,]*\d)?)", re.IGNORECASE)
DISCOUNT_RE = re.compile(r"(\d+\s?%\s?(off|discount|save))", re.IGNORECASE)
TRIAL_RE = re.compile(r"\b(trial|sample|starter)\b", re.IGNORECASE)
GUARANTEE_RE = re.compile(r"\b(guarantee|return|refund|money.?back)\b", re.IGNORECASE)
BUNDLE_RE = re.compile(r"\b(bundle|combo|pack of|buy \d|get \d)\b", re.IGNORECASE)
EXPIRY_RE = re.compile(r"\b(limited|ends|last day|hurry|offer ends)\b", re.IGNORECASE)
SHIPPING_RE = re.compile(r"\b(free (shipping|delivery)|cod|cash on delivery)\b", re.IGNORECASE)

HOOK_TYPES = ("proof", "authority", "contrarian", "confession", "expose")


def extract_offer_tags(copy: str | None) -> dict[str, Any]:
    """Visible offer signals from ad copy. Absent = not_in_creative."""
    text = copy or ""
    price = PRICE_RE.search(text)
    discount = DISCOUNT_RE.search(text)
    return {
        "price": price.group(0) if price else "not_in_creative",
        "discount": discount.group(0) if discount else "not_in_creative",
        "trial": bool(TRIAL_RE.search(text)),
        "guarantee_or_returns": bool(GUARANTEE_RE.search(text)),
        "bundle": bool(BUNDLE_RE.search(text)),
        "expiry": bool(EXPIRY_RE.search(text)),
        "shipping": bool(SHIPPING_RE.search(text)),
    }


def extract_hook(ad: dict[str, Any]) -> dict[str, Any]:
    """First-line hook + heuristic type. Type is a tag, never a hook rate."""
    copy = (ad.get("copy") or "").strip()
    first_line = next((ln.strip() for ln in copy.splitlines() if ln.strip()),
                      copy[:140]).strip()[:140]
    hook_text = first_line or (ad.get("headline") or "")[:140]
    low = hook_text.lower()
    if PRICE_RE.search(hook_text) or DISCOUNT_RE.search(hook_text) or "%" in hook_text:
        hook_type = "proof"
    elif any(w in low for w in ("doctor", "science", "clinical", "study", "expert")):
        hook_type = "authority"
    elif any(w in low for w in ("stop", "don't", "myth", "lie", "wrong")):
        hook_type = "contrarian"
    elif low.startswith("i ") or " my " in f" {low} ":
        hook_type = "confession"
    else:
        hook_type = "expose"
    media = ad.get("media") or []
    return {
        "hook_id": f"{ad.get('ad_id')}:0",
        "ad_ids": [ad.get("ad_id")],
        "hook_text": hook_text,
        "hook_type": hook_type,
        "transcript_src": "manual",
        "spoken_lang": "unknown",
        "caption_present": "unknown",
        "style": "video" if media and media[0].get("type") == "video" else "static",
        "evidence": {"quote": hook_text[:200]},
        "confidence": "low",
    }


def detect_offer_url_changes(
    old_ads: list[dict[str, Any]], new_ads: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per-ad destination_url + offer-tag changes with before/after evidence."""
    old = {a["ad_id"]: a for a in old_ads}
    changes = []
    for rec in new_ads:
        ad_id = rec["ad_id"]
        if ad_id not in old:
            continue
        if old[ad_id].get("destination_url") != rec.get("destination_url"):
            changes.append({
                "ad_id": ad_id, "day_field": "destination_url",
                "before": old[ad_id].get("destination_url"),
                "after": rec.get("destination_url"),
            })
        before_tags = extract_offer_tags(old[ad_id].get("copy"))
        after_tags = extract_offer_tags(rec.get("copy"))
        if before_tags != after_tags:
            changes.append({
                "ad_id": ad_id, "day_field": "offer_tags",
                "before": before_tags, "after": after_tags,
            })
    return changes


def build_hook_library(ads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One hook record per ad, searchable by type/style/text."""
    return [extract_hook(a) for a in ads if a.get("ad_id")]
