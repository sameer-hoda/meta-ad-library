# Meta Ad Library toolkit — search, scrape, and analyze ads locally

Search Meta's Ad Library through the official API, scrape commercial ads
with a local headless browser (no Apify, no paid proxies for small runs),
and turn the results into an HTML competitor report.

Includes a full sample: a 10-ad breakdown of The Stack Club (India) in
`reports/stackclub/`.

## Quickstart

```bash
git clone <this-repo-url> && cd meta-ad-library
python3 -m venv .venv
source .venv/bin/activate
pip install -r v1/requirements.txt
```

### 1. Run the API (official Meta API search + insights)

```bash
cp v1/.env.example .env   # add your META_ACCESS_TOKEN
source .venv/bin/activate
uvicorn v1.app:app --reload --port 8000
# open http://127.0.0.1:8000/docs
```

Without a token, `/search` returns 501 with setup instructions —
`/insights` and `/nikshacks/run-info` work without one.

### 2. Scrape locally (commercial ads, no token)

Meta returns HTTP 403 to headless browsers but still renders results and
streams ad data over GraphQL — the scraper ignores the 403 and intercepts
the data. English is forced via locale + cookie (Meta geo-targets language
by IP otherwise).

```bash
# one-time: fetch the (excluded) browser dependency
git clone --depth 1 https://github.com/NiksHacks/meta-ads-library-scraper third_party/meta-ads-library-scraper
cd third_party/meta-ads-library-scraper && npm install && npx playwright install chromium && cd ../..

# scrape (conservative: ~5 scrolls)
NODE_PATH="third_party/meta-ads-library-scraper/node_modules" \
  node v1/local_scrape.js "Brand Name" IN /tmp/ads_raw.json
```

Parse `search_results_connection.edges[].node.collated_results[]` for
`ad_archive_id`, `page_name`, `is_active`, `start_date`,
`publisher_platform`, and `snapshot` (copy, `videos[].video_hd_url`,
`images[].original_image_url`), then POST the list to `/insights`.

### 3. View the sample report

Open `reports/stackclub/index.html` in a browser — 10 real ads, 5 local
videos, frame-by-frame breakdowns, and a stealable messaging playbook.
Rebuild it for another brand by repeating step 2 and adapting the template.

## Layout

- `v1/app.py` — FastAPI service (`/health`, `/search`, `/insights`, `/nikshacks/run-info`)
- `v1/local_scrape.js` — conservative local scraper (403-tolerant GraphQL interception)
- `v1/requirements.txt`, `v1/.env.example`, `v1/README.md`
- `reports/stackclub/` — sample report: `index.html`, `ads_top10.json`, `assets/` (videos, images, frame strips)

## Notes and limits

- Meta publishes no spend, impressions, or targeting for Indian commercial
  ads — traction reads come from creative longevity and refresh cadence.
- Scraping may conflict with Meta's Terms of Service; use for internal
  research and keep runs small with human-like delays.
- Never commit `.env` or tokens. `third_party/` and `.venv/` are git-ignored
  by design — every clone re-fetches them with the commands above.
