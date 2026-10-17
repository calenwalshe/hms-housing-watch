# HMS Short-Term Housing Watch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a simple public page of current room leads near HMS and refresh its links and short annotations each day through the Mac-lane browser.

**Architecture:** A static page reads a generated JSON lead file and deploys through GitHub Pages. A daily Python job on the always-on agent-stack server uses the Mac-lane Chrome CDP endpoint to check allowed sources, writes a new lead file only after a successful run, and pushes the update to the public repository. A user timer runs the job daily; failed runs preserve the last good page.

**Tech Stack:** Static HTML/CSS/JSON, Python 3, `websockets` (already used by the Mac-lane CDP example), git/GitHub CLI, GitHub Pages Actions, systemd user timer.

**Spec:** `docs/superpowers/specs/2026-10-16-hms-housing-watch-design.md`

## Global Constraints

- Stay dates: November 9, 2026 through April 19, 2027.
- Budget target: $1,200/month; stretch ceiling: $1,400/month.
- The page is a public, one-column list with a stable URL reachable without tailnet or sign-in.
- Each lead has a direct source link, a short original annotation, and a last-checked date.
- Do not reproduce listing photos, full ad text, contact details, or user profile information.
- Honor each source's access rules; do not bypass login walls or anti-bot controls, submit forms, or send messages.
- If a source does not permit automated listing collection or republication, show its live search link only.
- On a failed daily run, keep the last successful public data and timestamp.
- Keep the existing untracked `housing-research-harvard-medical-school.md` out of the public repository.

## Review Focus

- Mac-lane is unavailable or cannot wake: leave the current site data and timestamp untouched.
- A configured collection source is blocked or changes markup: fail the run and preserve the prior snapshot; `link_only` sources do not count as collection failures.
- A listing has an unclear rent period, date range, or furnishing status: annotate uncertainty instead of presenting an inferred fact as confirmed.
- A listing disappears or becomes stale: remove it only after a successful check of its source confirms that it is unavailable.
- GitHub push or Pages deployment fails: preserve the last live version and report the local job failure without publishing an empty list.

---

## File Structure

- `site/index.html` — single-page list layout and rendering of the generated data.
- `site/styles.css` — restrained responsive styling for phone and desktop.
- `site/leads.json` — current public leads and successful-refresh timestamp.
- `config/sources.json` — source search URLs and per-source collection/display mode.
- `scripts/daily_refresh.py` — Mac-lane/CDP collection, normalization, eligibility checks, unavailable-lead removal, and atomic JSON replacement.
- `scripts/run_daily.sh` — lane startup, single-run lock, GitHub commit/push, and failure logging wrapper.
- `systemd/hms-housing-watch.service` — user service that runs the wrapper.
- `systemd/hms-housing-watch.timer` — daily 07:00 America/Los_Angeles schedule.
- `.github/workflows/pages.yml` — deploys only `site/` to GitHub Pages on pushes to `main`.
- `.gitignore` — excludes the private/untracked research brief and local runtime/log artifacts.

### Task 1: Build the static page and public data contract

**Files:**
- Create: `site/index.html`
- Create: `site/styles.css`
- Create: `site/leads.json`

**Interfaces:**
- Produces: JSON object `{ "generated_at": string, "stay": {"start": string, "end": string}, "budget": {"target_monthly": number, "max_monthly": number}, "leads": [{"url": string, "source": string, "annotation": string, "checked_at": string}], "search_links": [{"url": string, "source": string}] }`.
- `index.html` loads `leads.json` from the same directory and renders header, refresh date, lead list, and live-search links; if JSON loading fails, it shows a clear stale/unavailable message rather than a blank page.

- [ ] Create `site/leads.json` with the exact stay dates, budget values, empty `leads` and `search_links` arrays, and a generated timestamp.
- [ ] Create `site/index.html` to render the data contract above with accessible lead and search-link text, an explicit “last updated” value, and a note that listings must be confirmed with hosts.
- [ ] Create `site/styles.css` for a readable one-column mobile and desktop layout; keep all lead information in the JSON, not duplicated in markup.
- [ ] Manually inspect the page from a local static server with both an empty list and representative populated JSON.
- [ ] Commit the page and data contract as `feat: add HMS housing watch page`.

### Task 2: Implement daily lead collection through Mac-lane

**Files:**
- Create: `config/sources.json`
- Create: `scripts/daily_refresh.py`
- Modify: `site/leads.json`

**Interfaces:**
- Consumes: `config/sources.json`, the page data schema from Task 1, and Mac-lane CDP at `http://127.0.0.1:19999` after `mac-lane.sh up`.
- Produces: `@dataclass Lead(url: str, source: str, annotation: str, checked_at: str)`, `@dataclass SearchLink(url: str, source: str)`, `@dataclass Source(name: str, search_url: str, mode: Literal["collect", "link_only"])`, `collect_sources() -> tuple[list[Lead], list[SearchLink]]`, `normalize_lead(raw: dict[str, str], source: Source) -> Lead | None`, and `write_successful_snapshot(leads: list[Lead], search_links: list[SearchLink], generated_at: str) -> None` in `scripts/daily_refresh.py`.
- `Lead` and `SearchLink` map exactly to their corresponding objects in the public JSON.

- [ ] Define a source record with `name`, `search_url`, and `mode` (`collect` or `link_only`); set restricted or inaccessible sources to `link_only`.
- [ ] Implement a CDP helper using `urllib.request` plus `websockets`, following `/home/agent/.claude/skills/mac-lane/reference/drive-example.py` for tab open/close and `Runtime.evaluate`.
- [ ] Extract only direct URLs and the minimum visible facts needed for an original short annotation; do not retain raw page text, contact fields, photos, or profile data.
- [ ] Filter out explicit rent above $1,400/month and explicit stay-date mismatches. Mark unclear amounts, utility inclusion, and dates as “confirm with host.”
- [ ] Normalize each eligible lead to the Task 1 schema, deduplicate by canonical URL, and set `checked_at` to the local date.
- [ ] Keep direct source-search links for all `link_only` entries in a separate “Search these sites” list in the same JSON contract; extend the schema with `{"url": string, "source": string}` for those links and render them as ordinary list links.
- [ ] Write output to a temporary file and atomically replace `site/leads.json` only after every configured `collect` source completes; if any `collect` source fails or changes beyond the supported markup, exit nonzero without changing the existing JSON.
- [ ] Manually run a read-only refresh against the configured sources and inspect the generated links, dates, prices, and annotations; confirm an unclear date or rent period is marked for host confirmation.
- [ ] Manually simulate a failure for one configured `collect` source and confirm the existing JSON and timestamp remain unchanged.
- [ ] Manually confirm an absent or unavailable listing is removed only after its source completed a successful check; a failed source check leaves its previous leads untouched by failing the whole snapshot.
- [ ] Commit as `feat: collect daily HMS housing leads`.

### Task 3: Publish the page and schedule the daily refresh

**Files:**
- Create: `scripts/run_daily.sh`
- Create: `systemd/hms-housing-watch.service`
- Create: `systemd/hms-housing-watch.timer`
- Create: `.github/workflows/pages.yml`
- Create: `.gitignore`

**Interfaces:**
- Consumes: `scripts/daily_refresh.py`, `site/`, existing GitHub CLI authentication for the service user, and the Mac-lane startup script at `/home/agent/projects/cairn-gate-labs/lab/infra/browser-bridge/bin/mac-lane.sh`.
- Produces: a public Pages URL and an enabled `hms-housing-watch.timer` that invokes `scripts/run_daily.sh` once per day at 07:00 Pacific.

- [ ] Add ignore rules for the existing research brief, local lock/log files, Python cache, and any local secrets; confirm the research brief is not staged.
- [ ] Create the public GitHub repository `hms-housing-watch` with the site, collector, workflow, and planning docs; exclude the existing housing research brief. Configure GitHub Pages deployment from `.github/workflows/pages.yml` and grant the workflow only `pages: write`, `id-token: write`, and `contents: read`.
- [ ] Implement `scripts/run_daily.sh` to start Mac-lane, acquire a non-overlapping lock, run `daily_refresh.py`, and commit/push only when the generated data changes; do not print credentials.
- [ ] Add the systemd user service and timer for 07:00 America/Los_Angeles; configure persistent catch-up behavior and bounded runtime.
- [ ] Enable the timer for the service user and confirm its next scheduled time with `systemctl --user list-timers`.
- [ ] Run the service once manually, open the public GitHub Pages URL from outside the tailnet, and confirm links, dates, refresh timestamp, and mobile layout; simulate a source failure and confirm that it does not publish an empty or partial snapshot.
- [ ] Commit as `feat: publish and schedule housing watch`.

## Acceptance Review

- A reader in Germany can open the stable public URL without a tailnet or account.
- The page stays a simple linear list of short-annotated direct links with last-checked and last-successful-refresh dates.
- The daily job uses Mac-lane, only collects from sources configured for permitted collection, and preserves the previous page after any total failure.
- Restricted sources remain one-click live search links.
- The public repository does not contain the existing research brief, personal contact details, photos, or full copied listing text.
