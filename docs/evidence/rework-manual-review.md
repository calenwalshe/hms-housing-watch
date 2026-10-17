# Manual review at HEAD 8d50a2c (2026-10-16, rework of blk-de8b0a306e97)

No tests were added or run. All checks were manual, local, and read-only. The only network use was
two GETs of the one listing URL. Reviewed SHA for every row: `8d50a2ca0487ffe6be873c0058fe3fee2b626a0c`.

| # | Check | Evidence | Result |
|---|-------|----------|--------|
| 1 | Local rendering | `docs/evidence/u3-render-mobile.png` (390 px) shows the title, stay and budget, "Last successful refresh: 2026-10-16 19:06 (-07:00)", the disclaimer, one lead with an "Open listing" link, annotation and "Last checked 2026-10-16", and four "live search" links. Matches `site/leads.json` (same refresh stamp, URL and annotation text). Empty-list and missing-JSON states were checked in u1; not re-run here. | PASS (screenshot only; I did not re-render) |
| 2 | Current dated leads from permitted sources | `leads.json` has `generated_at` 2026-10-16T19:06:13-07:00 and 1 lead (rotatingroom.com/need-a-room/45705, $1,200/month, `checked_at` 2026-10-16). Only RotatingRoom is `collect`. Its `access_note` records robots.txt as allowing all agents with no automation clause in the terms. Craigslist, Zillow and Apartments.com are `link_only`. Re-fetching the URL returned HTTP 200, price 1200, availability 2026-06-01 to 2027-07-31, which covers the 2026-11-09 to 2027-04-19 stay. | PASS for existence, date, price and stay-fit. See finding F1. |
| 3 | Prior snapshot preserved on source failure | `u2-source-failure-preservation.md`: Failure A (index 404) and Failure B (CDP proxy refused) both exit 1, and sha256 of `site/leads.json` is 5732389b…8af0e before and after. That hash equals the current file (`sha256sum`, re-run here). Code: `write_successful_snapshot` writes a temp file then `os.replace`, called only after every `collect` source succeeds; any `SourceError` aborts before the write (`daily_refresh.py:215-246`). | PASS (the failure runs are the earlier worker's recorded output; I did not re-run them) |
| 4 | Schema | `site/leads.json` has `generated_at`, `stay`, `budget`, `leads[{url,source,annotation,checked_at}]`, `search_links[{url,source}]`, as in plan Task 1/2. It holds no contact details, photos or copied text. | PASS |
| 5 | Source configuration | `config/sources.json` parses (json.load OK): 1 `collect`, 4 `link_only`, with access notes and rate limits (`max_listings` 40, `delay_seconds` 2). | PASS |
| 6 | Refresh and wrapper scripts | `bash -n scripts/run_daily.sh` OK. `daily_refresh.py` parses (`ast.parse`). Wrapper: lock via flock, `mac-lane.sh up`, refresh, then commit and push only if `leads.json` changed. The push stays unexecuted. | PASS (static review; the wrapper was not executed because it ends in `git push`) |
| 7 | Publish workflow | `.github/workflows/pages.yml` deploys only `site/`, with permissions `contents: read`, `pages: write`, `id-token: write`. It runs only on push to `main` or manual dispatch. No repo exists and nothing was pushed. | PASS as an inert template |
| 8 | systemd service and timer | `systemd-analyze calendar` normalizes to `*-*-* 07:00:00 America/Los_Angeles` (next 2026-10-17 07:00 PDT). Not installed or enabled. See the warnings section. | PASS as inactive templates |
| 9 | Protected file | `.gitignore:1` ignores `housing-research-harvard-medical-school.md`. It is not in the tree and has no history in `git log --all`. | PASS |
| 10 | Unavailable-lead removal (plan Task 2) | Each successful run rebuilds the snapshot from scratch, so a listing that disappears drops out on the next successful run. A failed run changes nothing. No live "listing removed" case was observed. | UNVERIFIED (by code reading only) |
| 11 | Harvard/HMS resource links | Not configured. `unresolved_sources` in `sources.json` records that the URLs could not be verified. This is a limitation of the spec's initial source set, not a satisfied requirement. | UNRESOLVED (documented limitation) |
| 12 | Gated steps (public repo, Pages, timer enablement, outside-tailnet check, push) | Not performed, by contract. Plan Task 3 steps 2, 5 and 6 are therefore not done. | NOT DONE (gated) |

## Finding F1 (data accuracy, not fixed)
The lead's annotation says "Medford". The parser (`parse_listing`) takes the neighborhood from the
third breadcrumb. The listing page's own data reads differently:
- `addressLocality`: Somerville (and Cambridge in another block).
- Title: "Cozy bedroom in Somerville with backyard".
- Summary text: "2-bedroom in West Somerville".

The breadcrumb contains a `medford-ma` link. The "Medford" label is therefore likely wrong, and the "5.36 mi from HMS"
figure is not independently verified. The annotation already tells readers to confirm the unit type, utilities
and total cost with the host. The "Medford" label is stated without a hedge. I did not change the parser or the snapshot,
because that goes beyond a review-only rework. Suggested fix for the next unit: prefer `addressLocality`,
or drop the neighborhood, then re-run the refresh.

## systemd validation warnings
`systemd-analyze verify --user systemd/hms-housing-watch.service systemd/hms-housing-watch.timer` printed three lines:
1. `authsys-browser-supervisor.service:3: Invalid URL, ignoring: deploy/UNITS.md`. This is another unit in the
   user's `~/.config/systemd/user`, unrelated to these templates.
2. `spice-vdagent.service:23: Unknown key 'StandardError' in [Install]`. This is a system-packaged unit, unrelated.
3. `hms-housing-watch.service: Command /home/agent/projects/hms-housing-watch/scripts/run_daily.sh is not executable:
   No such file or directory`. This one concerns our template. It is expected: `%h/projects/hms-housing-watch`
   does not exist, because the checkout is only a worktree and nothing is installed. It would clear once the
   repository is placed there. The check is path-dependent, so I count it as unverified-until-install rather than as a
   defect. There were no syntax or key errors in either hms unit, and `%h` expanded correctly.
Only warning 3 touches these templates, and it is an install-path condition, not a template error.
