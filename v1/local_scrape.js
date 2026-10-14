// Conservative local Meta Ad Library scraper (no Apify, no token).
// Meta returns HTTP 403 to headless browsers but still renders the page and
// streams ad data over GraphQL — so this script ignores the status code,
// scrolls a few times, and saves the intercepted GraphQL payloads.
//
// Usage (from repo root):
//   cd third_party/meta-ads-library-scraper && npm install
//   npx playwright install chromium
//   NODE_PATH="$PWD/node_modules" node ../../v1/local_scrape.js Myntra IN /tmp/meta_ads_raw.json
//
// Then normalize + analyze, e.g. POST the parsed ads to the /insights endpoint.
const fs = require('fs');
const { chromium } = require('playwright');

const QUERY = process.argv[2] || 'Myntra';
const COUNTRY = process.argv[3] || 'IN';
const OUT = process.argv[4] || '/tmp/meta_ads_raw.json';

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'],
  });
  const context = await browser.newContext({
    locale: 'en-US', timezoneId: 'Asia/Kolkata',
    viewport: { width: 1366, height: 768 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    extraHTTPHeaders: { 'Accept-Language': 'en-US,en;q=0.9' },
  });
  // Force English UI: Meta picks Kannada from this IP's geolocation unless told otherwise.
  await context.addCookies([{ name: 'locale', value: 'en_US', domain: '.facebook.com', path: '/' }]);
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  });
  const page = await context.newPage();
  const payloads = [];
  page.on('response', async (r) => {
    if (!r.url().includes('/graphql')) return;
    try {
      const body = await r.text();
      if (body.includes('search_results_connection')) payloads.push(body);
    } catch (e) { /* ignore race-closed bodies */ }
  });
  const url = `https://www.facebook.com/ads/library?q=${encodeURIComponent(QUERY)}&country=${COUNTRY}&ad_type=all&active_status=all&view_all_page_id=`;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
  await page.waitForTimeout(10000);
  for (let i = 0; i < 5; i++) {
    await page.mouse.wheel(0, 1200 + Math.floor(Math.random() * 800));
    await page.waitForTimeout(3000);
  }
  fs.writeFileSync(OUT, JSON.stringify(payloads));
  console.log(JSON.stringify({ query: QUERY, country: COUNTRY, payloads: payloads.length, bytes: payloads.join('').length }));
  await browser.close();
})();
