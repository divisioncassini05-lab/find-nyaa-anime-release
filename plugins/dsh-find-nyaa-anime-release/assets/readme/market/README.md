# Market screenshots

These images render the actual `client/Panel.jsx` component using the fictional,
read-only records in `client/market-fixture.mjs`. They do not connect to a DSH
profile, Bangumi, qBittorrent or Nyaa. Cover placeholders are intentional: no
real cover is assigned to a fictional work. No credentials or personal records
are used. The UI heading matches the dsh-find-anime display name.

Order: daytime inbox, expanded result, weekly plan form, Bangumi library,
nighttime inbox. `screenshots.json` at the package root declares the same order
for public-market discovery. This does not itself submit the plugin for review.

Reproduce with `node tools/capture_market.mjs` after installing development
dependencies and Playwright. Set `PLAYWRIGHT_MODULE` to an external Playwright
module if needed; optionally set `PLAYWRIGHT_CHANNEL=msedge` or `chrome` to use
an installed browser. Browser contexts are fresh and external requests blocked.
The capture server closes automatically. Only the isolated preview is built;
the installed plugin and production bundle are not modified.
