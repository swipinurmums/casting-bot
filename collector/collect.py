#!/usr/bin/env python3
"""Collect public opportunities from explicitly configured RSS/Atom feeds.

This collector intentionally does not scrape Instagram Stories or bypass logins,
paywalls, robots rules, or source terms. Add only feeds whose use is permitted.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "data" / "sources.json"
OUTPUT_FILE = ROOT / "data" / "opportunities.json"
USER_AGENT = "ModellingOpportunityRadar/0.1 (+https://github.com/swipinurmums/casting-bot)"
KEYWORDS = ("model", "modelling", "modeling", "casting", "fashion", "editorial", "campaign", "runway", "lookbook", "photoshoot", "photographer", "brand ambassador", "fit model")
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
        published = child_text(node, ("pubdate", "published", "updated", "date"))
        body = re.sub(r"<[^>]+>", " ", summary)
        combined = " ".join((title, body))
        if not title or not link or not any(k in combined.lower() for k in KEYWORDS):
            continue
        stable = hashlib.sha256(link.lower().encode()).hexdigest()[:16]
        results.append({
            "id": stable,
            "title": title[:180],
            "category": category(combined),
            "compensation": compensation(combined),
            "location": location(combined),
            "deadline": None,
            "source": source.get("name", "Unknown source"),
            "source_platform": source.get("platform", "web"),
            "source_url": link,
            "url": link,
            "description": re.sub(r"\s+", " ", body).strip()[:900],
            "published_at": parse_date(published),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "status": "New",
            "saved": False,
            "demo": False
        })
    return results

def main() -> None:
    config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    collected: dict[str, dict] = {}
    errors = []
    active_feeds = [s for s in config.get("sources", []) if s.get("enabled") and s.get("collection") == "rss_atom" and s.get("feed_url")]
    for source in active_feeds:
        try:
            for item in fetch_feed(source):
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
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(active_feeds),
        "opportunities": sorted(collected.values(), key=lambda x: x.get("published_at") or "", reverse=True),
        "errors": errors
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Checked {len(active_feeds)} feed(s); collected {len(collected)} opportunity/ies; {len(errors)} error(s).")

if __name__ == "__main__":
    main()
