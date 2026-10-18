#!/usr/bin/env python3
"""PROTOTYPE: browser-bridge (Mac-lane CDP) daily pass, brief-style output.

Replicates the shape of the one-time Oct 16 research brief: drive the real
Mac Chrome via the bridge proxy, read public Craigslist Boston room searches,
open a few promising detail pages, and write an original-annotation table.
Read-only: no sign-in, forms, messages, favorites, or clicks beyond navigation.
Short extracted facts only; no ad text, photos, titles, or contact details.
Output: --out PATH (default beside this script/../var/prototype/index.html); tailnet review only.
"""
import html as htmllib
import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily_refresh as dr  # reuses the bridge CDP fetch + config

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_RENT = 1400
DETAIL_LIMIT = 12
SEARCHES = ["brookline", "mission hill", "longwood", "somerville"]


def text_of(html):
    body = re.search(r'id="postingbody"(.*?)</section>', html, re.S)
    raw = body.group(1) if body else html
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", htmllib.unescape(raw)).strip()


def parse_cards(html):
    cards = []
    for m in re.finditer(
            r'data-pid="(\d+)"[^>]*title="([^"]*)".*?href="(https://www\.craigslist\.org/view/d/[^"]+)"'
            r'.*?result-posted-date">([^<]*)</span>.*?result-location">([^<]*)</span>.*?priceinfo">\$?([0-9,]+)',
            html, re.S):
        pid, _title, url, posted, loc, price = m.groups()
        cards.append({"pid": pid, "url": url, "posted": posted.strip(),
                      "loc": loc.strip(), "price": int(price.replace(",", ""))})
    return cards


def detail_facts(html):
    t = text_of(html)
    low = t.lower()
    facts = []
    if "furnished" in low:
        facts.append("furnished")
    if re.search(r"utilities included|all utilities|incl\.? utilities", low):
        facts.append("utilities included")
    if re.search(r"available (now|immediately)", low):
        facts.append("available now")
    m = re.search(r"available (?:from |on |starting )?((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2})", low)
    if m:
        facts.append(f"available {m.group(1)}")
    if re.search(r"short.?term|month.to.month|flexible lease|sublet", low):
        facts.append("short-term/flexible mentioned")
    if re.search(r"1 year lease|12 month|one year lease|year lease required", low):
        facts.append("long lease mentioned — date fit unlikely")
    if re.search(r"private bath|own bathroom|ensuite|en-suite", low):
        facts.append("private bath")
    if "laundry" in low:
        facts.append("laundry mentioned")
    return facts


def fit_note(card, facts):
    good = [f for f in facts if "unlikely" not in f]
    bits = []
    if card["price"] <= 1200:
        bits.append("At/under the $1,200 target before utilities.")
    else:
        bits.append("Within the $1,400 stretch ceiling before utilities.")
    if good:
        bits.append("Ad states: " + ", ".join(good) + ".")
    if any("unlikely" in f for f in facts):
        bits.append("Lease length looks mismatched; only pursue if a Nov 9–Apr 19 sublet is authorized.")
    bits.append("Confirm exact Nov 9–Apr 19 dates, total monthly cost, sublet authorization, and get a live video tour.")
    return " ".join(bits)


def main():
    cfg, _ = dr.load_config()
    proxy = cfg["cdp_proxy"]
    seen, pool = {}, []
    per_search = {}
    for q in SEARCHES:
        url = f"https://boston.craigslist.org/search/roo?query={q.replace(' ', '%20')}&max_price={MAX_RENT}&sort=date"
        page = dr._fetch_cdp(url, proxy)
        cards = parse_cards(page)
        per_search[q] = len(cards)
        for c in cards:
            if c["pid"] not in seen and 0 < c["price"] <= MAX_RENT:
                seen[c["pid"]] = c
                pool.append(c)
        time.sleep(3)
    # Judgment pass, mirroring the one-time brief: drop sub-$600 (weekly-rate or
    # scam-pattern ads), keep HMS-commutable neighborhoods, rank close-in first.
    hood_rank = {"brookline": 0, "mission hill": 0, "longwood": 0, "roxbury": 1,
                 "jamaica plain": 1, "fenway": 1, "allston": 2, "brighton": 2,
                 "somerville": 2, "cambridge": 2, "medford": 3, "boston": 3}
    def rank(c):
        loc = (c["loc"] or "").lower()
        return next((r for k, r in hood_rank.items() if k in loc), 9)
    pool = [c for c in pool if c["price"] >= 600 and rank(c) < 9]
    pool.sort(key=lambda c: (rank(c), c["price"]))
    rows = []
    for c in pool[:DETAIL_LIMIT]:
        time.sleep(3)
        try:
            facts = detail_facts(dr._fetch_cdp(c["url"], proxy))
        except Exception as e:
            facts = [f"detail read failed ({e})"]
        rows.append((c, facts))
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    trs = []
    for c, facts in rows:
        label = f"{c['loc'] or 'Boston'} room — ${c['price']:,}/month"
        terms = f"${c['price']:,}/month shown; posted {c['posted']}; " + ("; ".join(facts) if facts else "few terms stated in ad")
        trs.append(f"<tr><td><a href=\"{c['url']}\" rel=\"noopener noreferrer\" target=\"_blank\">{htmllib.escape(label)}</a></td>"
                   f"<td>{htmllib.escape(terms)}.</td><td>{htmllib.escape(fit_note(c, facts))}</td></tr>")
    searched = ", ".join(f"{q} ({n} cards)" for q, n in per_search.items())
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prototype — browser-bridge daily pass</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:0;background:#fafaf7;color:#1b1b1f}}
main{{max-width:64rem;margin:0 auto;padding:1.25rem 1rem 3rem}} table{{border-collapse:collapse;width:100%}}
th,td{{border-top:1px solid #dcdcd4;padding:.6rem .5rem;text-align:left;vertical-align:top;font-size:.95rem}}
.note{{color:#5d5d66;border-left:3px solid #dcdcd4;padding-left:.75rem}}</style></head><body><main>
<h1>Short-term housing leads near Harvard Medical School — prototype</h1>
<p class="note">Prototype generated {now} by a read-only Mac-lane browser-bridge pass
(Craigslist Boston rooms: {searched}; {len(pool)} unique in-budget rooms; first {len(rows)} opened).
Stay needed: Nov 9, 2026–Apr 19, 2027. Target $1,200/month, stretch $1,400.
These are unverified live ads, not vetted or endorsed housing; confirm each directly.
Nothing here is on the public page.</p>
<h2>Best current leads (cheapest first)</h2>
<table><tr><th>Lead</th><th>Listed terms</th><th>Why it may fit / what to confirm</th></tr>
{''.join(trs)}
</table></main></body></html>"""
    out = sys.argv[sys.argv.index("--out")+1] if "--out" in sys.argv else os.path.join(HERE, "..", "var", "prototype", "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(doc)
    print(json.dumps({"searched": per_search, "unique_in_budget": len(pool), "opened": len(rows), "out": out}))


if __name__ == "__main__":
    main()
