"""Aktualität vor Ranking und Modellaufruf, Rohdaten bleiben erhalten."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('freshness_builder',ROOT/'scripts/build_briefing.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.ref='2026-10-06T12:00:00+02:00'
        self.config=[{'id':'security','max_news_age_days':7}]

    def item(self, date, **extra):
        return dict(id='news',source_id='security',source='Security',source_type='primary',
            status='ok',published_at=date,collected_at=self.ref,last_seen_at=self.ref,
            title='Cybersecurity',raw_excerpt='Security for companies.',category=['IT Security'],**extra)

    def test_boundary_unknown_future_and_recollected_old_item(self):
        dates=['2026-09-29T12:00:00+02:00','2026-09-29T11:59:59+02:00',
            '2026-07-01',None,'invalid','2026-10-07']
        items=[self.item(d) for d in dates]
        original=copy.deepcopy(items)
        selected=builder.filter_source_freshness(items,self.config,self.ref)
        self.assertEqual([items[0]],selected)
        self.assertEqual(original,items)

    def test_other_sources_keep_existing_behavior(self):
        old=self.item('2026-07-01');old['source_id']='other'
        self.assertEqual([old],builder.filter_source_freshness([old],self.config,self.ref))

    def test_invalid_reference_fails_visibly(self):
        with self.assertRaises(ValueError):
            builder.filter_source_freshness([],self.config,'invalid')

    def test_baseline_does_not_fill_five_with_old_items(self):
        status=[{'name':'Security','type':'core','status':'ok'}]
        recent=self.item('2026-10-01');old=self.item('2026-07-01');old['id']='old'
        selected,_=builder.select_candidates_for_mode([old,recent],status,self.config,self.ref,mode='baseline')
        self.assertEqual(['news'],[x['id'] for x in selected])

    def test_old_items_do_not_reach_hybrid_provider(self):
        provider=mock.Mock(side_effect=AssertionError('No API expected'))
        status=[{'name':'Security','type':'core','status':'ok'}]
        with tempfile.TemporaryDirectory() as tmp:
            selected,_=builder.select_candidates_for_mode([self.item('2026-07-01')],status,
                self.config,self.ref,mode='hybrid',hybrid_provider=provider,
                cache_path=Path(tmp)/'cache.json')
        self.assertEqual([],selected)
        provider.assert_not_called()

if __name__=='__main__':unittest.main()
