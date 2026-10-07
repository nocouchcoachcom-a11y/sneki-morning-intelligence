import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec=importlib.util.spec_from_file_location('detail',Path(__file__).resolve().parents[1]/'scripts/editorial_depth.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

class EditorialDepthTests(unittest.TestCase):
    item={'id':'one','source_id':'official','source':'Official','source_type':'primary','title':'KI im Projektmanagement','published_at':'2026-10-01'}
    config=[{'id':'official','url':'https://example.org/news'}]
    def prediction(self,id='one'):
        return dict(id=id,assessment_status='scored',title_de='KI im Projektmanagement',summary=' '.join(['Belegter']*110),why_relevant='Redaktionelle Einordnung.',practice_example='Hypothetischer Test.',next_step='Quelle prüfen.',limitations='Grenzen bleiben offen.')
    def response(self,items):
        return dict(usage={'input_tokens':100,'output_tokens':300},output=[dict(type='message',content=[dict(type='output_text',text=json.dumps({'items':items}))])])
    def test_disabled_never_fetches_or_calls_model(self):
        fetcher=Mock(side_effect=AssertionError());provider=Mock(side_effect=AssertionError())
        result,stats=d.enrich([self.item],self.config,'unused.json',fetcher=fetcher,provider=provider)
        self.assertEqual([self.item],result);self.assertEqual(0,stats['api_calls']);fetcher.assert_not_called();provider.assert_not_called()
    def test_validated_cache_reuses_results_without_second_api_request(self):
        fetcher=Mock(return_value='Artikeltext '*100);provider=Mock(return_value=self.response([self.prediction()]))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cache.json'
            result,stats=d.enrich([self.item],self.config,path,enabled=True,fetcher=fetcher,provider=provider)
            self.assertEqual(1,stats['api_calls']);self.assertTrue(result[0]['_editorial_detail'])
            result,stats=d.enrich([self.item],self.config,path,enabled=True,fetcher=fetcher,provider=provider)
            self.assertEqual(1,stats['cache_hits']);self.assertEqual(0,stats['api_calls']);self.assertEqual(1,provider.call_count)
        self.assertNotIn('_editorial_detail',self.item)
    def test_invalid_status_retains_usage_and_does_not_retry(self):
        prediction=self.prediction();prediction['assessment_status']='adequate'
        provider=Mock(return_value=self.response([prediction]))
        with tempfile.TemporaryDirectory() as tmp:
            result,stats=d.enrich([self.item],self.config,Path(tmp)/'cache.json',enabled=True,fetcher=Mock(return_value='Text '*200),provider=provider)
        self.assertEqual([self.item],result);self.assertEqual(1,provider.call_count);self.assertEqual(300,stats['usage']['output_tokens']);self.assertIn('fallback',stats)
    def test_failed_article_does_not_call_model(self):
        provider=Mock(side_effect=AssertionError())
        with tempfile.TemporaryDirectory() as tmp:
            result,stats=d.enrich([self.item],self.config,Path(tmp)/'cache.json',enabled=True,fetcher=Mock(side_effect=ValueError('Unavailable')),provider=provider)
        self.assertEqual(1,stats['article_failures']);self.assertEqual([self.item],result);provider.assert_not_called()
    def test_budget_blocks_before_provider(self):
        provider=Mock(side_effect=AssertionError())
        with tempfile.TemporaryDirectory() as tmp:
            result,stats=d.enrich([self.item],self.config,Path(tmp)/'cache.json',enabled=True,fetcher=Mock(return_value='X'*100000),provider=provider)
        self.assertEqual(0,stats['api_calls']);provider.assert_not_called()
    def test_schema_has_exact_status_enum(self):
        p=d.build_request([{'id':'one','article_text':'Text'}])
        props=p['text']['format']['schema']['properties']['items']['items']['properties']
        self.assertEqual(['scored','insufficient_input'],props['assessment_status']['enum']);self.assertFalse(p['store'])
    def test_extraction_uses_body_not_meta_and_stops_before_comments(self):
        html='<html><meta name="description" content="Tiny description"><body><main><h1>Topic</h1><nav><p>Navigation</p></nav><p>Actual detailed article.</p><h2>Kommentare</h2><p>Ignore comments.</p></main></body></html>'
        self.assertEqual('Actual detailed article.',d.extract_article(html))
    def test_builder_keeps_full_detail_and_reports_cost_without_real_api(self):
        spec=importlib.util.spec_from_file_location('builder',Path(__file__).resolve().parents[1]/'scripts/build_briefing.py')
        b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
        item={**self.item,'source':'Official','source_url':'https://example.org/article','raw_excerpt':'KI im Projektmanagement','verification':'primary','status':'ok','category':['AI & PM'],'collected_at':'2026-10-07T07:00:00+02:00'}
        html='<html><main><h1>KI im Projektmanagement</h1><p>'+('Detaillierter Artikeltext. '*50)+'</p></main></html>'
        get=Mock(return_value=Mock(status_code=200,headers={'Content-Type':'text/html'},content=html.encode()))
        response=self.response([self.prediction()]);post=Mock(return_value=Mock(status_code=200,json=Mock(return_value=response)))
        from datetime import datetime
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'SNEKI_EDITORIAL_ENABLED':'1','SNEKI_RANKING_MODE':'baseline','OPENAI_API_KEY':'offline-fixture','GITHUB_EVENT_NAME':'schedule'}),patch.object(b,'DATA',Path(tmp)),patch.object(b,'read_source_config',return_value=self.config),patch.object(b,'now_local',return_value=datetime.fromisoformat('2026-10-07T07:00:00+02:00')),patch('requests.get',get),patch('requests.post',post):
            b.build_edition('offline',{'items':[item],'source_status':[{'name':'Official','type':'core','status':'ok'}]},preview=True)
            edition=json.loads((Path(tmp)/'manual-preview.json').read_text())
        self.assertTrue(edition['items'][0]['editorial_depth']);self.assertEqual(110,len(edition['items'][0]['summary'].split()))
        self.assertEqual(1,edition['editorial_depth_status']['api_calls']);self.assertEqual(1,post.call_count)
        self.assertEqual(110,len(edition['editorial_brief']['summary'].split()))
    def test_duplicate_and_short_predictions_rejected(self):
        with self.assertRaises(ValueError):d.validate_predictions([self.prediction(),self.prediction()],['one','two'])
        short=self.prediction();short['summary']='Too short'
        with self.assertRaises(ValueError):d.validate_predictions([short],['one'])

if __name__=='__main__':unittest.main()
