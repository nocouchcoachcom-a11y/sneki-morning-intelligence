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
    def test_source_label_does_not_establish_topic(self):
        item=self.item('edic','2026-10-01')
        item.update(title='EDIC agri-food launched',raw_excerpt='Digital infrastructure for agriculture')
        self.assertEqual(('Digitalisierung & Kontext',False),b.editorial_topic(item))
        original=copy.deepcopy(item)
        current,background,_=self.select([item])
        self.assertEqual([],current)
        self.assertTrue(background[0]['_reading'])
        story=b.make_story(background[0],1,content_kind='background')
        self.assertEqual('reading',story['content_kind']);self.assertFalse(story['is_top5'])
        self.assertEqual(original,item)
    def test_recent_reading_remains_visible_among_old_background(self):
        reading=self.item('reading','2026-10-01')
        reading.update(title='Projektmanagement PISA',raw_excerpt='Projektmanagement Studie')
        current,background,_=self.select([self.item('old'+str(i),'2026-07-01') for i in range(8)]+[reading])
        self.assertEqual([],current);self.assertEqual('reading',background[0]['id']);self.assertEqual(5,len(background))
    def test_unrelated_recent_article_is_not_used_to_fill_readings(self):
        unrelated=self.item('rockets','2026-10-01')
        unrelated.update(title='Meet the rocket builders',raw_excerpt='The people behind propulsion')
        current,background,_=self.select([unrelated])
        self.assertEqual([],current);self.assertEqual([],background)
    def test_core_topics_and_general_pm(self):
        for title,expected,core in [('KI im Projektmanagement','AI & PM',True),('AI Act requirements','EU AI Act',True),('Datenschutz im Unternehmen','DSGVO & Ethik',True),('Cybersecurity guidance','IT Security',True),('Projektmanagement: PISA Studie','Projektmanagement',False)]:
            with self.subTest(title=title):
                self.assertEqual((expected,core),b.editorial_topic(dict(title=title,raw_excerpt='',category=['EU AI Act'])))
    def test_cached_summary_and_explicit_source_excerpt(self):
        item=self.item('one','2026-10-01')
        item['_hybrid_content']=dict(summary='Deutsche Zusammenfassung.',why_relevant='Belegte Bedeutung.',watch_next='Quelle beobachten.')
        story=b.make_story(item,1)
        self.assertEqual('Deutsche Zusammenfassung.',story['summary']);self.assertEqual('generated',story['summary_origin'])
        item.pop('_hybrid_content')
        story=b.make_story(item,1)
        self.assertEqual(item['raw_excerpt'],story['summary']);self.assertEqual('source_excerpt',story['summary_origin'])
    def test_failed_source_never_used_for_background(self):
        current,background,_=b.select_edition_candidates([self.item('old','2026-07-01')],[{'name':'Official','type':'core','status':'failed'}],[],self.ref,mode='baseline')
        self.assertEqual([],current);self.assertEqual([],background)

class SourceUrlDeduplicationTests(unittest.TestCase):
    def setUp(self):
        self.old=dict(id='old',source_id='official',source_url='https://example.org/old',title='Original title',collected_at='2026-10-01T00:00:00Z')
        self.new=dict(self.old,id='new',source_url='https://example.org/new',title='Updated title')
        self.config=[{'id':'official','url_aliases':{'https://example.org/old':'https://example.org/new'}}]
    def test_verified_alias_keeps_canonical_article_without_mutating_raw(self):
        raw=[self.old,self.new];original=copy.deepcopy(raw)
        for records in [raw,list(reversed(raw))]:
            self.assertEqual([self.new],b.deduplicate_source_urls(records,self.config))
        self.assertEqual(original,raw)
    def test_similar_titles_without_alias_remain_separate(self):
        self.assertEqual(2,len(b.deduplicate_source_urls([self.old,self.new],[])))
    def test_alias_does_not_merge_independent_sources(self):
        other=dict(self.new,source_id='other')
        self.assertEqual(2,len(b.deduplicate_source_urls([self.old,other],self.config)))
    def test_same_url_keeps_latest_observation(self):
        later=dict(self.old,id='later',last_seen_at='2026-10-07T00:00:00Z')
        self.assertEqual([later],b.deduplicate_source_urls([later,self.old],[]))

if __name__=='__main__':unittest.main()
