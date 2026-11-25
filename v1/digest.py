"""Morning digest + survivor timelines (JSON + static HTML, no JS).

Builds on trusted diffs: partial runs suppress "lost", gaps stay unknown,
and longevity is labeled a signal, never performance proof.
"""

import html
from collections import Counter
from typing import Any

SCOPE_STAMP = (
    "Observed sample only — not full account inventory. "
    "Country fields record where ads were searched, not proven targeting."
)


def build_digest(
    brand: dict[str, Any],
    day: str,
    ads: list[dict[str, Any]],
    prev_ads: list[dict[str, Any]],
    diff: dict[str, list],
    alerts: list[str],
    scope: dict[str, Any],
    partial: bool = False,
) -> dict[str, Any]:
    return {
        "brand": brand.get("brand_id"),
        "brand_name": brand.get("brand_name"),
        "day": day,
        "ads_observed": len(ads),
        "previous_day_count": len(prev_ads),
        "partial": partial,
        "diff": {k: list(v) for k, v in diff.items()},
        "diff_counts": {k: len(v) for k, v in diff.items()},
        "alerts": list(alerts),
        "scope": {**scope, "limitations": SCOPE_STAMP},
    }


def compute_timelines(
    history: dict[str, dict[str, Any]], day: str
) -> dict[str, Any]:
    """Per-ad longevity from accumulated status history.

    ``history`` maps ad_id -> {"first_seen": day, "last_seen": day,
    "days_observed": n, "status": s}. Gaps stay unknown: an ad absent for
    a run keeps its last status, never "ended".
    """
    survivors = {
        ad_id: info for ad_id, info in history.items()
        if (info.get("days_observed") or 0) >= 30
    }
    return {
        "day": day,
        "ads_tracked": len(history),
        "survivors_30d": sorted(survivors),
        "details": history,
        "note": "Longevity is an observed signal, not proof of performance.",
    }


def brand_rollup(
    ads: list[dict[str, Any]], diff: dict[str, list]
) -> dict[str, Any]:
    formats = Counter("video" if (a.get("media") or [{}])[0].get("type") == "video"
                      else "image" for a in ads)
    return {
        "observed": len(ads),
        "new": len(diff.get("new", [])),
        "lost": len(diff.get("lost", [])),
        "reactivated": len(diff.get("reactivated", [])),
        "changed": len(diff.get("changed_creative_or_url", [])),
        "format_mix": dict(formats),
    }


_CSS = """
:root{--board:#fbfaf6;--ink:#1f2937;--muted:#6b7280;--blue:#1d4ed8;
--red:#c2410c;--green:#15803d;--line:#d6d3cc}
body{background:var(--board);color:var(--ink);font:14px/1.45 Inter,system-ui,sans-serif;margin:0}
.wrap{max-width:860px;margin:0 auto;padding:24px 16px}
h1{font-family:Caveat,cursive;font-size:44px;margin:0}
.sub{color:var(--muted);font-size:12px}
.board{background:#fff;border:2px solid var(--ink);border-radius:14px;padding:16px 18px;margin:18px 0}
.board h2{font-family:Caveat,cursive;font-size:32px;margin:0 0 8px}
.bignum{font-family:Georgia,serif;font-size:30px}
.tl{display:flex;gap:8px;list-style:none;padding:0}
.tl li{flex:1;text-align:center;font-size:12px;color:var(--muted)}
.dot{width:22px;height:22px;border-radius:50%;border:2px solid var(--ink);margin:0 auto 4px}
.hot{background:var(--red)}.quiet{border-style:dashed}
.row{display:grid;grid-template-columns:110px 1fr;gap:8px;align-items:center;margin:6px 0}
.bar{height:22px;border:2px solid var(--ink);border-radius:6px}
.b1{background:var(--blue)}.b2{background:var(--red)}.b3{background:var(--green)}
.ins{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.ins blockquote{border-left:4px solid var(--red);margin:0;padding:6px 10px;background:var(--board)}
.ins q{font-family:Caveat,cursive;font-size:22px}
.gaps{border:2px dashed var(--green);border-radius:10px;padding:10px 12px}
.muted{color:var(--muted);font-size:11px}
code{font-family:ui-monospace,monospace;font-size:12px}
@media(max-width:640px){.ins{grid-template-columns:1fr}.row{grid-template-columns:90px 1fr}.tl li{font-size:10px}}
"""


def render_digest_html(digest: dict[str, Any], rollup: dict[str, Any]) -> str:
    """Server-rendered digest page: whiteboard tokens, no JS, no external CSS."""
    e = html.escape
    counts = digest.get("diff_counts", {})
    alerts = "".join(f"<li>{e(a)}</li>" for a in digest.get("alerts", [])) or "<li>Quiet day.</li>"
    partial = "<p><strong>PARTIAL RUN</strong> — lost counts suppressed; treat as unknown.</p>" if digest.get("partial") else ""
    fmt = rollup.get("format_mix", {})
    total_fmt = sum(fmt.values()) or 1
    bars = "".join(
        f'<div class="row"><span>{e(k)}</span><div class="bar b1" style="width:{int(100*v/total_fmt)}%"></div></div>'
        for k, v in fmt.items()
    )
    scope = digest.get("scope", {})
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(str(digest.get('brand_name') or digest.get('brand')))} digest {e(str(digest.get('day')))}</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>{e(str(digest.get('brand_name') or ''))} — morning digest</h1>
<p class="sub">{e(str(digest.get('day')))} · {digest.get('ads_observed', 0)} ads observed ·
query {e(str(scope.get('query', '')))} · {e(str(scope.get('country', '')))}</p>
<div class="board"><h2>What changed</h2>{partial}
<p><span class="bignum">{counts.get('new', 0)}</span> new ·
<span class="bignum">{counts.get('lost', 0)}</span> no longer observed ·
<span class="bignum">{counts.get('reactivated', 0)}</span> reactivated ·
<span class="bignum">{counts.get('changed_creative_or_url', 0)}</span> changed</p>
<ul>{alerts}</ul></div>
<div class="board"><h2>Format mix</h2>{bars or '<p class="sub">No ads observed.</p>'}</div>
<div class="board"><h2>Scope &amp; limits</h2>
<p class="sub">{e(str(scope.get('limitations', SCOPE_STAMP)))}</p>
<p class="muted">Payloads {scope.get('payloads', '?')} · records {scope.get('raw_records', '?')} ·
malformed {scope.get('malformed', '?')}</p></div>
<p class="muted">Longevity and volume are observable signals, not performance proof.
Disappearance is not proof of a pause.</p>
</div></body></html>"""
