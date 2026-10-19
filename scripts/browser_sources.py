"""Bounded, read-only checks of rendered public pages on the Mac-lane.

Only URLs, original factual annotations, and check dates leave this module.
Page text is transient; no account actions, contacts, photos, or raw ads are saved.
"""
import asyncio
import json
import re
import time
import urllib.request
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo
from datetime import datetime


class BrowserSourceError(Exception):
    pass


class UnsupportedRentPeriod(BrowserSourceError):
    pass


# Use rendered cards, never embedded/private API responses. Some platforms put
# the card link around its image only, so inspect nearby rendered ancestors.
PAGE_SCRIPT = r"""(() => {
 const kind = __KIND__;
 const patterns = {
  furnishedfinder: /\/property\/[\w-]+/,
  roomies: /\/rooms\/\d+/,
  spareroom: /room_for_rent\.pl\?.*flatshare_id=\d+/,
  airbnb: /\/rooms\/\d+/,
  sabbaticalhomes: /\/rental\/\d+/i,
  zillow: /\/homedetails\//,
  apartments: /\/[^/]+\/[a-z0-9]+\/$/,
  harvard: /\/housing\/property\//,
  craigslist_sublets: /\/view\/d\//
 };
 const seen = new Set(), cards = [];
 for (const a of document.querySelectorAll('a[href]')) {
  if (!patterns[kind].test(a.href)) continue;
  const u = new URL(a.href);
  if (u.hostname !== location.hostname && !u.hostname.endsWith('.craigslist.org')) continue;
  let key = kind === 'spareroom' ? u.searchParams.get('flatshare_id') : u.pathname;
  if (seen.has(key)) continue;
  let text = '';
  for (let p = a, n = 0; p && n < 8; p = p.parentElement, n++) {
   const t = (p.innerText || '').trim();
   if (t.length > 5000) break;
   if (/\$[\d,]+/.test(t) && t.length > 25) { text = t; break; }
  }
  if (!text) text = a.getAttribute('aria-label') || a.querySelector('img')?.alt || '';
  if (!text || !/\$[\d,]+/.test(text)) continue;
  seen.add(key);
  cards.push({url:a.href, text:text.slice(0,5000)});
  if (cards.length >= __LIMIT__) break;
 }
 return {url:location.href, title:document.title,
         text:(document.body?.innerText || '').slice(0,180000), cards};
})()"""


class Browser:
    def __init__(self, proxy, kind, max_listings=40):
        self.proxy = proxy.rstrip('/')
        self.kind = kind
        self.max_listings = max_listings

    def read(self, url):
        # Navigate by CDP after creating about:blank: this preserves every URL
        # query parameter and avoids treating the initial empty document as ready.
        req = urllib.request.Request(self.proxy + '/json/new?about:blank', method='PUT')
        tab = json.loads(urllib.request.urlopen(req, timeout=15).read())
        async def run():
            import websockets
            async with websockets.connect(tab['webSocketDebuggerUrl'], max_size=16*1024*1024) as ws:
                ident = 0
                async def command(method, params):
                    nonlocal ident
                    ident += 1
                    current = ident
                    await ws.send(json.dumps({'id':current, 'method':method, 'params':params}))
                    while True:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=25))
                        if msg.get('id') == current:
                            if 'error' in msg:
                                raise BrowserSourceError('Browser command failed')
                            return msg.get('result', {})
                async def evaluate(expression):
                    result = await command('Runtime.evaluate', {'expression':expression, 'returnByValue':True})
                    if result.get('exceptionDetails'):
                        raise BrowserSourceError('Rendered page could not be read')
                    return result.get('result', {}).get('value')
                navigation = await command('Page.navigate', {'url':url})
                if navigation.get('errorText'):
                    raise BrowserSourceError('Browser navigation failed')
                for _ in range(35):
                    await asyncio.sleep(1)
                    ready = await evaluate("location.protocol.startsWith('http') && document.readyState === 'complete' && (document.body?.innerText.length || 0) > 200")
                    if ready:
                        break
                else:
                    raise BrowserSourceError('Page did not finish rendering')
                await asyncio.sleep(2)  # allow client-rendered cards to settle
                script = PAGE_SCRIPT.replace('__KIND__', json.dumps(self.kind)).replace('__LIMIT__', str(self.max_listings))
                if self.kind == 'airbnb' and '/rooms/' in url:
                    # The booking quote hydrates after the rest of the listing.
                    for _ in range(10):
                        if await evaluate(r"/\$[\d,]+\s*monthly/.test(document.body.innerText)"):
                            break
                        await asyncio.sleep(1)
                page = await evaluate(script)
                if not page or not page.get('text'):
                    raise BrowserSourceError('Empty rendered page')
                heading = (page['title'] + '\n' + page['text'][:400]).lower()
                if re.search(r'access denied|verify you are human|press.*hold|robot or human|just a moment|captcha challenge', heading):
                    raise BrowserSourceError('Access challenge; no bypass attempted')
                return page
        try:
            return asyncio.run(run())
        finally:
            try:
                urllib.request.urlopen(self.proxy + '/json/close/' + tab['id'], timeout=5).read()
            except Exception:
                pass


def clean_url(url, kind):
    p = urlsplit(url)
    # SpareRoom IDs are semantic query parameters, unlike tracking parameters.
    query = urlencode([(k,v) for k,v in parse_qsl(p.query) if k == 'flatshare_id']) if kind == 'spareroom' else ''
    return urlunsplit((p.scheme, p.netloc, p.path.rstrip('/'), query, ''))


def monthly_price(kind, text):
    range_price = re.search(r'\$[\d,]+\s*[-–]\s*\$([\d,]+)\s*(?:/\s*(?:month|Bedroom)|monthly)', text, re.I)
    if range_price:
        return int(range_price.group(1).replace(',', ''))
    patterns = {
        'furnishedfinder': r'\$([\d,]+)\s*/\s*month',
        'roomies': r'(?:Rent\s*)?\$([\d,]+)\s*(?:per month|inc\.)',
        'spareroom': r'\$([\d,]+)\s*(?:monthly|/month)',
        'airbnb': r'\$([\d,]+)\s*monthly',
        'sabbaticalhomes': r'(?:From USD|Rates from USD)\s*\$([\d,]+)\s*(?:\||/)\s*Monthly',
        'zillow': r'\$([\d,]+)\s*/mo',
        'apartments': r'\$([\d,]+)(?:\+)?\s*(?:Plus Fees|Total Monthly Price|\n)',
        'harvard': r'\$([\d,]+)(?:\s*-\s*\$[\d,]+)?\s*/\s*Bedroom',
        'craigslist_sublets': r'\$([\d,]+)',
    }
    match = re.search(patterns[kind], text, re.I)
    if not match:
        # Range cards use the upper advertised rent to avoid passing an
        # over-budget room just because another room in the card is cheaper.
        match = re.search(r'\$[\d,]+\s*[-–]\s*\$([\d,]+)\s*/month', text, re.I)
    if not match:
        raise BrowserSourceError('Monthly rent missing or unsupported')
    return int(match.group(1).replace(',', ''))


MONTHS = {m:i for i,m in enumerate(('jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),1)}
DATE_WORDS = r'([A-Z][a-z]+)\.?\s+(\d{1,2})(?:,?\s+(20\d{2}))?'


def parsed_date(match, year):
    month, day, explicit_year = match.groups()
    number = MONTHS.get(month[:3].lower())
    if not number:
        return None
    return date(int(explicit_year or year), number, int(day))


def assess_listing(kind, text, cfg):
    # Similar-listing cards must not supply the primary listing's rent/dates.
    text = re.split(r'Similar rentals|Nearby apartments for rent|Other Nearby Rentals', text, flags=re.I)[0]
    if kind == 'craigslist_sublets' and not re.search(r'rent period:\s*monthly|/mo(?:nth)?|\bmonthly\b', text, re.I):
        raise UnsupportedRentPeriod('Listing does not state a monthly rent period')
    if kind == 'airbnb' and re.search(r'Add dates for prices', text, re.I) and not re.search(r'\$[\d,]+\s*monthly', text):
        return None, 'quote_unavailable'
    rent = monthly_price(kind, text)
    start, end = (date.fromisoformat(cfg['stay'][k]) for k in ('start','end'))
    duration = (end-start).days
    extra = re.search(r'(?:plus\s+)?utilities\s*\(\$([\d,]+)\)', text, re.I)
    extra_rent = int(extra.group(1).replace(',', '')) if extra else 0
    if rent + extra_rent > cfg['budget']['max_monthly']:
        return None, 'over_budget'
    if kind == 'airbnb':
        checkin = re.search(r'CHECK-IN\s*(\d{1,2}/\d{1,2}/20\d{2})', text)
        checkout = re.search(r'CHECKOUT\s*(\d{1,2}/\d{1,2}/20\d{2})', text)
        if not checkin or not checkout:
            raise BrowserSourceError('Airbnb exact-date quote unavailable')
        dates = [datetime.strptime(m.group(1), '%m/%d/%Y').date() for m in (checkin, checkout)]
        if dates != [start,end]:
            return None, 'date_mismatch'
        date_note = 'displayed quote for the exact stay dates; reconfirm final total and cancellation terms'
    else:
        available = re.search(r'\bAvailable(?: on| from)?\s*:?\s*' + DATE_WORDS, text, re.I)
        if available:
            when = parsed_date(available, start.year)
            if when and when > start:
                return None, 'date_mismatch'
        until = re.search(r'\buntil\s+' + DATE_WORDS, text, re.I)
        if until:
            when = parsed_date(until, end.year)
            if when and when < end:
                return None, 'date_mismatch'
        flexible = bool(re.search(r'negotiable|flexible|short rentals considered|short.term', text, re.I))
        if not flexible and re.search(r'\b(?:1|one) year lease|\b12.month lease', text, re.I):
            return None, 'date_mismatch'
        for label, is_min in [('Minimum (?:stay|term)', True), ('Maximum (?:stay|term)', False)]:
            term = re.search(label + r'\s*:?\s*(\d+)\s*(day|month|year)s?', text, re.I)
            if term:
                count, unit = int(term.group(1)), term.group(2).lower()
                days = count * {'day':1,'month':30,'year':365}[unit]
                if (is_min and days > duration) or (not is_min and days < duration):
                    return None, 'date_mismatch'
        date_note = 'confirm the exact full stay dates and authorization with the host'
    parts = [f'${rent:,}/month advertised']
    low = text.lower()
    if re.search(r'not furnished|unfurnished', low):
        parts.append('unfurnished stated')
    elif 'furnished' in low or kind in ('furnishedfinder','airbnb'):
        parts.append('furnished listing')
    if re.search(r'utilities\s*:\s*included|bills\s+included|utilities included\?\s*yes|utilities are included|all utilities included', text, re.I):
        parts.append('utilities included per listing')
    else:
        parts.append('confirm utilities and all additional charges')
    term = re.search(r'Minimum (?:stay|term)\s*:?\s*(\d+)\s*(month|day|year)s?', text, re.I)
    if term:
        parts.append(f'minimum stay {term.group(1)} {term.group(2).lower()}s')
    # Do not infer that a headline is the applicable rent when its own prose
    # quotes a different rental amount, as on the South Whitney cross-post.
    other = re.search(r'Rental\s*:\s*\$([\d,]+)', text, re.I)
    if other and int(other.group(1).replace(',', '')) != rent:
        parts.append('conflicting advertised prices; confirm the applicable rent')
    if kind == 'sabbaticalhomes' and len(set(re.findall(r'30\s*[-–]\s*(\d+)\s*days', text, re.I))) > 1:
        parts.append('conflicting stay limits; confirm duration')
    area = next((x for x in ('Longwood','Mission Hill','Fenway','Jamaica Plain','Brookline','Roslindale','Watertown','Somerville','Brighton','Cambridge','Dorchester','Medford','Boston') if x.lower() in text[:2500].lower()), None)
    if area:
        parts.insert(0, area)
    parts.append(date_note)
    return '; '.join(parts) + '.', 'eligible'


def search_url(source, cfg):
    if source.parser == 'airbnb':
        return source.search_url.split('?')[0] + '?' + urlencode({
            'checkin':cfg['stay']['start'], 'checkout':cfg['stay']['end'],
            'adults':1, 'room_types[]':'Private room'})
    if source.parser == 'spareroom':
        start = date.fromisoformat(cfg['stay']['start'])
        return source.search_url.split('?')[0] + '?' + urlencode({
            'search':'Boston', 'flatshare_type':'offered', 'searchtype':'simple', 'action':'search',
            'max_rent':cfg['budget']['max_monthly'], 'furnished':'Y', 'short_lets_considered':'Y',
            'available_search':'Y','day_avail':f'{start.day:02}','mon_avail':f'{start.month:02}', 'year_avail':start.year})
    return source.search_url


def collect(source, cfg):
    if source.transport != 'cdp':
        raise BrowserSourceError('This source requires the real-browser transport')
    browser = Browser(cfg['cdp_proxy'], source.parser, source.max_listings)
    page = browser.read(search_url(source,cfg))
    cards = page['cards']
    if not cards:
        if re.search(r'\b0 (?:rooms|rentals|results)|no (?:matching )?(?:results|rentals|rooms) found', page['text'], re.I):
            return [], {'source':source.name,'checked':0,'over_budget':0,'date_mismatch':0,'eligible':0}
        raise BrowserSourceError('No rendered listing cards; source layout or access changed')
    stats = {'source':source.name,'checked':len(cards),'over_budget':0,'date_mismatch':0,'eligible':0,'details_checked':0}
    pool = []
    recognized = 0
    for card in cards:
        try:
            price = monthly_price(source.parser,card['text'])
            recognized += 1
        except BrowserSourceError:
            continue
        if price > cfg['budget']['max_monthly']:
            stats['over_budget'] += 1
            continue
        if price < max(source.min_rent,600):
            continue
        # Familiar medical-area names first, followed by other in-budget rooms.
        rank = next((i for i,n in enumerate(('longwood','mission hill','fenway','brookline','jamaica plain')) if n in card['text'].lower()),5)
        pool.append((rank,price,card))
    if not recognized:
        raise BrowserSourceError('Listing cards found but none had a supported monthly rent')
    pool.sort(key=lambda row:(row[0],row[1]))
    leads = []
    today = datetime.now(ZoneInfo('Europe/Berlin')).date().isoformat()
    for _,_,card in pool[:source.detail_limit]:
        time.sleep(source.delay_seconds)
        url = clean_url(card['url'],source.parser)
        visit_url = url
        if source.parser == 'airbnb':
            visit_url += '?' + urlencode({'check_in':cfg['stay']['start'],'check_out':cfg['stay']['end'],'adults':1})
        detail = browser.read(visit_url)
        stats['details_checked'] += 1
        try:
            note, reason = assess_listing(source.parser, detail['text'], cfg)
        except UnsupportedRentPeriod:
            stats['rent_period_unknown'] = stats.get('rent_period_unknown',0) + 1
            continue
        if note is None:
            stats[reason] = stats.get(reason,0) + 1
            continue
        leads.append({'url':visit_url,'source':source.name,'annotation':note,'checked_at':today})
    stats['eligible'] = len(leads)
    return leads, stats
