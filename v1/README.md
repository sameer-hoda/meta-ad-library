# Meta Ad Library API (v1) — India competitor setup

Hybrid: official API for search + NiksHacks Apify actor for commercial creatives.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r v1/requirements.txt
```

Copy `v1/.env.example` to `.env` and fill in tokens (never commit `.env`).

## Run

```bash
source .venv/bin/activate
uvicorn v1.app:app --reload --port 8000
```

## Try it

```bash
curl localhost:8000/health
curl "localhost:8000/nikshacks/run-info?query=Nike&country=IN"
curl "localhost:8000/search?query=shoes&country=IN&limit=5"  # needs META_ACCESS_TOKEN
curl -X POST localhost:8000/insights -H 'Content-Type: application/json' \
  -d '{"ads":[{"pageName":"Brand A","isActive":true,"platforms":["Facebook"],"startDate":"2026-09-01"}]}'
```

## Scrape locally (no Apify, works)

`v1/local_scrape.js` ignores Meta's 403 status (the page still renders and
streams GraphQL), scrolls conservatively, and saves raw payloads. Parse
`search_results_connection.edges[].node.collated_results[]` for
`ad_archive_id`, `page_name`, `is_active`, `start_date`,
`publisher_platform`, and `snapshot`, then POST to `/insights`.

```bash
cd third_party/meta-ads-library-scraper && npm install
npx playwright install chromium
NODE_PATH="$PWD/node_modules" node ../../v1/local_scrape.js Myntra IN /tmp/meta_ads_raw.json
```

Verified Oct 2026: `Myntra / IN` returned 38 unique ads across 5 payloads.

## Run the NiksHacks scraper (Apify alternative)

This repo is a Node Apify Actor, not a Python package:

1. Import `NiksHacks/meta-ads-library-scraper` in Apify Console.
2. Use the JSON from `/nikshacks/run-info` as the actor input with `country=IN`.
3. Local alternative needs Node 20+, `npm install`, `npx playwright install chromium`, plus residential proxies.

Meta publishes no commercial spend/impressions for IN, so insights use creative volume and activity.
