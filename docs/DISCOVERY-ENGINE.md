# Discovery engine

## Pipeline

1. **Source registry** — `data/sources.json` records each source, platform, collection method, permission state and enabled flag.
2. **Collectors** — each collector only accesses sources through a permitted public feed, documented API, authorised integration or user-submitted link/content.
3. **Normalisation** — collector output uses a shared opportunity schema.
4. **Deduplication** — canonical source URL is the first stable key. Future matching can use title, brand, date, location and image/content fingerprints.
5. **Dashboard** — `data/opportunities.json` is the public feed consumed by the site.
6. **Alerts** — future notifications should be sent only for newly discovered and relevant opportunities.

## Current collector

`collector/collect.py` reads configured Google News RSS/Atom search feeds and a set of configured public HTML listing indexes. The HTML collector uses Python's standard library, checks each page against its site's `robots.txt`, makes a single request to each configured index page per run, and extracts same-domain links whose anchor text looks casting-related. It does not use browser automation, accounts, cookies, private APIs, CAPTCHA workarounds or access-control bypasses.

HTML sources currently enabled for discovery are ToolsForModels, Casting London, Casting Calls UK (Manchester index), ModelManagement UK, Models Direct, 3Light Talent, FashionDB, Talent Management and Talent Talks. A source may return zero leads or be skipped if its robots policy blocks the page, it is unavailable, or the page structure does not expose usable listing links. Robots permission is not a substitute for checking site terms; source-specific permission should be confirmed and any source can be disabled in `data/sources.json`. Backstage automated collection remains disabled because its Terms of Service expressly prohibit automated access tools.

Extracted HTML links are deliberately lightweight discovery leads: the collector does not claim to have read the full brief, and compensation/location/deadline remain Unknown or TBC until explicitly verified. Every lead is labelled `needs_review`. Per-source `scrape_stats` and errors are written to `data/opportunities.json` and printed in the Actions log. RSS results remain search-index discovery leads, not verified castings.

Run locally:

```bash
python collector/collect.py
```

Run on GitHub: Actions → Discover opportunities → Run workflow. A scheduled run is configured every three hours.

## Instagram

Instagram is a priority source category, but Stories from arbitrary accounts are not available through the standard Instagram API. The official API is scoped to professional accounts and authorised access; Story endpoints are for the connected account, not arbitrary third-party Stories.

For now, Instagram sources are kept in the registry as `manual_review`. Future options to investigate:

- Ask account owners for permission, a feed, or a direct submission channel.
- Use an authorised Meta integration where the exact content and permission scope support the intended use.
- Accept user-submitted Story links, screenshots or forwarded opportunity details, with human approval before publishing.
- Monitor public profile posts only where a documented, permitted access method exists; do not assume this includes Stories.

Do not use session-cookie scraping, login automation, private endpoints, access-control workarounds or methods that violate platform terms.

## Shared opportunity fields

- `id`, `title`, `category`, `location`
- `compensation`: Paid / TFP / Unpaid / Expenses only / Unknown
- `deadline` (nullable), `published_at`, `collected_at`
- `source`, `source_platform`, `source_url`, `url`
- `description`, `status`, `saved`, `demo`
- `also_seen_at`: other sources that published the same opportunity

Compensation is only classified from explicit wording. Missing pay information remains Unknown.


## Automated discovery boundaries

The collector reads configured RSS/Atom feeds and makes conservative, robots-checked requests to configured public HTML index pages. It does not log in, use session cookies, crawl private areas, bypass CAPTCHA/access controls or scrape Instagram Stories. Backstage remains excluded because its Terms of Service expressly prohibit automated access tools. Public-page extraction is not a guarantee of permission under a site's terms; disable any source whose terms prohibit automated collection or where permission is unclear.
