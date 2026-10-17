# HMS Short-Term Housing Watch — Design Spec

**Date:** October 16, 2026  
**Status:** Design for user review  
**Audience:** A German short-term scholar at Harvard Medical School

## Goal

Provide a simple public page the scholar can check each day for current room and shared-apartment leads near Harvard Medical School. The required stay is November 9, 2026 through April 19, 2027. The target is about $1,200 per month, with a stretch ceiling of $1,400.

## User experience

The page is one linear, mobile-friendly list. Each entry has a direct source link, a short original annotation, and the date it was last checked. A small header shows the search window, budget, and the latest successful refresh time. Listings that are no longer available, no longer fit the dates, or cannot be verified are removed on the next successful update. There is no sign-in, search UI, filter panel, saved-leads notebook, or contact action.

The annotations should help prioritize a lead (for example, neighborhood/commute, stated price, furnishing, and date fit) and should be concise. The page is a lead-finding aid, not a verification or endorsement of hosts, properties, or lease terms. The scholar must confirm current availability, exact dates, total costs, sublet authorization, and safety directly with the host.

## Research and refresh

A once-daily scheduled run uses the Mac-lane real Chrome browser to inspect the selected public search sources, open promising results, and check each lead against the scholar's stay dates and budget. The run writes a new dated list and publishes it only after the output is formed successfully. The page shows the time of the most recent successful update; a failed run leaves the previous list in place and does not advance that timestamp.

The initial source set is Harvard/HMS housing resources, Harvard's off-campus housing portal where accessible, RotatingRoom, Craigslist Boston room searches, and mainstream rental search sources identified in the existing research brief. The implementation must honor each source's access rules, avoid bypassing login walls or anti-bot controls, avoid sending messages or submitting forms, and use only the minimum requests needed. If a source disallows automated collection or automated display of listings, it remains a direct link to that source's live search rather than a source for copied listings. Source-specific behavior and rate limits must be documented in the implementation plan.

The page may contain a direct listing URL and a short independently written note. It will not reproduce photos, full ad text, contact details, or user profile information. It will not collect or retain personal data about hosts or the scholar.

## Architecture

- **Public page:** a small static site published through GitHub Pages at a stable URL that works without a tailnet connection or sign-in.
- **Daily runner:** a scheduled job on the always-on agent-stack server. It drives the permitted Mac-lane browser flow, validates the generated list, and updates the published page.
- **Data:** a compact generated JSON or Markdown file checked into the public site repository alongside the static page. The page renders that file without an application backend or database.
- **Failures:** if browser access, a source, or publishing fails, keep the last good page and timestamp. Record an operational error locally; do not publish a misleading empty list.

## Initial content

The dated October 16 research brief in `housing-research-harvard-medical-school.md` is the initial research reference. Before any entries are placed on the public page, their links and date/budget fit must be rechecked. The public page starts with only currently verified leads and source-search links; it does not copy the research brief wholesale.

## Out of scope

- User accounts, personal notes, application workflows, messaging landlords, automatic deposits, or recommendations that guarantee legitimacy.
- Scraping sources that prohibit it, defeating access controls, or publishing more source content than is needed to identify and evaluate a lead.
- A promise that every suitable room will be found or that a listing remains available between daily checks.

## Acceptance criteria

1. A person in Germany can open the stable public URL without a VPN, account, or tailnet.
2. The page is a readable single-column list on phone and desktop, with direct links and brief annotations.
3. Every lead shows its last-checked date; the page shows the last successful daily refresh.
4. Leads are checked against November 9, 2026–April 19, 2027 and the $1,200 target / $1,400 stretch budget, with uncertain terms clearly marked for confirmation.
5. A daily run refreshes eligible leads and leaves the prior successful page intact if the run fails.
6. Restricted sources remain available as live search links without automated listing republication.
7. The page contains no host contact information, photos, copied full descriptions, user accounts, or messaging functionality.
