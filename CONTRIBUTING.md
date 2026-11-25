# Contributing

Thanks for stopping by. This project tracks competitor ads honestly:
unknown stays unknown, partial runs never read as shutdowns, and
longevity is a signal, not performance proof.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r v1/requirements.txt
# scraper only:
git clone --depth 1 https://github.com/NiksHacks/meta-ads-library-scraper third_party/meta-ads-library-scraper
cd third_party/meta-ads-library-scraper && npm install && npx playwright install chromium
```

Copy `v1/.env.example` to `.env` for tokens. Never commit `.env`.

## Checks (same as CI)

```bash
python -m unittest discover -s v1 -p "test_*.py"
node --check v1/local_scrape.js
```

## How to contribute

1. Fork, branch, keep the diff small and scoped.
2. Every behavior change ships with a fixture test in `v1/test_*.py`.
3. Run the checks above before pushing.
4. Open a PR describing scope, coverage stamp, and limits.

Good first issues: more watchlist brands with verified queries,
hook-type fixtures from real ad copy, report template polish.

## Ground rules

- Missing data stays unknown, never zero. No spend/reach/targeting claims
  for Indian commercial ads — Meta does not publish them.
- Every insight links back to ad ids + quoted evidence.
- Keep runs small and human-paced; scraping must respect Meta's Terms.
