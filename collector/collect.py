#!/usr/bin/env python3
"""Collect public opportunities from explicitly configured RSS/Atom feeds.

This collector intentionally does not scrape Instagram Stories or bypass logins,
paywalls, robots rules, or source terms. Add only feeds whose use is permitted.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "data" / "sources.json"
EMAIL_LEADS_FILE = ROOT / "data" / "email-leads.json"
OUTPUT_FILE = ROOT / "data" / "opportunities.json"
USER_AGENT = "ModellingOpportunityRadar/0.1 (+https://github.com/swipinurmums/casting-bot)"
OPPORTUNITY_TITLE = re.compile(r"\b(casting call for models?|model casting|model call|model search|model wanted|models wanted|model needed|models needed|open call for models?|fit models?|fit model|new faces|talent search|looking for (?:male |female |new )?models?|seeking (?:male |female |new )?models?|audition(?:s)? for models?)\b|\b(?:male|female|men\x27s|women\x27s) models?\b.{0,90}\b(?:casting|wanted|needed|shoot|campaign|lookbook|photoshoot)\b", re.I)
MAX_AGE_DAYS = 45
PAID = re.compile(r"(?:£\s?\d|\bpaid\b|\bfee\b|\brate\b|\bday rate\b|\bsalary\b|\bremuneration\b)", re.I)
TFP = re.compile(r"\b(TFP|time for prints?|time for print)\b", re.I)
UNPAID = re.compile(r"\b(unpaid|voluntary|volunteer)\b", re.I)
EXPENSES = re.compile(r"\b(expenses (?:only|covered|paid)|travel expenses|expenses reimbursed)\b", re.I)
CITY_PATTERNS = [
    ("London", r"\bLondon\b"), ("Manchester", r"\bManchester\b"),
    ("Birmingham", r"\bBirmingham\b"), ("Leeds", r"\bLeeds\b"),
    ("Liverpool", r"\bLiverpool\b"), ("Bristol", r"\bBristol\b"),
    ("Glasgow", r"\bGlasgow\b"), ("Edinburgh", r"\bEdinburgh\b"),
    ("Remote / UK-wide", r"\b(remote|UK[- ]wide|nationwide|anywhere in the UK)\b")
]

def text_of(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())

def child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in list(node):
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names:
            return text_of(child)
    return ""

def entry_link(node: ET.Element) -> str:
    for child in list(node):
        if child.tag.rsplit("}", 1)[-1].lower() == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            value = text_of(child)
            if value:
                return value
    return ""

def clean_url(value: str) -> str:
    try:
        parsed = urlparse(value.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ""
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    except Exception:
        return ""

def compensation(text: str) -> str:
    # Explicit wording only. Missing compensation is never assumed to mean unpaid.
    if EXPENSES.search(text):
        return "Expenses only"
    if TFP.search(text):
        return "TFP"
    if UNPAID.search(text):
        return "Unpaid"
    if PAID.search(text):
        return "Paid"
    return "Unknown"

def category(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("runway", "catwalk", "fashion week")):
        return "Runway"
    if any(word in lower for word in ("editorial", "magazine", "photographer", "photoshoot", "photo shoot")):
        return "Editorial"
    if any(word in lower for word in ("commercial", "campaign", "e-commerce", "ecommerce", "brand ambassador", "lookbook")):
        return "Commercial"
    if any(word in lower for word in ("fashion", "designer", "clothing", "garment")):
        return "Fashion"
    return "Other"

def location(text: str) -> str:
    for name, pattern in CITY_PATTERNS:
        if re.search(pattern, text, re.I):
            return name
    return "Location TBC"

def parse_date(value: str) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except Exception:
            return None

def fetch_feed(source: dict) -> list[dict]:
    feed_url = source.get("feed_url", "")
    if not feed_url:
        return []
    request = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read(5_000_000)
    root = ET.fromstring(raw)
    entries = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in ("item", "entry")]
    results = []
    for node in entries:
        title = child_text(node, ("title",))
        summary = child_text(node, ("description", "summary", "content", "encoded"))
        link = clean_url(entry_link(node))
        published_raw = child_text(node, ("pubdate", "published", "updated", "date"))
        published_at = parse_date(published_raw)
        body = html.unescape(re.sub(r"<[^>]+>", " ", summary))
        combined = " ".join((title, body))
        # Search feeds can contain unrelated stories about models. Keep only
        # recent titles that clearly describe a casting/recruitment opportunity.
        if not title or not link or not OPPORTUNITY_TITLE.search(title):
            continue
        if not published_at:
            continue
        published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - published_dt > timedelta(days=MAX_AGE_DAYS):
            continue
        publisher = child_text(node, ("source",))
        stable = hashlib.sha256(link.lower().encode()).hexdigest()[:16]
        results.append({
            "id": stable,
            "title": title[:180],
            "category": category(combined),
            "compensation": compensation(combined),
            "location": location(combined),
            "deadline": None,
            "source": publisher or source.get("name", "Unknown source"),
            "discovery_source": source.get("name", "RSS discovery"),
            "source_platform": source.get("platform", "web"),
            "source_url": link,
            "url": link,
            "description": re.sub(r"\s+", " ", body).strip()[:900],
            "published_at": published_at,
            "added": datetime.now(timezone.utc).date().isoformat(),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "status": "New",
            "saved": False,
            "demo": False,
            "collection_method": "rss_discovery",
            "review_status": "needs_review",
            "application_method": "Check the original listing and its eligibility, fee, deadline and application route before applying"
        })
    return results


# Conservative public-page discovery. This is deliberately a lead extractor, not
# a browser/login scraper. Each source must opt in and pass its robots.txt check.
from html.parser import HTMLParser
from urllib.parse import urljoin, urldefrag
import urllib.robotparser

LISTING_HINTS = re.compile(
    r"\b(model|models|casting|castings|casting call|open call|audition|talent|"
    r"campaign|photoshoot|photo shoot|lookbook|fashion|commercial|brand|"
    r"new faces|wanted|seeking|fit model|editorial)\b", re.I
)
NAV_LABELS = {
    "home", "about", "contact", "contact us", "privacy", "terms", "login",
    "log in", "sign up", "register", "search", "next", "previous", "read more",
    "view all", "learn more", "menu", "my account", "apply now"
}

class ListingLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "a" and attrs.get("href"):
            self.current = {"href": attrs["href"], "text": []}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            text_value = " ".join(" ".join(self.current["text"]).split())
            self.links.append((self.current["href"], text_value))
            self.current = None

def robots_allows(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            robots_text = response.read(500_000).decode("utf-8", errors="replace")
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(robots_text.splitlines())
        allowed = parser.can_fetch(USER_AGENT, url)
        return allowed, "robots.txt allows path" if allowed else "robots.txt disallows path"
    except urllib.error.HTTPError as exc:
        # A missing robots.txt is not a robots prohibition; other HTTP failures
        # are treated conservatively as unavailable.
        if exc.code == 404:
            return True, "robots.txt not found"
        return False, f"robots.txt returned HTTP {exc.code}"
    except Exception as exc:
        return False, f"robots.txt check failed: {str(exc)[:160]}"

def fetch_html_listings(source: dict) -> list[dict]:
    page_url = source.get("url", "")
    if not page_url:
        return []
    allowed, reason = robots_allows(page_url)
    if not allowed:
        raise PermissionError(reason)
    request = urllib.request.Request(
        page_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-GB,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            raise ValueError(f"Expected HTML, received {content_type[:100]}")
        raw = response.read(4_000_000)
        final_url = response.geturl()
    parser = ListingLinkParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    base_host = urlparse(final_url).netloc.lower().removeprefix("www.")
    seen = set()
    results = []
    for href, title in parser.links:
        title = re.sub(r"\s+", " ", html.unescape(title)).strip()
        if not title or len(title) < 10 or len(title) > 180:
            continue
        if title.casefold() in NAV_LABELS or not LISTING_HINTS.search(title):
            continue
        link = urldefrag(urljoin(final_url, href))[0]
        parsed_link = urlparse(link)
        if parsed_link.scheme not in ("http", "https"):
            continue
        link_host = parsed_link.netloc.lower().removeprefix("www.")
        if link_host != base_host or link.rstrip("/") == final_url.rstrip("/"):
            continue
        canonical = clean_url(link)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        stable = hashlib.sha256(canonical.lower().encode()).hexdigest()[:16]
        results.append({
            "id": stable,
            "title": title[:180],
            "category": category(title),
            "compensation": "Unknown",
            "location": "Location TBC",
            "deadline": None,
            "source": source.get("name", "Public listing page"),
            "discovery_source": source.get("name", "HTML discovery"),
            "source_platform": source.get("platform", "web"),
            "source_url": canonical,
            "url": canonical,
            "description": "Listing discovered on the source's public index page. Open the original brief to check details.",
            "published_at": None,
            "added": datetime.now(timezone.utc).date().isoformat(),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "status": "New",
            "saved": False,
            "demo": False,
            "collection_method": "html_scrape",
            "review_status": "needs_review",
            "application_method": "Open the original listing and check eligibility, compensation, deadline and application route",
        })
    return results

def main() -> None:
    config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    collected: dict[str, dict] = {}
    errors = []
    # Preserve manually verified entries while refreshing automated RSS results.
    try:
        previous = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        for item in previous.get("opportunities", []):
            if item.get("collection_method") == "manual_curated":
                collected[item["id"]] = item
    except (OSError, ValueError, KeyError):
        pass
    # Import minimal metadata leads published by the user-authorised Gmail bridge.
    # These remain unverified until the original casting brief is checked.
    try:
        email_payload = json.loads(EMAIL_LEADS_FILE.read_text(encoding="utf-8"))
        for item in email_payload.get("leads", []):
            if item.get("id"):
                collected[item["id"]] = item
    except (OSError, ValueError):
        pass
    active_feeds = [s for s in config.get("sources", []) if s.get("enabled") and s.get("collection") == "rss_atom" and s.get("feed_url")]
    active_pages = [s for s in config.get("sources", []) if s.get("enabled") and s.get("collection") == "html_scrape" and s.get("url")]
    feed_stats = []
    for source in active_feeds:
        try:
            feed_items = fetch_feed(source)
            feed_stats.append({"source": source.get("name", source.get("id")), "leads": len(feed_items)})
            for item in feed_items:
                # Same canonical URL from multiple feeds becomes one opportunity;
                # preserve every discovered source link.
                key = item["id"]
                if key not in collected:
                    collected[key] = item
                    collected[key]["also_seen_at"] = []
                else:
                    collected[key]["also_seen_at"].append({"source": item["source"], "url": item["source_url"]})
        except (urllib.error.URLError, TimeoutError, ET.ParseError, ValueError) as exc:
            errors.append({"source": source.get("name", source.get("id")), "error": str(exc)[:300]})
    scrape_stats = []
    for source in active_pages:
        try:
            page_items = fetch_html_listings(source)
            scrape_stats.append({"source": source.get("name", source.get("id")), "leads": len(page_items), "status": "ok"})
            for item in page_items:
                key = item["id"]
                if key not in collected:
                    collected[key] = item
                    collected[key]["also_seen_at"] = []
                else:
                    collected[key].setdefault("also_seen_at", []).append({"source": item["source"], "url": item["source_url"]})
        except (urllib.error.URLError, TimeoutError, ValueError, PermissionError) as exc:
            scrape_stats.append({"source": source.get("name", source.get("id")), "leads": 0, "status": "skipped_or_error", "detail": str(exc)[:250]})
            errors.append({"source": source.get("name", source.get("id")), "error": str(exc)[:300]})
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(active_feeds) + len(active_pages),
        "opportunities": sorted(collected.values(), key=lambda x: x.get("published_at") or "", reverse=True),
        "errors": errors,
        "feed_stats": feed_stats,
        "scrape_stats": scrape_stats
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Checked {len(active_feeds)} feed(s) and {len(active_pages)} public page(s); collected {len(collected)} opportunity/ies; {len(errors)} error(s).")
    for stat in feed_stats:
        print("  " + stat["source"] + ": " + str(stat["leads"]) + " lead(s)")
    for stat in scrape_stats:
        print("  SCRAPE " + stat["source"] + ": " + str(stat["leads"]) + " lead(s) [" + stat["status"] + "]")
    for error in errors:
        print("  ERROR " + error["source"] + ": " + error["error"])

if __name__ == "__main__":
    main()
