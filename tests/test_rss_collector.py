"""RSS-Vertrag und Fehlerpfade, ohne Netz oder Modellaufrufe."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rss_collector', ROOT/'scripts/collector.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)

class RssTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(id='bsi', name='BSI', role='primary', adapter='rss',
            url='https://www.bsi.bund.de/feed.xml', allowed_domains=['www.bsi.bund.de'],
            category=['IT Security'], keywords=['KI', 'Ransomware'],
            exclude_keywords=['Webinar'], max_items=5)

    def entry(self, title='KI-Sicherheit', link='https://www.bsi.bund.de/news/ki',
              date='<pubDate>Tue, 06 Oct 2026 08:00:00 GMT</pubDate>',
              summary='<description><![CDATA[<p>Unternehmen schützen KI-Systeme.</p>]]></description>'):
        return f'<item><title>{title}</title><link>{link}</link>{date}{summary}</item>'

    def read(self, entries):
        r = mock.Mock(content=f'<rss version="2.0"><channel><title>BSI</title><link>https://www.bsi.bund.de</link><description>News</description>{entries}</channel></rss>'.encode())
        with mock.patch.object(collector.requests, 'get', return_value=r) as get:
            result = collector.collect_source(self.source)
            get.assert_called_once()
        return result

    def test_original_url_plaintext_date_and_identity(self):
        item = self.read(self.entry())[0]
        self.assertEqual('2026-10-06T10:00:00+02:00', item['published_at'])
        self.assertEqual('Unternehmen schützen KI-Systeme.', item['raw_excerpt'])
        self.assertEqual('https://www.bsi.bund.de/news/ki', item['source_url'])
        self.assertEqual('primary', item['verification'])
        self.assertEqual('ok', item['status'])
        self.assertEqual(item['id'], self.read(self.entry())[0]['id'])

    def test_editorial_discovery_source_is_secondary(self):
        self.source['role']='discovery'
        self.assertEqual('secondary',self.read(self.entry())[0]['verification'])

    def test_missing_date_is_visible_not_invented(self):
        item = self.read(self.entry(date=''))[0]
        self.assertIsNone(item['published_at'])
        self.assertEqual('degraded', item['status'])

    def test_missing_excerpt_is_visible(self):
        self.assertEqual('degraded', self.read(self.entry(summary=''))[0]['status'])

    def test_untrusted_links_and_duplicates_rejected(self):
        entries = ''.join(self.entry(link=url) for url in [
            'https://evil.example/news', 'http://www.bsi.bund.de/news',
            'https://www.bsi.bund.de.evil.example/news',
            'https://user:pass@www.bsi.bund.de/news',
            'https://www.bsi.bund.de/news/ki', 'https://www.bsi.bund.de/news/ki'])
        self.assertEqual(1, len(self.read(entries)))

    def test_irrelevant_and_event_items_filtered(self):
        self.assertEqual([], self.read(self.entry(title='Sommerfest', summary='') +
            self.entry(title='KI Webinar')))

    def test_max_items_and_empty_feed(self):
        self.source['max_items'] = 1
        self.assertEqual(1, len(self.read(self.entry() + self.entry(link='https://www.bsi.bund.de/news/two'))))
        self.assertEqual([], self.read(''))

    def test_invalid_feed_and_http_error_propagate(self):
        with mock.patch.object(collector.requests, 'get', return_value=mock.Mock(content=b'<html>blocked</html>')):
            with self.assertRaises(RuntimeError):
                collector.fetch_rss(self.source)
        r = mock.Mock()
        r.raise_for_status.side_effect = collector.requests.HTTPError('403')
        with mock.patch.object(collector.requests, 'get', return_value=r):
            with self.assertRaises(collector.requests.HTTPError):
                collector.fetch_rss(self.source)

if __name__ == '__main__':
    unittest.main()
