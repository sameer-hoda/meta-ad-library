# Meta Ad Library — Project Context & Robustness Guide

Reviewed: 2026-10-26. Repo revision at review: `main` @ `9377102`.
Remote: `https://github.com/sameer-hoda/meta-ad-library` (`origin/main`, clean tree).

## 1. What this project is

Search Meta's Ad Library through the official API, scrape Indian commercial ads
with a local headless browser (no Apify / paid proxies for small runs), normalize
everything into one versioned schema, and turn results into an HTML competitor report.

Design principles (from `ENHANCEMENTS.md` + code):
- Missing data stays **unknown, never zero**. No invented spend, reach, or targeting.
- Longevity / repetition are **observable signals, not performance proof**.
- Every report is stamped with **scope, collection time, coverage, limitations**.
- A failed or partial run is **unknown, never a competitor shutdown**.
- Country fields record **where ads were searched, not proven targeting**.

## 2. Repo map

| Path | Role |
|---|---|
| `v1/app.py` | FastAPI service: `/health`, `/search` (official API), `/insights` (aggregate any ad list), `/coverage` (capability matrix), `/nikshacks/run-info` (Apify input) |
| `v1/normalize.py` | Canonical schema v1 + tri-state status + UTC dates + 3-shape adapter |
| `v1/parse_ads.py` | CLI: GraphQL payloads → deduped normalized JSON + collection health |
| `v1/daily_check.py` | Watchlist runner: scrape → snapshot → diff new/lost/reactivated/changed |
| `v1/local_scrape.js` | Conservative Playwright scraper: ignores HTTP 403, intercepts GraphQL, 5 scrolls |
| `v1/test_normalize.py` | 12 regression tests (`python -m unittest v1.test_normalize`) |
| `v1/requirements.txt` | `fastapi`, `uvicorn`, `httpx`, `pydantic` only |
| `watchlist.json` | Tracked brands (today: 1 — The Stack Club, IN, daily) |
| `ENHANCEMENTS.md` | Build checklist + progress (P0 done, P1–P4 backlog) |
| `reports/stackclub/` | Sample: `index.html`, `by-product.html`, `whiteboard.html`, `ads_top10.json`, `assets/` (5 videos, images, frame strips) |
| `snapshots/the-stack-club/` | Daily snapshots `2026-10-15` → `2026-10-18` (git-ignored, local only) |
| `third_party/` | Git-ignored clone of `NiksHacks/meta-ads-library-scraper` (re-fetched per clone) |

## 3. Data flow

1. **Collect.** Either `GET /search` (official `ads_archive` Graph API, needs `META_ACCESS_TOKEN`)
   or `node v1/local_scrape.js "<Brand>" IN /tmp/ads_raw.json` (Playwright, intercepts
   `search_results_connection.edges[].node.collated_results[]`).
2. **Normalize.** `normalize_record()` maps official / scraper / sample shapes onto
   schema v1; records without any ad id are skipped with a reason.
3. **Parse / health.** `parse_ads` dedupes by ad id, counts malformed/skipped,
   and emits `health` (run id, collected-at, query/country, payloads, raw/unique counts,
   status breakdown, missing-field rates, `partial: true` always for capped scrapes).
4. **Aggregate.** `POST /insights` normalizes mixed shapes, returns counts, known-status-only
   `active_ratio`, top pages, platform mix, date range, scope/coverage stamps.
5. **Track.** `daily_check` scrapes due brands, persists dated snapshots, diffs vs previous,
   applies `alert_rules` (launch cluster ≥ N, reactivation, new URL), prints JSON digest.

## 4. Schema v1 contract (the load-bearing details)

Canonical fields: `schema_version, ad_id, page_id, page_name, source_url, source_type,
country_searched, start_utc, stop_utc, status, platforms, copy, headline, description,
cta, destination_url, media, raw`. Raw input is always retained alongside normalized data.

- **Status** is strict tri-state: `parse_status()` maps `True/1/"true"/"active"` → active,
  `False/0/"false"/"inactive"` → inactive, everything else → unknown. The `"false"`-string
  fix is intentional and tested — never treat it as truthy.
- **Dates** are UTC ISO strings: epoch or ISO in, `+00:00` out; naive assumed UTC;
  invalid/missing → `None`. Source launch date is kept separate from discovery time.
- **Platforms** accept singular `publisher_platform`, plural variants, or a bare string.
- **Media** comes from `snapshot.images[].original_image_url` and
  `snapshot.videos[].video_hd_url` (with SD/resized fallbacks).
- **Ratios** divide by known statuses only: `active / (active + inactive)`, `None` when none known.

## 5. Current state

- P0 (correctness) is done and tested: 12/12 green covering status, dates, all three shapes,
  id-missing skip, canonical passthrough, ratio denominators, collated extraction.
- Official-API coverage is **documented, not promised**: `/coverage` states a token does NOT
  unlock Indian commercial spend/impressions; IN commercial = creatives + page only.
- One brand tracked daily; 4 consecutive snapshots exist locally (Oct 15–18).
- No CI, no `CONTRIBUTING.md`, no issue/PR templates, no lint config, no pagination on
  `/search` (first page only), no retry/backoff, no rate limiting, sync `httpx.get` in API.

## 6. Observed fragilities (from reading the code)

1. **Scraper selectors-by-network-shape.** Intercepting `search_results_connection` payloads is
   more stable than parsing rendered HTML, but the deep key path
   `data.ad_library_main.search_results_connection.edges` is still a single point of failure
   if Meta renames it. No fallback path or shape-version log exists.
2. **Blocking drift.** The 403-tolerant trick + fixed UA + 5-scroll loop works today; Meta can
   change blocking without notice. No retry, proxy rotation, or run-abort-on-challenge logic.
3. **`diff_snapshots` reactivation bug.** `reactivated` is computed over `new_ids` (ads absent
   from old snapshot), then checks `old.get(i).status == inactive` — which can never be true
   for an id not in old. True reactivations (present→inactive→active across runs with status
   history) are therefore never reported.
4. **Sync outbound HTTP.** `/search` uses blocking `httpx.get` inside a sync route — fine at
   tiny scale, becomes a throughput bottleneck under concurrent use.
5. **No pagination.** `/search` reads only the first Graph API page; large result sets silently truncate.
6. **Bare `--no-scrape` coupling, no locking.** Concurrent `daily_check` runs can interleave
   snapshot writes; no atomic write or run lock.
7. **Snapshot comparison is id-presence only.** Disappearance conflates "ad ended" with
   "this scroll didn't load it" — the digest text warns about this, but the diff itself has
   no minimum-payload / completeness gate before emitting "lost" alerts.

## 7. Robustness playbook (external sources + mapping)

Scraper resilience:
- Prefer **network interception over DOM parsing** — DOM class names break first. This repo
  already does this; keep it and add a shape-version assertion + alert when the expected
  key path is absent ([resilient-scraper write-up](https://dev.to/milton_ngeno_c9aabd639087/building-a-resilient-meta-ads-scraper-what-breaks-and-what-i-learned-fixing-it-1li6)).
- Production Playwright separators are **browser-context isolation, request interception to
  cut waste, robust retries, per-context proxy rotation** ([Playwright harvesting walkthrough](https://compareproxyzone.com/pages/playwright-web-data-harvesting-a-step-by-step-walkthrough.html)).
  Map: add per-brand contexts, block images/fonts during scroll, exponential backoff with jitter,
  optional residential proxy env var (README already hints proxies are needed at scale).
- Realistic pacing (3–5s between actions, rotating sessions) is the difference between a
  script and a reliable job ([hook-pattern scraping notes](https://kenashe.ai/blog/2026-06-16-scraping-the-meta-ad-library-with-gpt-4-vision-to-reverse-engineer-hook-patterns/));
  `local_scrape.js` already scrolls conservatively — add jitter + abort on CAPTCHA/challenge.
- Use **locators + auto-wait, async concurrency, and network interception** as the 2026
  Playwright baseline ([2026 Playwright scraping tutorial](https://dev.to/agenthustler/playwright-web-scraping-tutorial-in-2026-javascript-rendered-pages-made-easy-35fc)).

API robustness:
- **Exempt `/health` (and `/ready`, `/metrics`) from rate limiting**, return `X-RateLimit-*`
  + `Retry-After` headers ([FastAPI rate-limiting guide](https://oneuptime.com/blog/post/2025-01-06-fastapi-rate-limiting/view)).
- Add **deep health/readiness** (dependency checks), not just `{"status": "ok"}`
  ([FastAPI health-check practices](https://www.index.dev/blog/how-to-implement-health-check-in-python)).
- Standard production set: **async routes, timeouts + retries with backoff/jitter on 429/5xx,
  request validation, paginated reads, structured logging** ([FastAPI best practices](https://mathison.ch/en-ch/blog/effizienz-freischalten-beherrschen-sie-fastapi-mit/),
  [rate-limit handling guide](https://dev.to/vhub_systems_ed5641f65d59/how-to-handle-api-rate-limits-before-they-break-your-production-integration-53fn)).
- Concrete next edits: `slowapi`/`fastapi-limiter` on `/search` + `/insights`; cursor pagination
  passthrough on `/search`; `httpx.AsyncClient` with 30s timeout + 3 retries; `/ready` endpoint.

Data correctness:
- Fix the reactivation computation (track status history per ad id across snapshots, not just
  id presence). Gate "lost" alerts on run completeness (min payloads/records threshold).
- Atomic snapshot writes (tmp + rename), run locks, JSON-schema validation of snapshots.

## 8. Making the project effective & contributive

What healthy contributor-friendly repos share: an engaged owner, **README + developer guide +
  CONTRIBUTING that lets someone contribute without asking for help**, issue/PR templates,
  code of conduct, license (already MIT here), **high test coverage + linters + reliably
  passing CI** ([how to grow contributors](https://code.dblock.org/2024/12/14/how-to-grow-open-source-contributors-and-maintainers),
  [contributor-friendly essentials](https://beaulebens.com/2023/02/01/the-essentials-of-a-contributor-friendly-open-source-project/),
  [first-contribution guide](https://osssoftware.org/blog/your-first-open-source-contribution-guide/)).

Suggested additions, smallest-first:
1. `CONTRIBUTING.md` — setup (venv + Node/Playwright), how to run tests, style, PR steps;
   run the same checks CI runs before pushing ([step-by-step contribution norms](https://openresource.dev/guide/contributing/contributing-to-open-source)).
2. `.github/workflows/ci.yml` — `python -m unittest`, `node --check`, (later) `ruff`.
3. Issue templates (bug / new-brand request / data-quality) + PR template; `good first issue` labels.
4. `CODE_OF_CONDUCT.md` (Contributor Covenant), `SECURITY.md` (never commit `.env`/tokens).
5. Schema/data dictionary (`docs/SCHEMA.md`) + collection-limits doc (ToS caution, keep runs small).
6. `Makefile` (`make setup|test|scrape|report`) so the README quickstart is one command.
7. Roadmap issues cut from `ENHANCEMENTS.md` P1–P4 with acceptance criteria ("done when" lines).
8. Keep continuity cheap: **tests stay, contributors come and go** — every P1+ feature ships with
   a fixture test ([why tests matter for OSS continuity](https://turbaszek.medium.com/how-to-open-source-a-guide-for-new-contributors-and-maintainers-c37b8a802d9a)).

## 9. Suggested next steps (mapped to ENHANCEMENTS.md)

- **Correctness (P0 leftover):** fix `reactivated` logic; add completeness gate for "lost".
- **P1 dashboard:** inventory + dedupe + age buckets + evidence-first output, all fixture-tested.
- **P2 history:** status-history store, launch velocity / refresh rate, change reports.
- **Robustness track (new):** retries, rate limits, pagination, async HTTP, atomic snapshots.
- **Community track (new):** CONTRIBUTING + CI + templates + docs, then label `good first issues`.

## Sources

- Resilient Meta ads scraper: [DEV write-up](https://dev.to/milton_ngeno_c9aabd639087/building-a-resilient-meta-ads-scraper-what-breaks-and-what-i-learned-fixing-it-1li6)
- Playwright reliability: [harvesting walkthrough](https://compareproxyzone.com/pages/playwright-web-data-harvesting-a-step-by-step-walkthrough.html) ·
  [2026 tutorial](https://dev.to/agenthustler/playwright-web-scraping-tutorial-in-2026-javascript-rendered-pages-made-easy-35fc) ·
  [pacing notes](https://kenashe.ai/blog/2026-06-16-scraping-the-meta-ad-library-with-gpt-4-vision-to-reverse-engineer-hook-patterns/)
- FastAPI robustness: [rate limiting](https://oneuptime.com/blog/post/2025-01-06-fastapi-rate-limiting/view) ·
  [health checks](https://www.index.dev/blog/how-to-implement-health-check-in-python) ·
  [best practices](https://mathison.ch/en-ch/blog/effizienz-freischalten-beherrschen-sie-fastapi-mit/) ·
  [rate-limit failures](https://dev.to/vhub_systems_ed5641f65d59/how-to-handle-api-rate-limits-before-they-break-your-production-integration-53fn)
- Contributor growth: [growing maintainers](https://code.dblock.org/2024/12/14/how-to-grow-open-source-contributors-and-maintainers) ·
  [contributor-friendly essentials](https://beaulebens.com/2023/02/01/the-essentials-of-a-contributor-friendly-open-source-project/) ·
  [contribution norms](https://openresource.dev/guide/contributing/contributing-to-open-source) ·
  [first-contribution guide](https://osssoftware.org/blog/your-first-open-source-contribution-guide/)
