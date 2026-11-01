# Discovery engine

## Pipeline

1. **Source registry** — `data/sources.json` records each source, platform, collection method, permission state and enabled flag.
2. **Collectors** — each collector only accesses sources through a permitted public feed, documented API, authorised integration or user-submitted link/content.
3. **Normalisation** — collector output uses a shared opportunity schema.
4. **Deduplication** — canonical source URL is the first stable key. Future matching can use title, brand, date, location and image/content fingerprints.
5. **Dashboard** — `data/opportunities.json` is the public feed consumed by the site.
6. **Alerts** — future notifications should be sent only for newly discovered and relevant opportunities.

## Current collector

`collector/collect.py` reads configured Google News RSS/Atom search feeds, including targeted searches for Talent Talks, Models Direct, 3Light Talent and broader UK model/casting terms. Backstage automated collection is disabled because its Terms of Service expressly prohibit automated access tools. These are search-index discovery leads, not direct publisher feeds or guaranteed coverage. The collector does not crawl arbitrary websites. Add a source only after checking its terms, robots guidance and feed usage permissions.

Other directories currently registered for manual review include ToolsForModels, FashionDB, Talent Management, Models Direct, Backstage and 3Light Talent. A directory appearing in the registry does not mean its listings are automatically collected. RSS results are discovery leads, not verified castings; the dashboard labels them as unverified until the original brief has been checked. Each run logs the number of leads returned by each feed so weak sources can be identified.

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

The collector only reads configured RSS/Atom feeds. It does not crawl arbitrary listing pages. Backstage automated collection is disabled because its Terms of Service expressly prohibit bots and other automatic access tools. Talent Talks and Models Direct are currently discovered via third-party search-index RSS queries, not direct scraping of their websites. This is not guaranteed coverage and does not bypass membership or application restrictions. Direct integrations should be added only after the source provides permission, a documented feed/API, or other clear authorisation.
