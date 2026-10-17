# u5 manual review of the F1 fix and the Harvard/HMS resource links (2026-10-16)

Implementation SHA reviewed: `caa86b5dfc053d249599e694f669bd365cc45cde`. No tests were added or run; the publishing wrapper was not executed.
This file is committed on top of that SHA.

## F1: location and distance provenance — PASS
Listing 45705 carries conflicting location signals:
- Breadcrumb "Medford Sublets" is a site category and was dropped.
- Accommodation `address.addressLocality` is "Somerville", the title says "Cozy bedroom in Somerville", and the FAQ says "furnished sublet in Somerville, MA".
- The Organization block says Cambridge; that is the company's address, not the listing's.

Fix in `parse_listing`: the location is used only when the listing's own `addressLocality` is also named in the FAQ rent answer ("in <locality>, <ST>"). Otherwise it is omitted. It is no longer taken from the breadcrumb and is not taken from addressLocality alone.

Distance: the FAQ says "Harvard Medical School, 5.36 miles away". The listing's `geo` is 42.41091, -71.12980. The great-circle distance from there to Vanderbilt Hall (42.3358, -71.1031) is 5.37 mi (haversine, computed here). So the figure is a straight-line distance from the listing's coordinates, not a travel distance. The annotation now says "5.36 mi straight-line from HMS (per site)". The HMS reference point is the site's own, and I matched it only approximately.

Snapshot: `site/leads.json` regenerated 2026-10-16T19:13:28-07:00; the annotation now reads "Somerville; 5.36 mi straight-line from HMS (per site); ...".

## Harvard/HMS resource links (spec requirement) — PASS for 3 links; HMS-specific portal beyond these not found
Plain curl returns HTTP 403 for the HMS page and the portal, so they cannot be checked headlessly. They were loaded read-only in the Mac-lane Chrome. Three page loads and no interaction, with titles:
| Link | Browser title | curl |
|---|---|---|
| https://hms.harvard.edu/life-hms/housing-dining | "Housing and Dining \| Harvard Medical School" | 403 |
| https://harvardhousingoffcampus.com/ | "Harvard University \| Off-Campus Housing Search" | 403 |
| https://huhousing.harvard.edu/ | "Home \| Harvard University Housing" | 200 |

The URLs came from search results on official Harvard pages (the HMS housing page itself, plus HUH and the Harvard Summer School and HLS pages) that point to these sites. They are added as `link_only` sources and shown in "Search these sites". The earlier `unresolved_sources` entry is now empty. A guess at `hms.harvard.edu/student-affairs/housing` returned 403 and was not used. `offcampushousing.harvard.edu` did not resolve and was not used.
Caveat: the page labels every entry there as "— live search", including the three resource pages; the wording is slightly off for HMS/HUH info pages and I left the renderer alone.

## Rendering — PASS
`docs/evidence/rework-render-mobile.png` (390 px, headless Chrome, served from `site/` on a free port) shows: refresh 2026-10-16 19:13, the Somerville lead with the straight-line wording, and seven links with the three Harvard/HMS entries first. The first attempt hit another service on port 8765 and was discarded.

## Failure preservation — PASS
With `cdp_proxy` pointed at 127.0.0.1:1: "refresh failed; snapshot unchanged: RotatingRoom (Boston): Connection refused", exit 1, sha256 of `site/leads.json` identical before and after (3c931a0a…). The write path (temp file then `os.replace`) is unchanged.
