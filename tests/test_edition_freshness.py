"""Offline regression tests for current news and separate background."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('edition_builder',Path(__file__).resolve().parents[1]/'scripts/build_briefing.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class EditionFreshnessTests(unittest.TestCase):
    ref='2026-10-07T07:26:23+02:00'
    status=[{'name':'Official','type':'core','status':'ok'}]
    def item(self,id,date):
        return dict(id=id,published_at=date,source_id='official',source='Official',source_type='primary',verification='primary',status='ok',title='AI governance requirements',raw_excerpt='AI governance for companies',category=['EU AI Act'],collected_at=self.ref)
    def select(self,items,**kw):
        return b.select_edition_candidates(items,self.status,[],self.ref,mode='baseline',**kw)
    def test_old_dominant_items_do_not_displace_new_news(self):
        items=[self.item('old'+str(i),'2026-07-01') for i in range(8)]+[self.item('new','2026-10-01')]
        original=copy.deepcopy(items)
        current,background,_=self.select(items)
        self.assertEqual(['new'],[x['id'] for x in current])
        self.assertEqual(5,len(background));self.assertEqual(original,items)
    def test_boundary_unknown_invalid_future(self):
        dates=['2026-09-30T07:26:23+02:00','2026-09-30T07:26:22+02:00',None,'invalid','2026-10-08']
        current,background,_=self.select([self.item(str(i),d) for i,d in enumerate(dates)])
        self.assertEqual(['0'],[x['id'] for x in current]);self.assertEqual(['1'],[x['id'] for x in background])
    def test_old_only_edition_does_not_call_hybrid_provider(self):
        provider=mock.Mock(side_effect=AssertionError('No API allowed'))
        with tempfile.TemporaryDirectory() as tmp:
            current,background,_=b.select_edition_candidates([self.item('old','2026-07-01')],self.status,[],self.ref,mode='hybrid',hybrid_provider=provider,cache_path=Path(tmp)/'cache.json')
        self.assertEqual([],current);self.assertEqual(1,len(background));provider.assert_not_called()
    def test_background_not_top_five(self):
        story=b.make_story(self.item('old','2026-07-01'),1,content_kind='background')
        self.assertFalse(story['is_top5']);self.assertEqual('background',story['content_kind'])
    def test_failed_source_never_used_for_background(self):
        current,background,_=b.select_edition_candidates([self.item('old','2026-07-01')],[{'name':'Official','type':'core','status':'failed'}],[],self.ref,mode='baseline')
        self.assertEqual([],current);self.assertEqual([],background)

if __name__=='__main__':unittest.main()
