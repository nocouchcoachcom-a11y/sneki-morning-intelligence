"""ENISA-Karten: Datum, Herkunft, Filter und sichtbare Fehler."""
import unittest
from unittest import mock
from test_rss_collector import collector

class EnisaTests(unittest.TestCase):
    def setUp(self):
        self.source=dict(id='enisa',name='ENISA',role='primary',category=['IT Security'],
            adapter='enisa_news',url='https://www.enisa.europa.eu/news',
            allowed_domains=['www.enisa.europa.eu'],keywords=['Cybersecurity','AI'],
            exclude_keywords=['Webinar'],max_items=5)

    def card(self,title='Cybersecurity for companies',href='/news/skills ',
             date='2026-09-30T13:55:56+03:00',excerpt='Manage digital risks.'):
        time=f'<time datetime="{date}"></time>' if date else ''
        return f'<div class="publications-item"><div class="publication-content"><h3><a href="{href}">{title}</a></h3><p class="metadata">{time}</p><div class="content"><p>{excerpt}</p></div></div></div>'

    def read(self,cards):
        r=mock.Mock(text=f'<div class="view-content">{cards}</div>')
        with mock.patch.object(collector.requests,'get',return_value=r) as get:
            result=collector.collect_source(self.source)
            get.assert_called_once()
        return result

    def test_card_fields_and_whitespace_in_url(self):
        x=self.read(self.card())[0]
        self.assertEqual('https://www.enisa.europa.eu/news/skills',x['source_url'])
        self.assertEqual('2026-09-30T12:55:56+02:00',x['published_at'])
        self.assertEqual('Manage digital risks.',x['raw_excerpt'])
        self.assertEqual('ok',x['status'])

    def test_duplicates_untrusted_and_non_news_links(self):
        html=self.card()+self.card()+self.card(href='https://evil.example/news/x')+self.card(href='/topics/ai')
        self.assertEqual(1,len(self.read(html)))

    def test_filters_do_not_force_items(self):
        self.assertEqual([],self.read(self.card(title='Cybersecurity Webinar')+self.card(title='Summer party')))

    def test_missing_or_invalid_date_is_degraded(self):
        for date in ('','invalid'):
            x=self.read(self.card(date=date))[0]
            self.assertIsNone(x['published_at'])
            self.assertEqual('degraded',x['status'])

    def test_sort_before_limit(self):
        self.source['max_items']=1
        html=self.card(href='/news/old',date='2026-07-01T10:00:00Z')+self.card()
        self.assertEqual('https://www.enisa.europa.eu/news/skills',self.read(html)[0]['source_url'])

    def test_structure_change_and_http_error_visible(self):
        with self.assertRaises(RuntimeError):self.read('<p>No news cards</p>')
        r=mock.Mock();r.raise_for_status.side_effect=collector.requests.HTTPError('500')
        with mock.patch.object(collector.requests,'get',return_value=r):
            with self.assertRaises(collector.requests.HTTPError):collector.fetch_enisa_news(self.source)

if __name__=='__main__':unittest.main()
