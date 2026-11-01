# Modelling Opportunity Radar

A free-first personal dashboard for discovering and tracking modelling opportunities across the UK.

## Current version

The first version is a static website designed for GitHub Pages. It includes:

- Responsive dashboard layout
- Search and filters for category, compensation and location
- Saved opportunities and application statuses
- Manual opportunity entry with quick capture from pasted casting captions/briefs
- Public source directory covering 11 user-supplied Instagram accounts and two UK casting boards
- Basic extraction of likely title, category, compensation, location, deadline and links from pasted text
- Browser-local persistence using localStorage
- Private modelling profile editor (profile details remain in the current browser)
- Initial opportunity-to-profile matching labels with brief explanations
- Clearly labelled example records (not real casting calls)

## Run locally

Open `index.html` in a browser. No build step or package installation is required.

## Publish with GitHub Pages

1. Open the repository's **Settings → Pages**.
2. Under **Build and deployment**, select **Deploy from a branch**.
3. Choose the `main` branch and `/(root)` folder, then save.
4. Wait for GitHub Pages to publish the site.

## Important current limitations

- The discovery pipeline supports permitted RSS/Atom feeds, but none are configured yet. The source directory is a research/intake shortlist, not an automatic scraper, so the live feed will remain empty until suitable feeds or authorised integrations are added.
- Instagram accounts are registered for manual review; arbitrary third-party Stories are not available through the standard Instagram API, so the project does not scrape them.
- Manually entered opportunities and the modelling profile are stored in the current browser only. They are not synced across devices.
- Profile matching is an early keyword-based heuristic, not a reliable eligibility decision. Always check the original casting brief.
- Underwear briefs are flagged for individual review; nudity is excluded. Missing requirements should remain uncertain rather than being guessed.
- Example cards are fictional UI examples and must not be treated as real opportunities.
- A public GitHub Pages site must never contain API keys, passwords, private tokens or other secrets.

## Roadmap

1. Verify and prioritise source coverage, including the two public UK casting boards and Instagram accounts.
2. Add permitted public RSS/Atom feeds and documented API integrations.
3. Improve matching against casting age, height, gender and work preferences.
4. Improve cross-source deduplication and retain all source links.
5. Add freshness checks, deadline/expiry handling and source attribution.
6. Build alerts and optional cross-device persistence without exposing private profile details.

## Compensation labels

- **Paid** — a stated fee or rate is advertised.
- **TFP** — time for prints / portfolio collaboration.
- **Unpaid** — explicitly unpaid.
- **Expenses only** — expenses are covered, but no fee is stated.
- **Unknown** — the listing does not make compensation clear.

Never infer that an opportunity is unpaid simply because no rate is shown.