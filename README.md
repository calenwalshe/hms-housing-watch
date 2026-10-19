# HMS Short-Term Housing Watch

Static one-column page of current room/sublet leads near Harvard Medical School for a stay of
2026-11-09 to 2027-04-19 (target $1,200/month, stretch $1,400/month). Spec and plan:
`docs/superpowers/`. The page lists leads, not verified or endorsed listings.

## Layout
- `site/` — `index.html`, `styles.css`, `leads.json`, `history.json` (day-by-day archive, Berlin dates; the only published content).
- `config/sources.json` — stay, budget, CDP proxy, and sources (`collect` or `link_only`).
- `scripts/daily_refresh.py` — collects, filters, annotates, atomically replaces `site/leads.json` only if every `collect` source succeeds.
- `scripts/run_daily.sh` — Mac-lane start, single-run lock, refresh, commit/push when data changed.
- `systemd/` — service and timer templates (installed copies live in ~/.config/systemd/user/) (daily 05:00 Europe/Berlin, `Persistent=true`, 30 min runtime cap).
- `.github/workflows/pages.yml` — deploys only `site/`; permissions `contents: read`, `pages: write`, `id-token: write`.
- `docs/evidence/` — manual review evidence. `var/` (locks, logs, scratch) is git-ignored.

After all collection sources finish, a second pass canonicalizes listing URLs and removes duplicates across
sources, including tracking-query, fragment, trailing-slash, `www`, and Craigslist regional-host variants.
It records the number removed in refresh history and on the page. It does not merge distinct URLs based on
approximate rent or location matches, which could collapse separate rooms.

## Configuration and dependencies
Python 3 (stdlib only for `--transport http`); `websockets` (see `requirements.txt`, installed in the
project `.venv`: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`) for the default
CDP transport; Mac-lane (`mac-lane.sh up`, proxy `http://127.0.0.1:19999`); `git` with credentials for
`origin` (run_daily.sh). `HMS_CONFIG` overrides the config path.
Manual run: `.venv/bin/python scripts/daily_refresh.py [--dry-run] [--transport http]`.

Source policy: two `collect` sources. (1) RotatingRoom Boston (robots.txt allows all agents,
terms have no automation clause; reads each public listing page's structured data, one index
request plus up to 40 detail requests 2 s apart, once a day; no sign-in, forms, or messages).
(2) Craigslist Boston rooms via the Mac-lane browser bridge (owner-approved 2026-10-17;
read-only real-browser pass, 4 search pages + up to 12 detail pages 3 s apart, original
annotations from extracted facts only; Craigslist terms restrict automated collection —
see the access_note in config/sources.json). Zillow and Apartments.com remain `link_only`. Stored per lead: URL, source name, a short
original annotation, and check date. No photos, ad text, titles, or contact details.

## Activation status (done 2026-10-17, owner-approved)
1. Public GitHub repository: https://github.com/calenwalshe/hms-housing-watch (the private research brief is git-ignored and was never committed).
2. GitHub Pages via Actions — live at https://calenwalshe.github.io/hms-housing-watch/
3. systemd user units installed in `~/.config/systemd/user/` (checkout path set) and the timer enabled: daily 05:00 Europe/Berlin.
4. Post-activation checks passed: one manual service run (2026-10-17) collected via Mac-lane, committed, and pushed; the public URL serves the current snapshot; a failed refresh (missing dependency, same day) left the snapshot unpublished and unchanged.

## Known limitations
- Harvard/HMS resources are link-only search links (HMS Housing and Dining, Harvard Off-Campus Housing Search, Harvard University Housing), verified by browser title on 2026-10-16; HMS pages return 403 to non-browser clients, so they are never collected.
- The initial snapshot has one lead; most RotatingRoom Boston listings were excluded on rent above $1,400 or date mismatch. There is no distance filter beyond the stated miles in the annotation (the lead is 5.4 mi from HMS).
- Annotations rely on the source's structured data; room vs whole-unit and utilities are unknown and marked for confirmation.
- A lead is dropped only when a fully successful run no longer includes it; a failed run keeps everything.
- The wrapper and workflow have not been executed (gated); only `bash -n`, `py_compile`, and `systemd-analyze calendar` were run.

## Browser-bridge prototype (superseded 2026-10-17)
The prototype pass was promoted into the production refresh as the `craigslist_browser`
collect source (same Mac-lane bridge, same judgment filters), so the daily 05:00 Berlin
public run now includes its leads with day-by-day first_seen tracking. The standalone
`hms-housing-prototype` timer is disabled; `scripts/browser_pass.py` remains for manual
brief-style passes to the tailnet Pixel page.
