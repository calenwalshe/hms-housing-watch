#!/usr/bin/env python3
"""Daily HMS housing lead refresh.

Reads config/sources.json, collects leads only from `collect` sources, and
refreshes successful sources and keeps the last checked data for failed sources.
If every collection source fails, the snapshot and timestamp remain untouched.

Usage: daily_refresh.py [--transport cdp|http] [--output PATH] [--dry-run]
  --transport  override each source's configured transport (default: per source)
  --output     snapshot path (default site/leads.json)
  --dry-run    collect and print, write nothing
"""
import argparse, asyncio, json, os, re, sys, time, urllib.request
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Literal
from urllib.parse import urlsplit, parse_qsl, urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.environ.get("HMS_CONFIG") or os.path.join(ROOT, "config", "sources.json")
SNAPSHOT = os.path.join(ROOT, "site", "leads.json")
UA = "hms-housing-watch/1.0 (personal lead finder; once daily)"


@dataclass
class Lead:
    url: str
    source: str
    annotation: str
    checked_at: str
    first_seen: str = ""
    cross_posts: list = field(default_factory=list)


@dataclass
class SearchLink:
    url: str
    source: str
    link_kind: str = "live search"


@dataclass
class Source:
    name: str
    search_url: str
    mode: Literal["collect", "link_only"]
    parser: str = ""
    transport: str = "http"
    max_listings: int = 40
    delay_seconds: float = 2
    link_kind: str = "live search"
    searches: tuple = ()
    detail_limit: int = 12
    min_rent: int = 0


class SourceError(Exception):
    pass


def berlin_today():
    return datetime.now(ZoneInfo("Europe/Berlin")).date()


def load_config():
    with open(CONFIG) as f:
        cfg = json.load(f)
    fields = Source.__dataclass_fields__
    srcs = [Source(**{k: v for k, v in s.items() if k in fields}) for s in cfg["sources"]]
    return cfg, srcs


# ---- fetching -------------------------------------------------------------

def _fetch_http(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _fetch_cdp(url, proxy):
    """Fetch page HTML through the Mac-lane Chrome (needs `mac-lane.sh up`)."""
    import websockets  # imported lazily so http mode has no dependency

    req = urllib.request.Request(f"{proxy}/json/new?{url}", method="PUT")
    tab = json.loads(urllib.request.urlopen(req, timeout=10).read())

    async def run():
        async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=16 * 1024 * 1024) as ws:
            async def ev(expr):
                await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                          "params": {"expression": expr, "returnByValue": True}}))
                while True:
                    m = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
                    if m.get("id") == 1:
                        return m.get("result", {}).get("result", {}).get("value")
            for _ in range(30):
                await asyncio.sleep(1)
                if await ev("document.readyState") == "complete":
                    break
            return await ev("document.documentElement.outerHTML")

    try:
        html = asyncio.run(run())
    finally:
        try:
            urllib.request.urlopen(f"{proxy}/json/close/{tab['id']}", timeout=5).read()
        except Exception:
            pass
    if not html:
        raise SourceError(f"empty page from {url}")
    return html


def fetch(url, source, proxy, override=None):
    t = override or source.transport
    return _fetch_cdp(url, proxy) if t == "cdp" else _fetch_http(url)


# ---- RotatingRoom parser --------------------------------------------------

def _ldjson(html):
    out = []
    pattern = r'<script\b(?=[^>]*\btype\s*=\s*["\']application/ld\+json["\'])[^>]*>(.*?)</script\s*>'
    for m in re.findall(pattern, html, re.I | re.S):
        try:
            out.append(json.loads(m))
        except ValueError:
            pass
    return out


def listing_urls(html):
    for d in _ldjson(html):
        if d.get("@type") == "ItemList" and d.get("itemListElement"):
            return [i["url"] for i in d["itemListElement"] if "/need-a-room/" in i.get("url", "")]
    raise SourceError("RotatingRoom index: ItemList structured data not found (markup changed?)")


def parse_listing(html):
    """Return the minimum facts needed for an annotation; nothing else is kept."""
    docs = _ldjson(html)
    acc = next((d for d in docs if d.get("@type") == "Accommodation"), None)
    faq = next((d for d in docs if d.get("@type") == "FAQPage"), None)
    if not acc or not faq:
        raise SourceError("RotatingRoom listing: expected structured data missing (markup changed?)")
    facts = {"rent": None, "period": None, "ranges": [], "miles": None, "hood": None,
             "beds": acc.get("numberOfBedrooms")}
    offer = acc.get("offers") or {}
    spec = offer.get("priceSpecification") or {}
    if isinstance(offer.get("price"), (int, float)):
        facts["rent"] = offer["price"]
        facts["period"] = spec.get("unitCode")  # MON = per month
    for q in faq.get("mainEntity", []):
        text = q.get("acceptedAnswer", {}).get("text", "")
        if q.get("name", "").startswith("When is this listing available"):
            facts["ranges"] = re.findall(r"(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", text)
        m = re.search(r"Harvard Medical School, ([\d.]+) miles", text)
        if m:
            facts["miles"] = float(m.group(1))
    # Location: the breadcrumb is a site category and can conflict with the listing, so it is
    # ignored. Use the listing's own locality only when the FAQ rent answer names the same place;
    # otherwise omit the location.
    loc = (acc.get("address") or {}).get("addressLocality")
    rent_ans = next((q.get("acceptedAnswer", {}).get("text", "") for q in faq.get("mainEntity", [])
                     if q.get("name", "").startswith("How much is rent")), "")
    if loc and re.search(r"\bin " + re.escape(loc) + r", [A-Z]{2}\b", rent_ans):
        facts["hood"] = loc
    return facts


def normalize_lead(raw, source, stay, max_rent, today):
    """raw: {'url', 'facts'}; returns Lead or None if explicitly ineligible."""
    f = raw["facts"]
    stay_s, stay_e = stay
    if f["rent"] is not None and f["period"] in (None, "MON") and f["rent"] > max_rent:
        return None
    if f["period"] not in (None, "MON") and f["rent"] is not None:
        rent_txt = f"listed ${f['rent']:,.0f} but rent period unclear: confirm with host"
    elif f["rent"] is None:
        rent_txt = "rent not stated: confirm with host"
    else:
        rent_txt = f"${f['rent']:,.0f}/month stated"
    if f["ranges"]:
        if any(s <= stay_s and e >= stay_e for s, e in f["ranges"]):
            date_txt = "stated availability covers the full stay"
        else:
            return None  # explicit date mismatch
    else:
        date_txt = "availability dates not stated: confirm with host"
    parts = []
    if f["hood"]:
        parts.append(f["hood"])
    if f["miles"] is not None:
        parts.append(f"{f['miles']:g} mi straight-line from HMS (per site)")
    if f["beds"]:
        parts.append(f"{f['beds']} bd unit; confirm whether room or whole unit")
    parts += [rent_txt, date_txt, "listed as furnished sublet; confirm utilities and total cost"]
    return Lead(url=raw["url"], source=source.name, annotation="; ".join(parts) + ".",
                checked_at=today.isoformat())


def collect_rotatingroom(source, cfg, override):
    stay = (cfg["stay"]["start"], cfg["stay"]["end"])
    proxy = cfg["cdp_proxy"]
    for attempt in range(2):
        index = fetch(source.search_url, source, proxy, override)
        try:
            urls = listing_urls(index)[: source.max_listings]
            break
        except SourceError:
            if attempt == 1:
                raise
            # The public page can finish navigation before its structured
            # result data is present. Retry once; keep failures fail-closed.
            time.sleep(3)
    if not urls:
        raise SourceError("RotatingRoom index returned no listings")
    leads, today = [], berlin_today()
    stats = {"source": source.name, "checked": 0, "over_budget": 0, "date_mismatch": 0, "eligible": 0}
    max_rent = cfg["budget"]["max_monthly"]
    for u in urls:
        time.sleep(source.delay_seconds)
        try:
            facts = parse_listing(fetch(u, source, proxy, override))
        except SourceError:
            raise
        except Exception as e:  # network/CDP error: fail the whole source
            raise SourceError(f"listing fetch failed for {u}: {e}")
        stats["checked"] += 1
        if facts["rent"] is not None and facts["period"] in (None, "MON") and facts["rent"] > max_rent:
            stats["over_budget"] += 1
        elif facts["ranges"] and not any(s <= stay[0] and e >= stay[1] for s, e in facts["ranges"]):
            stats["date_mismatch"] += 1
        lead = normalize_lead({"url": u, "facts": facts}, source, stay, max_rent, today)
        if lead:
            stats["eligible"] += 1
            leads.append(lead)
    return leads, stats


# ---- Craigslist browser-bridge parser (owner-approved 2026-10-17) ---------
# Read-only Mac-lane CDP pass over public room searches. Original short
# annotations from extracted facts only; no ad text, titles, photos, or
# contact details. Judgment filters mirror the Oct 16 one-time brief.

_CL_HOOD_RANK = {"brookline": 0, "mission hill": 0, "longwood": 0, "roxbury": 1,
                 "jamaica plain": 1, "fenway": 1, "allston": 2, "brighton": 2,
                 "somerville": 2, "cambridge": 2, "medford": 3, "boston": 3}


_CL_TWO_WORD_TOWNS = ("brookline village", "jamaica plain", "mission hill", "roxbury crossing")


def _cl_town(url, fallback):
    m = re.search(r"/view/d/([a-z]+(?:-[a-z]+){0,2})-", url)
    if not m:
        return fallback
    slug = m.group(1).replace("-", " ")
    for t in _CL_TWO_WORD_TOWNS:
        if slug.startswith(t):
            return t.title()
    first = slug.split(" ")[0]
    if first in _CL_HOOD_RANK or first in ("braintree", "watertown", "dorchester", "chelsea", "quincy", "malden", "everett", "arlington", "belmont", "newton", "waltham"):
        return first.title()
    return fallback


def _cl_rank(loc):
    loc = (loc or "").lower()
    return next((r for k, r in _CL_HOOD_RANK.items() if k in loc), 9)


def _cl_cards(html):
    out = []
    for m in re.finditer(
            r'data-pid="(\d+)".*?href="(https://www\.craigslist\.org/view/d/[^"]+)"'
            r'.*?result-posted-date">([^<]*)</span>.*?result-location">([^<]*)</span>.*?priceinfo">\$?([0-9,]+)',
            html, re.S):
        pid, url, _posted, loc, price = m.groups()
        out.append({"pid": pid, "url": url, "loc": loc.strip(), "price": int(price.replace(",", ""))})
    return out


def _cl_facts(html):
    import html as htmllib
    body = re.search(r'id="postingbody"(.*?)</section>', html, re.S)
    raw = re.sub(r"<[^>]+>", " ", body.group(1) if body else html)
    low = re.sub(r"\s+", " ", htmllib.unescape(raw)).lower()
    facts = []
    if "furnished" in low:
        facts.append("furnished")
    if re.search(r"utilities included|all utilities|incl\.? utilities", low):
        facts.append("utilities included per ad")
    if re.search(r"available (now|immediately)", low):
        facts.append("available now per ad")
    if re.search(r"short.?term|month.to.month|flexible lease|sublet", low):
        facts.append("short-term/flexible mentioned")
    if re.search(r"private bath|own bathroom|ensuite|en-suite", low):
        facts.append("private bath")
    if "laundry" in low:
        facts.append("laundry mentioned")
    long_lease = bool(re.search(r"1 year lease|12 month|one year lease|year lease required", low))
    return facts, long_lease


def collect_craigslist_browser(source, cfg, override):
    proxy = cfg["cdp_proxy"]
    max_rent = cfg["budget"]["max_monthly"]
    seen, pool, scanned, filtered = {}, [], 0, 0
    for q in source.searches:
        url = f"https://boston.craigslist.org/search/roo?query={q.replace(' ', '%20')}&max_price={max_rent}&sort=date"
        cards = _cl_cards(fetch(url, source, proxy, override))
        if not cards:  # SPA render race: one slow retry before failing the source
            time.sleep(10)
            cards = _cl_cards(fetch(url, source, proxy, override))
        if not cards:
            raise SourceError(f"Craigslist search '{q}': no result cards (markup changed?)")
        scanned += len(cards)
        for c in cards:
            if c["pid"] in seen:
                continue
            seen[c["pid"]] = c
            c["town"] = _cl_town(c["url"], c["loc"])
            if source.min_rent <= c["price"] <= max_rent and _cl_rank(c["town"]) < 9:
                pool.append(c)
            else:
                filtered += 1
        time.sleep(source.delay_seconds)
    pool.sort(key=lambda c: (_cl_rank(c["town"]), c["price"]))
    leads, today = [], berlin_today()
    for c in pool[: source.detail_limit]:
        time.sleep(source.delay_seconds)
        facts, long_lease = _cl_facts(fetch(c["url"], source, proxy, override))
        parts = [c["town"], f"${c['price']:,}/month shown"] + facts
        if long_lease:
            parts.append("long lease mentioned — only if a Nov 9–Apr 19 sublet is authorized")
        parts.append("dates/utilities not verified: confirm exact stay dates, total cost, and sublet authorization with host")
        leads.append(Lead(url=c["url"], source=source.name, annotation="; ".join(parts) + ".",
                          checked_at=today.isoformat()))
    stats = {"source": source.name, "checked": scanned, "over_budget": filtered,
             "date_mismatch": 0, "eligible": len(leads)}
    return leads, stats


def collect_browser_source(source, cfg, override):
    from browser_sources import collect
    if override and override != "cdp":
        raise SourceError("This source requires Mac-lane CDP")
    documents, stats = collect(source, cfg)
    return [Lead(**doc) for doc in documents], stats


PARSERS = {"rotatingroom": collect_rotatingroom, "craigslist_browser": collect_craigslist_browser}
PARSERS.update({name: collect_browser_source for name in (
    "furnishedfinder", "roomies", "spareroom", "airbnb", "sabbaticalhomes",
    "zillow", "apartments", "harvard", "craigslist_sublets")})


# ---- orchestration --------------------------------------------------------

def canonical_listing_key(url):
    """Build a stable identity for a listing URL without its tracking data."""
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise SourceError(f"invalid listing URL: {url!r}")

    host = parsed.hostname.lower().rstrip(".")
    # Craigslist may return the same post on a regional or www hostname.
    if host.endswith(".craigslist.org"):
        host = "craigslist.org"
    elif host.startswith("www."):
        host = host[4:]

    port = parsed.port
    if port and not ((parsed.scheme.lower() == "http" and port == 80) or
                     (parsed.scheme.lower() == "https" and port == 443)):
        host = f"{host}:{port}"

    # URL paths are case-sensitive. Decode only percent-encoded unreserved
    # characters, normalize the hex case of other escapes, and ignore query,
    # fragment, and trailing slash differences.
    unreserved = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    path = re.sub(
        r"%([0-9a-fA-F]{2})",
        lambda m: (chr(int(m.group(1), 16)) if chr(int(m.group(1), 16)) in unreserved
                   else "%" + m.group(1).upper()),
        parsed.path,
    )
    path = path.rstrip("/") or "/"
    if host == "spareroom.com":
        ids = [(k, v) for k, v in parse_qsl(parsed.query) if k == "flatshare_id"]
        if ids:
            return host + "/listing?" + urlencode(ids)
    if host == "craigslist.org" and "/view/d/" in path:
        return host + "/listing/" + path.rsplit("/", 1)[-1]
    return host + path


def dedupe_leads(leads, duplicate_groups=None):
    """Merge URL aliases and explicitly reviewed cross-posts, keeping provenance."""
    aliases = {}
    for index, group in enumerate(duplicate_groups or []):
        for url in group["urls"]:
            aliases[canonical_listing_key(url)] = f"reviewed-group:{index}"
    unique, seen = [], {}
    for lead in leads:
        canonical = canonical_listing_key(lead.url)
        key = aliases.get(canonical, canonical)
        if key in seen:
            primary = seen[key]
            if canonical != canonical_listing_key(primary.url):
                primary.cross_posts.append({"url":lead.url, "source":lead.source,
                    "annotation":lead.annotation, "checked_at":lead.checked_at,
                    "first_seen":lead.first_seen})
            continue
        seen[key] = lead
        unique.append(lead)
    return unique, len(leads) - len(unique)


def collect_sources(override=None, prior_snapshot=None):
    cfg, sources = load_config()
    if prior_snapshot is None:
        try:
            with open(SNAPSHOT) as stream:
                prior_snapshot = json.load(stream)
        except FileNotFoundError:
            prior_snapshot = {"leads": []}
    previous = list(prior_snapshot.get("leads", []))
    for lead in prior_snapshot.get("leads", []):
        previous.extend(lead.get("cross_posts", []))
    leads, links, checked, successes = [], [], [], 0
    fresh_sources = set()
    for source in sources:
        links.append(SearchLink(url=source.search_url, source=source.name, link_kind=source.link_kind))
        if source.mode == "link_only":
            continue
        print(f"checking {source.name}", flush=True)
        try:
            if source.parser not in PARSERS:
                raise SourceError(f"Unknown parser: {source.parser}")
            got, stats = PARSERS[source.parser](source, cfg, override)
            stats["status"] = "ok"
            stats["checked_at"] = berlin_today().isoformat()
            successes += 1
            fresh_sources.add(source.name)
            leads.extend(got)
            print(f"  {len(got)} retained after eligibility checks", flush=True)
        except Exception as error:
            retained = [Lead(**{k:v for k,v in old.items() if k in Lead.__dataclass_fields__})
                        for old in previous if old.get("source") == source.name]
            for old in retained:
                old.cross_posts = []
            leads.extend(retained)
            stats = {"source":source.name, "status":"failed", "retained":len(retained)}
            print(f"  failed; retaining {len(retained)} previously checked leads: {error}", flush=True)
        checked.append(stats)
    if not successes:
        raise SourceError("Every collection source failed; previous snapshot preserved")
    # Prefer a freshly checked alias when a cross-post's other source failed.
    leads.sort(key=lambda lead: (lead.source in fresh_sources, lead.checked_at), reverse=True)
    collected_count = len(leads)
    leads, duplicates_removed = dedupe_leads(leads, cfg.get("duplicate_groups"))
    checked.append({"source":"Deduplication", "checked":collected_count,
                    "duplicates_removed":duplicates_removed, "eligible":len(leads)})
    return cfg, leads, links, checked


def _berlin_day(generated_at):
    from zoneinfo import ZoneInfo
    return datetime.fromisoformat(generated_at).astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()


def _atomic_json(doc, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    with open(tmp) as stream:
        json.load(stream)  # validate before replacing
    os.replace(tmp, path)


def write_successful_snapshot(cfg, leads, search_links, generated_at, path=SNAPSHOT, checked=None):
    day = _berlin_day(generated_at)
    prior_first_seen = {}
    aliases = {canonical_listing_key(url): f"reviewed-group:{index}"
               for index, group in enumerate(cfg.get("duplicate_groups", []))
               for url in group["urls"]}

    def identity(url):
        key = canonical_listing_key(url)
        return aliases.get(key, key)

    def remember(listings, fallback=""):
        for listing in listings:
            key = identity(listing["url"])
            seen = listing.get("first_seen") or fallback
            if seen and (key not in prior_first_seen or seen < prior_first_seen[key]):
                prior_first_seen[key] = seen
            remember(listing.get("cross_posts", []), seen)

    if os.path.exists(path):
        with open(path) as stream:
            remember(json.load(stream).get("leads", []))
    hist_path = os.path.join(os.path.dirname(path), "history.json")
    days = []
    if os.path.exists(hist_path):
        with open(hist_path) as stream:
            days = json.load(stream).get("days", [])
        for previous_day in days:
            remember(previous_day.get("leads", []), previous_day.get("date", ""))
    for lead in leads:
        lead.first_seen = prior_first_seen.get(identity(lead.url), lead.first_seen or day)
        for cross_post in lead.cross_posts:
            cross_post["first_seen"] = prior_first_seen.get(identity(cross_post["url"]), lead.first_seen)
    lead_docs = [asdict(l) for l in leads]
    doc = {"generated_at": generated_at, "day": day, "stay": cfg["stay"], "budget": cfg["budget"],
           "snapshot_status": "partial" if any(s.get("status") == "failed" for s in (checked or [])) else "complete",
           "checked": checked or [], "leads": lead_docs,
           "search_links": [asdict(s) for s in search_links]}
    _atomic_json(doc, path)
    # Day-by-day archive next to the snapshot; same Berlin day replaces, cap 90 days.
    days = [d for d in days if d.get("date") != day]
    days.append({"date": day, "generated_at": generated_at, "checked": checked or [], "leads": lead_docs})
    days.sort(key=lambda d: d["date"])
    _atomic_json({"days": days[-90:]}, hist_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=["cdp", "http"])
    ap.add_argument("--output", default=SNAPSHOT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        prior = None
        if a.output != SNAPSHOT:
            prior = {"leads": []}
            if os.path.exists(a.output):
                with open(a.output) as stream:
                    prior = json.load(stream)
        cfg, leads, links, checked = collect_sources(a.transport, prior_snapshot=prior)
    except Exception as e:
        print(f"refresh failed; snapshot unchanged: {e}", file=sys.stderr)
        return 1
    generated_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    print(f"{len(leads)} eligible leads, {len(links)} search links at {generated_at}")
    dedupe_stats = next((s for s in checked if s["source"] == "Deduplication"), None)
    if dedupe_stats:
        print(f"deduplication: removed {dedupe_stats['duplicates_removed']} duplicate listing(s) "
              f"from {dedupe_stats['checked']} collected")
    if not a.dry_run:
        write_successful_snapshot(cfg, leads, links, generated_at, a.output, checked)
    return 0


if __name__ == "__main__":
    sys.exit(main())
