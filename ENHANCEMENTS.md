# Competitor ad intelligence: enhancement checklist

Proposed repo path: `ENHANCEMENTS.md`  
Reviewed: 2026-10-14, repo revision `cfd707b1148b93730d9aca745fb92874af761c84`

Goal: analyse OTHER companies' ads, explain observable performance signals and creative strategy, and suggest tests. Do not present creative persistence as measured profitability. Scope every result to the collected sample.

## Progress (2026-10-14)

P0 complete in this repo: versioned schema + `v1/normalize.py` (singular/plural
field aliases, tri-state status with `"false"`-string fix, UTC-aware dates,
sample-shape adapter, canonical passthrough); `v1/parse_ads.py` CLI (collated
extraction, dedupe by ad id, malformed counted, health incl. run id and
missing-field rates); `/insights` normalizes all shapes with scope stamp and
known-status-only ratio; `GET /coverage` capability matrix; `v1/test_normalize.py`
(12 tests green); `watchlist.json` + `v1/daily_check.py` (diff new/lost/
reactivated/changed, failed runs reported unknown); daily 08:30 cron scheduled.
Raw GraphQL shape verified against saved payloads (`publisher_platform`
singular list, epoch `start_date`, `ad_archive_id`). P1–P4 remain backlog.

## Data availability labels

- **[PUBLIC]** Observed public fields, only when supplied by the source.
- **[DERIVED]** Computed from collected records; not private account results.
- **[HISTORY]** Requires repeated, stored snapshots.
- **[AI]** Creative interpretation; retain evidence and confidence.
- **[ENRICH]** Requires media processing, public-page fetching or another source.
- **[CONDITIONAL]** Available only for supported regions/categories/records.
- **[UNAVAILABLE]** Not obtainable for Indian commercial competitors through this tool.

Labels can combine. Missing data stays unknown, never zero. Proposed tasks below are not claims that these features already exist.

## P0 - Fix correctness before adding metrics

- [ ] **[PUBLIC] Fix the field-name mismatch in `v1/app.py`.** Normalize scraper `start_date` and `publisher_platform` into the same schema as `startDate` / `ad_delivery_start_time` and `platforms` / `publisher_platforms`. Add fixtures proving raw scraper dates and platforms reach `/insights`.
- [ ] **[PUBLIC, DERIVED] Fix missing status becoming inactive.** Use explicit active/inactive/unknown states; parse booleans strictly. Return unknown count and active ratio = active / (active + inactive), or null with no known statuses. Never treat the string `"false"` as true.
- [ ] **[PUBLIC] Add a parser CLI, e.g. `v1/parse_ads.py`.** Decode intercepted GraphQL payloads, extract `search_results_connection.edges[].node.collated_results[]`, normalize records, deduplicate by ad ID and write JSON ready for `/insights`. Report malformed/skipped records rather than silently dropping them.
- [ ] **[PUBLIC] Define one versioned schema.** Preserve ad ID, Page ID/name, source ad URL, source type, country searched, source start/stop dates, status, platforms, copy/headline/description/CTA, destination URL and media references. Retain raw input alongside normalized data. Country searched is not actual targeting.
- [ ] **[PUBLIC] Handle the sample-report schema explicitly.** `ads_top10.json` uses `id`, `start`, `link`, `title`, `body` and `platforms`, and lacks explicit status. Support this as an adapter without inventing status.
- [ ] **[DERIVED] Fix and test date handling.** Parse epoch and ISO dates into UTC-aware timestamps; test mixed timezone inputs, invalid dates and missing dates. Keep source launch date separate from discovery date.
- [ ] **[PUBLIC, DERIVED] Add collection health.** Run ID, collected-at, query/country/status filters, exact selected Page IDs, requested limit, records collected, duplicate/skipped counts, missing-field rates, pagination/scroll progress, errors and partial/truncated flag. A capped scrape is not full account inventory.
- [ ] **[CONDITIONAL] Verify official API coverage before promising it.** Test supported country/ad-category combinations; document API versus browser-collection capabilities. Handle pagination and unsupported responses explicitly. Never imply an access token unlocks Indian commercial competitor performance.
- [ ] **[DERIVED] Correct report language.** Replace unsupported "winning", "traction" or "performance" conclusions with named observable signals. Stamp every report with scope, collection time, coverage and limitations; replace hand-entered counts with computed values.

Done when: raw scraper, API and sample fixtures produce consistent outputs; missing fields remain unknown; counts reconcile; unsupported sources fail visibly.

## P1 - Useful single-snapshot dashboard

- [ ] **[DERIVED] Inventory:** observed record count; active/inactive/unknown counts; known-status activity ratio; unique advertisers; platform mix; image/video/carousel/dynamic/unknown format mix; language mix; destination-domain count. Platform shares may overlap.
- [ ] **[DERIVED] Deduplication:** report raw records, unique ad IDs, unique media/copy creatives and apparent concepts separately. Use exact hashes first, then similarity grouping with inspectable membership. Dynamic-ad variants may be incomplete.
- [ ] **[DERIVED] Age:** source-start age, median age and 0-7 / 8-30 / 31-90 / 90+ day buckets, with dated-record denominator. Age does not establish uninterrupted delivery or success.
- [ ] **[DERIVED, AI] Creative families:** duplicates, variants per concept, shared hooks/copy/visuals, concept versus execution changes, same-date launch clusters, formats/languages/CTAs per concept and repeated concepts. Do not call clusters proven campaigns or A/B tests.
- [ ] **[AI] Messaging:** hook, promise, problem, benefit, angle, objection, proof type, emotional tone, urgency/scarcity, numeric claims, CTA intent and implied persona/awareness/funnel stage. Keep persona and funnel labels as hypotheses, not actual targeting/objectives.
- [ ] **[DERIVED, AI] Messaging summaries:** dominant hooks/angles/proof/CTAs, repeated-message share and product/category emphasis. Show counts and denominators, with drill-down to source ads.
- [ ] **[PUBLIC, AI] Offers:** visible price/currency, discount amount/percent, bundle, subscription, trial, shipping, guarantee/returns promise, coupon, expiry and value/premium positioning. Separate "not mentioned in captured creative" from "not offered".
- [ ] **[DERIVED] Destination and offer mix:** share of observed ads by product, offer, URL and domain; landing-page concentration. These are ad-count shares, never spend shares or sales shares.
- [ ] **[PUBLIC, DERIVED] Evidence-first output:** every count/tag links to its supporting ad IDs; include quoted text, unknown counts and extraction confidence. Preserve filters and allow JSON/CSV export plus generated HTML reports.

Done when: one collection produces a repeatable report with no hand-authored metrics and every insight is traceable.

## P2 - History and competitor change tracking

- [ ] **[HISTORY] Persist snapshots:** first seen, last seen, source start/stop, observed status history, creative/offer/destination versions and run completeness. Preserve evidence/media where permitted; record failed downloads and expiring source URLs.
- [ ] **[HISTORY, DERIVED] Changes:** newly observed ads/concepts, source-started-this-week versus new-to-us, newly inactive, disappeared, reappeared, net observed active change, launch velocity and refresh rate. Disappearance is not proof of a pause; failed/partial runs must not trigger removals.
- [ ] **[HISTORY, DERIVED] Persistence:** observed cohort survival, recurring/relaunched concepts, time between launches, format/offer rotation and seasonal/event bursts. Account for observation gaps; do not claim continuous delivery.
- [ ] **[HISTORY, AI] Strategy changes:** emerging/declining angles, product focus, proof, prices/offers and landing-page changes, backed by before/after evidence.
- [ ] **[HISTORY] Change reports and optional alerts:** configurable collection cadence, retry/backoff, stop on throttling/challenges, and user-selected alerts for launches/offer changes. Start conservative; do not promise exhaustive real-time coverage.

Done when: two comparable successful snapshots generate a reliable diff, and a failed scrape cannot manufacture a competitor shutdown.

## P3 - Media, landing pages and optional enrichment

- [ ] **[ENRICH] Media facts:** duration, aspect ratio, resolution, available variants and source/local asset references; transcripts, OCR, spoken language and caption presence. Support missing media and poster-frame fallbacks instead of black video panels.
- [ ] **[ENRICH, AI] Video structure:** first-three-second hook type/opening frame; time to product, brand, offer and CTA; UGC/testimonial/founder/demo/comparison/static style; spokesperson type, editing pace, scene structure, demonstration and proof placement. Include timestamps/frame evidence. Hook type is not hook rate.
- [ ] **[ENRICH, DERIVED] Asset reuse:** similar copy/images/video across concepts and competitors; distinguish exact duplicates from similarity matches.
- [ ] **[ENRICH] Landing-page snapshots:** final URL/domain, redirects, page type (product/collection/home/lead form/advertorial/quiz), headline/offer, visible price/availability, proof/trust/guarantee, lead versus purchase path and verifiable technology. Timestamp checks; old ad offers may be stale.
- [ ] **[ENRICH, AI, HISTORY] Ad-to-page match:** compare promise, product, offer and CTA; flag mismatches and version changes with evidence. Do not infer conversion rate or funnel drop-off.
- [ ] **[ENRICH, HISTORY] Optional engagement:** accessible likes/comments/shares/views, timestamped growth and comment themes/questions/objections. Record post/source identity and coverage. Organic and paid engagement can mix; no engagement rate without a valid denominator.
- [ ] **[CONDITIONAL] Transparency extensions:** retain disclosed payer/beneficiary, reach/targeting and spend/impression ranges only where the source supplies them for the relevant region/category. Store ranges, units and disclosure scope; never apply them to undisclosed Indian commercial ads.
- [ ] **[ENRICH] Optional third-party estimates:** accept only explicitly sourced modeled impressions/spend/popularity with provider, method/version if supplied, date and uncertainty. Keep separate from observed facts; do not invent estimates from age or ad counts.

## P4 - Cross-competitor decisions

- [ ] **[DERIVED, HISTORY, AI] Comparable brand views:** observed active ads, unique concepts, new-concept velocity, longevity distributions, format/platform/language mix, hook/angle/proof/offer mix, product emphasis and landing-page concentration. Compare the same country, period and collection depth; show coverage differences.
- [ ] **[DERIVED, AI] Market patterns and sample gaps:** recurring versus new ideas, shared creative themes and underrepresented angles. Label "share of observed creative activity", not market share, spend share or impression share of voice.
- [ ] **[AI] Decision report:** what changed, 3-5 persistent concepts worth inspecting, emerging offers/angles, differentiated test ideas and hook/script/storyboard briefs, each with source ads and a rationale. Propose experiments, not guaranteed winners.
- [ ] **[DERIVED, AI] Transparent prioritization:** expose persistence, repetition, recency, novelty and completeness components when ranking examples. Do not label the result predicted ROI or a validated winning-ad score.
- [ ] **[DERIVED] Ship tests and documentation:** fixture/regression tests for normalization, status, dates, dedupe, partial runs, history diffs and denominators; a generated Stack Club sample; schema/data dictionary, availability notes, collection limits and privacy/Terms-of-Service cautions. Keep tokens and `.env` out of exports and commits.

## Not competitor outputs: explicit unavailable fields

- [ ] **[UNAVAILABLE] Return null plus an availability reason, never guessed values, for:** actual spend, impressions, reach, frequency, CPM, link/outbound clicks, CTR, CPC, landing-page views/cost per visit, leads/CPL, purchases/conversions/CPA, revenue/purchase value, ROAS and conversion rate.
- [ ] **[UNAVAILABLE] Do the same for:** video starts, three-second views, ThruPlays/completions, hook/hold/watch-through/retention rates, performance fatigue, actual audience/placement performance, targeting and attribution-based results. Some transparency disclosures are conditional exceptions, not private account analytics.

These private metrics require the competitor's authorised account/analytics access. An own-account analytics module is outside this competitor-focused plan. Longevity, repetition and creative volume are observable signals, not substitutes for these metrics.

## Grounding

Repo inspected read-only; no commit, push or code changes. The MIT license is already present, so adding a license is not a task.

- Repo and implementation: https://github.com/sameer-hoda/meta-ad-library
- Competitor history/creative analysis reference: https://www.foreplay.co/spyder-ad-spy
- Estimate-labeling reference: https://bigspy.com/faq
- Creative/offer comparison reference: https://www.minea.com/competitor-ad-analysis
- Transparency scope: https://transparency.meta.com/researchtools/ad-library-tools/
- API field/coverage technical reference: https://addownloader.readthedocs.io/en/latest/adlib_api.html

Vendor references informed the prior landscape research; their feature claims are not audits of estimate accuracy. API coverage must still be tested against current source responses before implementation promises.
