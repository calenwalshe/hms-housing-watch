# HMS Short-Term Housing Watch

Public room/sublet leads near Harvard Medical School for **November 9, 2026–April 19, 2027**.
Target $1,200/month; stretch ceiling $1,400/month. Listings are leads for host confirmation,
not verified or endorsed housing. Live page: https://calenwalshe.github.io/hms-housing-watch/

## Daily operation

The enabled `hms-housing-watch.timer` runs at **05:00 Europe/Berlin every day**. The named
IANA timezone follows German daylight-saving changes automatically. Persistent catch-up is enabled.
The service has a 30-minute runtime cap and a single-run lock. Mac-lane wakes the cgl MacBook Air,
keeps it awake, and reads public pages through its real Chrome browser.

Collection sources, including the expansion explicitly requested by the owner on 2026-10-19:

| Source | Search coverage |
|---|---|
| RotatingRoom Boston | Structured public index and up to 40 listing pages |
| Craigslist Boston rooms | Four neighborhood searches, up to 12 detail pages |
| Craigslist Boston sublets | First 80 rendered cards, up to 6 detail pages |
| Furnished Finder Boston | Rendered Boston results, up to 6 detail pages |
| Roomies Boston | Rendered Boston room results, up to 6 detail pages |
| SpareRoom Boston | Furnished, short-term Boston search; up to 6 detail pages |
| Airbnb Boston | Private rooms with the exact configured stay dates; up to 6 detail pages |
| SabbaticalHomes Boston/Cambridge | Public city directory, up to 6 in-budget detail pages |
| Zillow Boston rooms | Rendered room results, up to 6 detail pages |
| Apartments.com Boston | Under-$1,400 search, up to 6 detail pages |
| Harvard off-campus portal | Public housing results, up to 6 detail pages |

The HMS Housing and Dining and Harvard University Housing information pages remain resource links.
Collection is bounded and does not promise to cover every result or page. Requests are spaced by the
configured source delay. Source policies and the owner's recurring browser-access authorization are
recorded in `config/sources.json`. A browser challenge or inaccessible page is a source failure; no
challenge bypass, account registration, applications, host messages, or booking actions occur.

## Eligibility and publication

The job reads rendered public cards and details, then writes original short factual annotations.
It does not save photos, raw ad text, contact details, or host profiles. Rent above the ceiling,
known additional monthly utilities that exceed it, explicit late starts/early ends, incompatible
minimum/maximum stays, and mandatory year-long leases are excluded. Unclear dates, fees,
furnishing, or lease conditions are marked for confirmation. Airbnb requires a displayed quote for
both exact stay dates; a search card alone does not establish availability.

Each source is attempted independently. A successful source replaces its previous results, including
when it legitimately returns no eligible listings. A failed source retains its previous leads and
**original check dates**, and the page labels that source unavailable. Partial refreshes show a banner.
If every collection source fails, the existing snapshot and refresh timestamp stay unchanged.

After collection, a second deduplication pass merges URL aliases, preserves semantic listing IDs
(such as SpareRoom's query IDs), and groups explicitly reviewed cross-posts. Grouped cross-posts keep
each source link, annotation, and check date so conflicting prices remain visible. Similar rent or
neighborhood alone never merges separate rooms. Additional confirmed duplicates can be added to
`duplicate_groups` in the source configuration.

## Files and configuration

- `config/sources.json`: dates, budget, CDP proxy, collection limits, resource links, and reviewed duplicates.
- `scripts/daily_refresh.py`: orchestration, source failure isolation, deduplication, snapshots, and history.
- `scripts/browser_sources.py`: bounded Mac-lane DOM checks and factual eligibility rules for added sites.
- `scripts/run_daily.sh`: lane startup, lock, logging, and data commit/push.
- `site/leads.json`: daily results and individual source status.
- `site/history.json`: the latest snapshot per Berlin day, retaining up to 90 days.
- `site/review.json`: the dated one-time review list; daily collection does not rewrite this historical list.
- `.github/workflows/pages.yml`: deploys only `site/` to GitHub Pages on pushes to `main`.
- `systemd/`: service/timer templates; installed service uses `/home/agent/work/work-20261016-180224`.
- `tests/`: regression checks for budget/date/lease filtering, failed-source retention, and deduplication.
- `var/`: ignored locks, logs, temporary snapshots, and live-check output.

Requires Python 3 and `websockets` from `requirements.txt` in the deployed checkout's `.venv`,
Mac-lane (`http://127.0.0.1:19999`), and the service user's existing SSH Git credentials.
`HMS_CONFIG` overrides the configuration path. Example commands:

```bash
python3 -m unittest discover -s tests -v
.venv/bin/python scripts/daily_refresh.py --dry-run
.venv/bin/python scripts/daily_refresh.py --output var/manual/leads.json
systemctl --user start hms-housing-watch.service
systemctl --user list-timers hms-housing-watch.timer
```

Create the custom output directory before using `--output`. Browser sources require CDP and do not
support the HTTP transport override. Logs are `var/logs/daily-YYYY-MM-DD.log` in the deployed checkout.
The private housing-research brief remains ignored and must not be committed. The standalone prototype
timer is disabled; its older scripts are retained for historical/manual use.
