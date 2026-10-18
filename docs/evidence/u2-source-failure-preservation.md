# u2 evidence: source failure preserves the prior snapshot

Manual runs on 2026-10-16, no tests. Hash is sha256 of site/leads.json.

Note: the first run of the CDP path (no override) found a Mac-lane proxy already live at 127.0.0.1:19999 and collected through that Chrome (read-only page loads). The wake step was not run by this job. That run produced the committed snapshot's content.

## Failure A: configured RotatingRoom index URL 404s (HMS_CONFIG=bad config, http)
```
before: 5732389b885bd3451fa6e1c3989931611bb36ecf200856899f74476dc008af0e  site/leads.json
refresh failed; snapshot unchanged: RotatingRoom (Boston): HTTP Error 404: Not Found
exit code: 1
after:  5732389b885bd3451fa6e1c3989931611bb36ecf200856899f74476dc008af0e  site/leads.json
```
Result: snapshot byte-identical

## Failure B: CDP proxy unreachable (HMS_CONFIG points cdp_proxy at 127.0.0.1:1)
```
before: 5732389b885bd3451fa6e1c3989931611bb36ecf200856899f74476dc008af0e  site/leads.json
refresh failed; snapshot unchanged: RotatingRoom (Boston): <urlopen error [Errno 111] Connection refused>
exit code: 1
after:  5732389b885bd3451fa6e1c3989931611bb36ecf200856899f74476dc008af0e  site/leads.json
```
Result: snapshot byte-identical, generated_at not advanced
