# HMS Short-Term Housing Watch

Static one-column page of current room/sublet leads near Harvard Medical School for a stay of
2026-11-09 to 2027-04-19 (target $1,200/month, stretch $1,400/month). Spec and plan:
`docs/superpowers/`. The page lists leads, not verified or endorsed listings.

## Layout
- `site/` — `index.html`, `styles.css`, `leads.json` (the only published content).
- `config/sources.json` — stay, budget, CDP proxy, and sources (`collect` or `link_only`).
- `scripts/daily_refresh.py` — collects, filters, annotates, atomically replaces `site/leads.json` only if every `collect` source succeeds.
- `scripts/run_daily.sh` — Mac-lane start, single-run lock, refresh, commit/push when data changed.
- `systemd/` — inactive service and timer templates (daily 07:00 America/Los_Angeles, `Persistent=true`, 30 min runtime cap).
- `.github/workflows/pages.yml` — deploys only `site/`; permissions `contents: read`, `pages: write`, `id-token: write`.
- `docs/evidence/` — manual review evidence. `var/` (locks, logs, scratch) is git-ignored.

## Configuration and dependencies
Python 3 (stdlib only for `--transport http`); `websockets` for the default CDP transport; Mac-lane
(`mac-lane.sh up`, proxy `http://127.0.0.1:19999`); `git` with credentials for `origin` (run_daily.sh).
`HMS_CONFIG` overrides the config path. Manual run: `python3 scripts/daily_refresh.py [--dry-run] [--transport http]`.

Source policy: RotatingRoom Boston is the only `collect` source (robots.txt allows all agents,
terms have no automation clause; it reads each public listing page's structured data, one index
request plus up to 40 detail requests 2 s apart, once a day; no sign-in, forms, or messages).
Craigslist, Zillow, and Apartments.com are `link_only`. Stored per lead: URL, source name, a short
original annotation, and check date. No photos, ad text, titles, or contact details.

## Activation approval gates (nothing below has been done)
1. Create the public GitHub repository `hms-housing-watch` (exclude `housing-research-harvard-medical-school.md`; it is git-ignored).
2. Push and set Pages source to "GitHub Actions" (deploys the page).
3. Install and enable the systemd units: copy to `~/.config/systemd/user/`, fix the checkout path, `systemctl --user enable --now hms-housing-watch.timer`.
4. Post-activation checks from the plan: one manual service run, open the public URL off-tailnet, confirm a simulated source failure publishes nothing.

## Known limitations
- Harvard off-campus portal and HMS housing resources are not configured: their public URLs could not be verified from the collection host (HMS pages 403 non-browser clients; portal host did not resolve). They appear neither as leads nor search links.
- The initial snapshot has one lead; most RotatingRoom Boston listings were excluded on rent above $1,400 or date mismatch. There is no distance filter beyond the stated miles in the annotation (the lead is 5.4 mi from HMS).
- Annotations rely on the source's structured data; room vs whole-unit and utilities are unknown and marked for confirmation.
- A lead is dropped only when a fully successful run no longer includes it; a failed run keeps everything.
- The wrapper and workflow have not been executed (gated); only `bash -n`, `py_compile`, and `systemd-analyze calendar` were run.
