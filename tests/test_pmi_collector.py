import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "collector", ROOT / "scripts" / "collector.py"
)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class Response:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class PmiCollectorTests(unittest.TestCase):
    def source(self):
        return {
            "id": "pmi-ai",
            "name": "PMI – Artificial Intelligence",
            "role": "primary",
            "category": ["AI & PM"],
            "url": "https://www.pmi.org/blog?userTagIDSort=11122",
            "allowed_domains": ["www.pmi.org"],
            "keywords": ["AI", "Artificial Intelligence"],
            "max_items": 5,
        }

    def test_extracts_matching_official_blog_card(self):
        html = """
        <section>
          <article>
            <h3>AI for Project Managers: Beyond Quick Wins</h3>
            <div>24 September 2026</div>
            <p>Explore how AI can support project managers while human review remains essential.</p>
            <a href="/blog/ai-for-project-managers-beyond-quick-wins">Read Post</a>
          </article>
          <article>
            <h3>Construction talent planning</h3>
            <div>29 September 2026</div>
            <p>This article discusses workforce planning, retention and recruiting.</p>
            <a href="/blog/construction-talent-planning">Read Post</a>
          </article>
        </section>
        """
        with mock.patch.object(collector.requests, "get", return_value=Response(html)):
            items = collector.fetch_pmi_blog(self.source())

        self.assertEqual(1, len(items))
        self.assertEqual("AI for Project Managers: Beyond Quick Wins", items[0]["title"])
        self.assertEqual("2026-09-24", items[0]["published_at"])
        self.assertEqual("ok", items[0]["status"])
        self.assertEqual(
            "https://www.pmi.org/blog/ai-for-project-managers-beyond-quick-wins",
            items[0]["source_url"],
        )

    def test_rejects_external_blog_link(self):
        html = """
        <article>
          <h3>AI for Projects</h3>
          <div>24 September 2026</div>
          <p>Artificial Intelligence guidance for project teams and governance.</p>
          <a href="https://attacker.example/blog/item">Read Post</a>
        </article>
        """
        with mock.patch.object(collector.requests, "get", return_value=Response(html)):
            with self.assertRaisesRegex(RuntimeError, "Keine passenden PMI"):
                collector.fetch_pmi_blog(self.source())

    def test_fails_visibly_when_structure_has_no_articles(self):
        with mock.patch.object(
            collector.requests, "get", return_value=Response("<html><h1>PMI</h1></html>")
        ):
            with self.assertRaisesRegex(RuntimeError, "Keine passenden PMI"):
                collector.fetch_pmi_blog(self.source())


if __name__ == "__main__":
    unittest.main()
