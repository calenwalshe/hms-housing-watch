import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import daily_refresh as refresh

class SourceIsolation(unittest.TestCase):
    def test_failed_source_keeps_old_check_date_and_other_source_refreshes(self):
        bad = refresh.Source('Failed source', 'https://bad.example', 'collect', parser='bad')
        good = refresh.Source('Healthy source', 'https://good.example', 'collect', parser='good')
        prior = {'leads': [{'source': 'Failed source', 'url': 'https://bad.example/room/1',
                           'annotation': 'Previous facts', 'checked_at': '2026-10-17', 'first_seen': '2026-10-16'}]}
        def fail(*args):
            raise refresh.SourceError('Page unavailable')
        def succeed(*args):
            return [refresh.Lead('https://good.example/room/2', 'Healthy source', 'New facts', '2026-10-19')], {
                'source': 'Healthy source', 'checked': 1, 'over_budget': 0, 'date_mismatch': 0, 'eligible': 1}
        with patch.object(refresh, 'load_config', return_value=({}, [bad, good])), patch.dict(refresh.PARSERS, bad=fail, good=succeed):
            _, leads, _, stats = refresh.collect_sources(prior_snapshot=prior)
        self.assertEqual({l.source for l in leads}, {'Failed source', 'Healthy source'})
        self.assertEqual(next(l for l in leads if l.source == 'Failed source').checked_at, '2026-10-17')
        self.assertEqual(stats[0]['status'], 'failed')
        self.assertEqual(stats[1]['status'], 'ok')

    def test_successful_empty_source_removes_its_old_results(self):
        source = refresh.Source('Healthy', 'https://good.example', 'collect', parser='good')
        prior = {'leads': [{'source': 'Healthy', 'url': 'https://good.example/room/1',
                           'annotation': 'Old', 'checked_at': '2026-10-17'}]}
        def empty(*args):
            return [], {'source': 'Healthy', 'checked': 5, 'eligible': 0}
        with patch.object(refresh, 'load_config', return_value=({}, [source])), patch.dict(refresh.PARSERS, good=empty):
            _, leads, _, stats = refresh.collect_sources(prior_snapshot=prior)
        self.assertEqual(leads, [])
        self.assertEqual(stats[0]['status'], 'ok')

    def test_all_failed_sources_prevent_snapshot_advance(self):
        bad = refresh.Source('Broken', 'https://bad.example', 'collect', parser='bad')
        def fail(*args):
            raise refresh.SourceError('Unavailable')
        with patch.object(refresh, 'load_config', return_value=({}, [bad])), patch.dict(refresh.PARSERS, bad=fail):
            with self.assertRaises(refresh.SourceError):
                refresh.collect_sources(prior_snapshot={'leads': []})

class ListingDedupe(unittest.TestCase):
    def test_spare_room_query_ids_remain_distinct(self):
        a = refresh.Lead('https://www.spareroom.com/roommate/room_for_rent.pl?flatshare_id=111&utm_source=a', 'SpareRoom', 'one', '2026-10-19')
        b = refresh.Lead('https://www.spareroom.com/roommate/room_for_rent.pl?flatshare_id=222', 'SpareRoom', 'two', '2026-10-19')
        self.assertEqual(len(refresh.dedupe_leads([a, b])[0]), 2)

    def test_reviewed_cross_posts_merge_but_keep_both_prices(self):
        a = refresh.Lead('https://www.spareroom.com/roommate/room_for_rent.pl?flatshare_id=111', 'SpareRoom', '$1290 stated', '2026-10-19')
        b = refresh.Lead('https://www.craigslist.org/view/d/shared-room/token', 'Craigslist', '$1390 stated', '2026-10-19')
        groups = [{'urls': [a.url, b.url]}]
        leads, removed = refresh.dedupe_leads([a, b], duplicate_groups=groups)
        self.assertEqual(len(leads), 1)
        self.assertEqual(removed, 1)
        self.assertEqual(leads[0].cross_posts[0]['annotation'], '$1390 stated')

class SnapshotIdentity(unittest.TestCase):
    def test_cross_post_keeps_property_first_seen_date(self):
        import json
        import tempfile
        a='https://www.spareroom.com/roommate/room_for_rent.pl?flatshare_id=111&utm_source=old'
        b='https://www.craigslist.org/view/d/shared-room/token'
        cfg={'stay':{'start':'2026-11-09','end':'2027-04-19'},'budget':{'max_monthly':1400},
             'duplicate_groups':[{'urls':[a,b]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'leads.json'
            path.write_text(json.dumps({'leads':[{'url':a,'first_seen':'2026-10-16'}]}))
            lead=refresh.Lead(b,'Craigslist','Current facts','2026-10-19')
            refresh.write_successful_snapshot(cfg,[lead],[], '2026-10-19T08:00:00-07:00',str(path),
                checked=[{'source':'Other','status':'failed','retained':0}])
            doc=json.loads(path.read_text())
            self.assertEqual(doc['leads'][0]['first_seen'],'2026-10-16')
            self.assertEqual(doc['snapshot_status'],'partial')

if __name__ == '__main__':
    unittest.main()
