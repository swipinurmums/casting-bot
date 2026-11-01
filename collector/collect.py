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
from urllib.parse import urljoin, urldefrag, urlparse, urlunparse

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
    ("Brighton", r"\bBrighton\b"), ("Chesterfield", r"\bChesterfield\b"),
    ("Harrogate", r"\bHarrogate\b"), ("Norwich", r"\bNorwich\b"),
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

def opportunity_type(text: str) -> tuple[str, str]:
    lower = text.lower()
    # Classify by the actual work being requested, not simply fashion-related words.
    if re.search(r"\b(creator community|content creator|ugc creator|user.generated content|influencer campaign|influencer|social media creator|tiktok creator|instagram creator)\b", lower):
        return "Creator campaign", "High"
    if re.search(r"\b(model agency|agency application|apply to (?:the )?(?:model )?agency|model representation|join (?:the )?(?:model )?agency|new faces application|become a model|apply as a model)\b", lower):
        return "Agency application", "High"
    if re.search(r"\b(extra(?:s)?|supporting artists?|background artists?|background actors?|actor casting|acting roles?|speaking roles?|voice.?over casting|walk.on roles?)\b", lower):
        return "Acting / Extras", "High"
    if re.search(r"\b(promo(?:tional)? staff|promotional model|brand ambassador|event staff|event host|sampling staff|product demonstrator)\b", lower):
        return "Promotional / Events", "High"
    if re.search(r"\b(model casting|casting call for models?|models? wanted|model wanted|fit model|fit models|model search|open call for models?|looking for (?:male |female )?models?|seeking (?:male |female )?models?)\b", lower):
        return "Modelling casting", "High"
    if re.search(r"\b(model|models|modelling|modeling|casting|castings|fashion|editorial|lookbook)\b", lower):
        return "Potential modelling work", "Review"
    return "Other", "Review"

def category(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(creator community|content creator|influencer campaign|influencer|ugc creator|user.generated content)\b", lower):
        return "Creator / Influencer"
    if re.search(r"\b(agency application|apply to (?:the )?agency|apply as a model|model and curve applications|model applications|model representation|join (?:the )?agency|new faces application)\b", lower):
        return "Agency application"
    if any(word in lower for word in ("runway", "catwalk", "fashion week")):
        return "Runway"
    if any(word in lower for word in ("editorial", "magazine", "photographer", "photoshoot", "photo shoot")):
        return "Editorial"
    if any(word in lower for word in ("commercial", "campaign", "e-commerce", "ecommerce", "brand ambassador", "lookbook")):
        return "Commercial"
    if any(word in lower for word in ("fashion", "designer", "clothing", "garment", "fit model")):
        return "Fashion"
    if re.search(r"\b(model|models|modelling|modeling|casting|castings)\b", lower):
        return "Model casting"
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
        type_label, type_confidence = opportunity_type(combined_text)
        results.append({
            "id": stable,
            "opportunity_type": type_label,
            "opportunity_type_confidence": type_confidence,
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
import time

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


class DetailPageParser(HTMLParser):
    """Extract visible text, metadata and JSON-LD from a public casting detail page."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.h1_parts = []
        self.text_parts = []
        self._skip_depth = 0
        self.meta = {}
        self.jsonld = []
        self._capture = None
        self._script_is_jsonld = False
        self._script_buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "script":
            self._script_is_jsonld = (attrs.get("type") or "").lower().split(";")[0].strip() == "application/ld+json"
            self._script_buffer = []
            self._skip_depth += 1
            return
        if tag in ("nav", "footer", "header", "aside", "style", "noscript"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
            value = attrs.get("content", "").strip()
            if key and value:
                self.meta[key] = value
        elif tag == "title":
            self._capture = "title"
        elif tag == "h1":
            self._capture = "h1"

    def handle_data(self, data):
        if self._script_is_jsonld:
            self._script_buffer.append(data)
            return
        if self._skip_depth:
            return
        value = " ".join(data.split())
        if not value:
            return
        self.text_parts.append(value)
        if self._capture == "title":
            self.title_parts.append(value)
        elif self._capture == "h1":
            self.h1_parts.append(value)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "script":
            if self._script_is_jsonld:
                raw = "".join(self._script_buffer).strip()
                if raw:
                    self.jsonld.append(raw)
            self._script_is_jsonld = False
            self._script_buffer = []
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if tag in ("nav", "footer", "header", "aside", "style", "noscript") and self._skip_depth:
            self._skip_depth -= 1
        if tag in ("title", "h1"):
            self._capture = None

def extract_jsonld_text(parser: DetailPageParser) -> str:
    values = []
    for raw in parser.jsonld:
        try:
            obj = json.loads(raw)
            stack = obj if isinstance(obj, list) else [obj]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    for key in ("name", "description", "jobTitle", "title", "datePosted", "validThrough", "jobLocation", "address", "streetAddress", "addressLocality", "addressRegion"):
                        value = node.get(key)
                        if isinstance(value, str):
                            values.append(value)
                        elif isinstance(value, dict):
                            stack.append(value)
                        elif isinstance(value, list):
                            stack.extend(value)
                    graph = node.get("@graph")
                    if isinstance(graph, list):
                        stack.extend(graph)
                elif isinstance(node, list):
                    stack.extend(node)
        except (ValueError, TypeError):
            continue
    return " ".join(values)

def clean_listing_title(value: str) -> str:
    value = html.unescape(re.sub(r"\s+", " ", value or "")).strip(" -|·")
    value = re.split(r"\s+(?:The assignment|Compensation|How to apply|Explore and prepare)\b", value, maxsplit=1, flags=re.I)[0]
    value = re.sub(r"\s*[|·•–—-]\s*(?:The assignment|Compensation|How to apply|Explore and prepare).*?$", "", value, flags=re.I)
    return value.strip(" -|·•")[:180]

def detail_compensation(text: str) -> str:
    # Avoid treating generic footer/site copy as proof that a casting is paid.
    if EXPENSES.search(text):
        return "Expenses only"
    if TFP.search(text):
        return "TFP"
    if UNPAID.search(text):
        return "Unpaid"
    explicit_paid = re.search(
        r"(?:\bpaid\s+(?:modelling|modeling|shoot|casting|campaign|role|work|job)|"
        r"\b(?:modelling|modeling|shoot|casting|campaign|role|work|job)\s+is\s+paid|"
        r"\b(?:fee|rate|payment|remuneration)\s*(?:of|:)?\s*£?\s*\d|"
        r"£\s?\d+(?:,\d{3})*(?:\.\d{1,2})?\s*(?:per|/)\s*(?:hour|day|session))",
        text, re.I
    )
    return "Paid" if explicit_paid else "Unknown"

def extract_deadline(text: str) -> str | None:
    patterns = [
        r"(?:casting\s+ends|apply\s+by|application\s+deadline|deadline|closing\s+date|closes)\s*:?\s*(\d{1,2}\s+[A-Za-z]+\s+20\d{2})",
        r"(?:casting\s+ends|apply\s+by|application\s+deadline|deadline|closing\s+date|closes)\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+20\d{2})",
        r"(?:casting\s+ends|apply\s+by|application\s+deadline|deadline|closing\s+date|closes)\s*:?\s*(20\d{2}-\d{2}-\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = match.group(1).replace(",", "").strip()
        for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                pass
    return None

def fetch_detail_page(url: str) -> dict:
    allowed, reason = robots_allows(url)
    if not allowed:
        raise PermissionError(reason)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-GB,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            raise ValueError(f"Expected HTML, received {content_type[:100]}")
        raw = response.read(2_500_000)
        final_url = response.geturl()
    parser = DetailPageParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    visible = " ".join(parser.text_parts)
    meta_description = parser.meta.get("description") or parser.meta.get("og:description") or parser.meta.get("twitter:description") or ""
    jsonld_text = extract_jsonld_text(parser)
    combined = " ".join(x for x in (visible, meta_description, jsonld_text) if x)
    page_title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or " ".join(parser.h1_parts).strip() or " ".join(parser.title_parts).strip()
    clean_visible = re.sub(r"\s+", " ", visible).strip()
    clean_visible = re.sub(r"(?i)\b(the assignment|compensation|how to apply|explore and prepare)\b", " ", clean_visible)
    clean_visible = re.sub(r"\s+", " ", clean_visible).strip()
    return {
        "final_url": clean_url(final_url) or url,
        "page_title": clean_listing_title(page_title),
        "description": re.sub(r"\s+", " ", meta_description or jsonld_text or clean_visible).strip()[:1800],
        "content": re.sub(r"\s+", " ", combined).strip()[:12000],
        "meta": parser.meta,
    }

def fetch_html_listings(source: dict, existing_items: dict[str, dict] | None = None) -> list[dict]:
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
    source_id = source.get("id", "")
    detail_pages_checked = 0
    existing_items = existing_items or {}
    for href, title in parser.links:
        title = clean_listing_title(title)
        if not title or len(title) < 10 or len(title) > 260:
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
        path = parsed_link.path.rstrip("/").lower()
        allowed = {
            "web-tools-for-models-uk": path.startswith("/en/casting/"),
            "web-casting-london": path == "/castings" or path.startswith("/castings/"),
            "web-casting-calls-uk-manchester": bool(re.search(r"/20\d{2}/\d{2}/", path)),
            "web-modelmanagement-uk": path.startswith("/casting/") and not any(x in path for x in ("digital-twins", "model-academy")),
            "web-talentmanagement-jobs": path.startswith("/search/job/"),
            "web-talent-talks-auditions": bool(re.fullmatch(r"/audition/\d+", path)),
        }
        if source_id in allowed and not allowed[source_id]:
            continue
        if re.search(r"/(become-a-model|hire-a-model|hire-models|talent-directory|agencies?)(/|$)", path):
            continue
        if re.search(r"\b(sign.?up|register|become a model|hire a model|model academy|post a casting|digital twins?)\b", title, re.I):
            continue
        canonical = clean_url(link)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        stable = hashlib.sha256(canonical.lower().encode()).hexdigest()[:16]
        previous_item = existing_items.get(stable, {})
        detail = {}
        detail_error = previous_item.get("detail_fetch_error") or ""
        detail_attempts = int(previous_item.get("detail_fetch_attempts", 0) or 0)
        # Work through unchecked listings over successive runs instead of repeatedly
        # spending the per-source request budget on the same first eight links.
        if previous_item.get("detail_page_checked") is not True and detail_pages_checked < 8 and detail_attempts < 2:
            detail_pages_checked += 1
            detail_attempts += 1
            try:
                detail = fetch_detail_page(canonical)
                detail_error = ""
                time.sleep(1.0)
            except (urllib.error.URLError, TimeoutError, ValueError, PermissionError) as exc:
                detail_error = str(exc)[:180]
        detail_text = detail.get("content", "")
        combined_text = " ".join((title, detail_text))
        description = detail.get("description") or "Listing discovered on the source's public index page. Open the original brief to check details."
        title_from_page = detail.get("page_title", "")
        if title_from_page and len(title_from_page) >= 8:
            title = clean_listing_title(title_from_page) or title
        gender_requirement = "Female only" if re.search(r"\b(female|women|woman|girls?)\b.{0,35}\b(model|models|required|wanted|needed)\b|\b(model|models)\b.{0,35}\b(female|women|woman|girls?)\b", combined_text, re.I) else (
            "Male only" if re.search(r"\b(male|men|man|boys?)\b.{0,35}\b(model|models|required|wanted|needed)\b|\b(model|models)\b.{0,35}\b(male|men|man|boys?)\b", combined_text, re.I) else "Not specified"
        )
        age_match = re.search(r"\b(?:aged?|ages?)\s*(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*(?:yrs?|years?)?\b", combined_text, re.I)
        age_requirement = f"{age_match.group(1)}–{age_match.group(2)}" if age_match else "Not specified"
        fee_match = re.search(r"(?:£\s?\d+(?:,\d{3})*(?:\.\d{1,2})?(?:\s*(?:per|/)\s*(?:hour|day|half.day|session))?|\b\d+(?:\.\d+)?\s*(?:EUR|euros?)\b)", combined_text, re.I)
        fee = fee_match.group(0) if fee_match else ""
        application = "Check the original brief for application instructions"
        if re.search(r"\bapply\s+(?:via|through|on)\s+(?:the\s+)?platform\b", combined_text, re.I):
            application = "Platform application"
        elif re.search(r"\bDM\s+(?:me|us|the)\b|\bdirect message\b", combined_text, re.I):
            application = "Direct message"
        elif re.search(r"\bmailto:|email\s+(?:your|a)\s+(?:portfolio|application|photos|details)\b", combined_text, re.I):
            application = "Email"
        results.append({
            "id": stable,
            "title": title[:180],
            "category": category(combined_text),
            "compensation": detail_compensation(detail_text) if detail else "Unknown",
            "location": location(combined_text),
            "deadline": extract_deadline(combined_text),
            "source": source.get("name", "Public listing page"),
            "discovery_source": source.get("name", "HTML discovery"),
            "source_id": source_id,
            "source_platform": source.get("platform", "web"),
            "source_url": canonical,
            "url": canonical,
            "description": description[:1800],
            "published_at": None,
            "added": datetime.now(timezone.utc).date().isoformat(),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "status": "New",
            "saved": False,
            "demo": False,
            "collection_method": "html_scrape",
            "review_status": "needs_review",
            "detail_page_checked": bool(detail),
            "detail_fetch_error": detail_error or None,
            "detail_fetch_attempts": detail_attempts,
            "casting_requirements": {"gender": gender_requirement, "age_range": age_requirement, "fee_as_stated": fee or "Not specified"},
            "application_method": application,
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
            if item.get("collection_method") in ("manual_curated", "html_scrape"):
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
            page_items = fetch_html_listings(source, collected)
            scrape_stats.append({"source": source.get("name", source.get("id")), "leads": len(page_items), "status": "ok"})
            for item in page_items:
                key = item["id"]
                if key not in collected:
                    collected[key] = item
                    collected[key]["also_seen_at"] = []
                else:
                    previous_item = collected[key]
                    merged_item = {**previous_item, **item}
                    if item.get("detail_page_checked") is not True and previous_item.get("detail_page_checked") is True:
                        for field in ("title", "description", "location", "compensation", "deadline", "casting_requirements", "application_method", "detail_page_checked", "detail_fetch_error"):
                            if field in previous_item:
                                merged_item[field] = previous_item[field]
                    merged_item["last_seen_at"] = datetime.now(timezone.utc).isoformat()
                    collected[key] = merged_item
        except (urllib.error.URLError, TimeoutError, ValueError, PermissionError) as exc:
            scrape_stats.append({"source": source.get("name", source.get("id")), "leads": 0, "status": "skipped_or_error", "detail": str(exc)[:250]})
            errors.append({"source": source.get("name", source.get("id")), "error": str(exc)[:300]})
    # Backfill type labels across retained records too, without dropping or rewriting
    # their original category, compensation, review status, or user tracking fields.
    for item in collected.values():
        combined = " ".join(str(item.get(key, "")) for key in ("title", "description", "source", "category"))
        label, confidence = opportunity_type(combined)
        item["opportunity_type"] = label
        item["opportunity_type_confidence"] = confidence
        if item.get("collection_method") == "html_scrape":
            item["category"] = category(combined)

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
