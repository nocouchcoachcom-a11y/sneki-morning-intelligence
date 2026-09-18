"""Offline-Tests für die vorhandene sneKI-V1-Pipeline.

Die Tests rufen keine Webseiten oder APIs auf. Sie prüfen nur die lokale
Projektstruktur, die vorhandenen JSON-Daten und den Briefing Builder.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from datetime import datetime, timedelta
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_RAW_PATH = ROOT / "tests" / "fixtures" / "ranking_benchmark_raw_v1.json"
BENCHMARK_SOURCES_PATH = (
    ROOT / "tests" / "fixtures" / "ranking_benchmark_sources_v1.json"
)


def load_ranking_benchmark():
    """Lädt den unveränderlichen 11-Item-Benchmark statt produktiver Live-Daten."""
    raw = json.loads(BENCHMARK_RAW_PATH.read_text(encoding="utf-8"))
    sources = json.loads(BENCHMARK_SOURCES_PATH.read_text(encoding="utf-8"))[
        "sources"
    ]
    return raw, sources


def load_builder():
    """Lädt den Builder direkt aus scripts/, ohne ein Python-Paket zu verlangen."""
    path = ROOT / "scripts" / "build_briefing.py"
    spec = importlib.util.spec_from_file_location("build_briefing", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Builder konnte nicht geladen werden: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_collector():
    """Lädt den Collector direkt aus scripts/, ohne einen Netzaufruf auszulösen."""
    path = ROOT / "scripts" / "collector.py"
    spec = importlib.util.spec_from_file_location("collector", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Collector konnte nicht geladen werden: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SitemapSourceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.collector = load_collector()

    @staticmethod
    def response(text):
        response = mock.Mock()
        response.text = text
        response.raise_for_status.return_value = None
        return response

    def source(self, source_id="gpm-pm", status_type="core"):
        return {
            "id": source_id,
            "name": "Test PM Source",
            "role": "primary",
            "priority": "MUST",
            "status_type": status_type,
            "category": ["AI & PM"],
            "url": "https://example.org/articles/",
            "sitemap_urls": ["https://example.org/sitemap.xml"],
            "article_path_prefixes": ["/articles/"],
            "allowed_domains": ["example.org"],
            "adapter": "sitemap_articles",
            "keywords": ["Artificial Intelligence", "PMO"],
            "scan_limit": 10,
            "max_items": 5,
            "enabled": True,
        }

    def test_relevant_article_is_collected_and_irrelevant_article_is_rejected(self):
        sitemap = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.org/articles/ai-governance</loc><lastmod>2026-09-17</lastmod></url>
          <url><loc>https://example.org/articles/summer-party</loc><lastmod>2026-09-16</lastmod></url>
        </urlset>"""
        relevant = """<html><main><article><header>
          <time datetime="2026-09-15">15 Sept 2026</time>
          <h1>Artificial Intelligence governance for projects</h1>
        </header><p>A practical governance framework for project leaders.</p></article></main></html>"""
        irrelevant = """<html><main><article><header>
          <time datetime="2026-09-14">14 Sept 2026</time>
          <h1>Photos from the summer party</h1>
        </header><p>Colleagues met for an informal celebration.</p></article></main></html>"""

        with mock.patch.object(
            self.collector.requests,
            "get",
            side_effect=[
                self.response(sitemap),
                self.response(relevant),
                self.response(irrelevant),
            ],
        ):
            items = self.collector.fetch_sitemap_articles(self.source())

        self.assertEqual(1, len(items))
        self.assertEqual("Artificial Intelligence governance for projects", items[0]["title"])
        self.assertEqual("2026-09-15", items[0]["published_at"])
        self.assertEqual("https://example.org/articles/ai-governance", items[0]["source_url"])

    def test_apm_style_article_uses_original_url_date_and_excerpt(self):
        sitemap = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.org/articles/pmo-value</loc><lastmod>2026-09-17</lastmod></url>
        </urlset>"""
        article = """<html><main><article><header>
          <time datetime="2026-09-17">17 Sept 2026</time><h1>Building a useful PMO</h1>
        </header><p>A PMO can improve portfolio decisions and project governance.</p></article></main></html>"""

        with mock.patch.object(
            self.collector.requests,
            "get",
            side_effect=[self.response(sitemap), self.response(article)],
        ):
            items = self.collector.fetch_sitemap_articles(self.source("apm-pm"))

        self.assertEqual("2026-09-17", items[0]["published_at"])
        self.assertEqual("https://example.org/articles/pmo-value", items[0]["source_url"])
        self.assertIn("portfolio decisions", items[0]["raw_excerpt"])

    def test_gpm_irrelevant_article_is_rejected(self):
        sitemap = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.org/articles/sommerfest</loc><lastmod>2026-09-17</lastmod></url>
        </urlset>"""
        article = """<html><main><article><header>
          <time datetime="2026-09-17">17.09.2026</time><h1>Fotos vom Sommerfest</h1>
        </header><p>Mitglieder trafen sich bei Musik und gutem Wetter zum Feiern.</p></article></main></html>"""

        with mock.patch.object(
            self.collector.requests,
            "get",
            side_effect=[self.response(sitemap), self.response(article)],
        ):
            items = self.collector.fetch_sitemap_articles(self.source("gpm-pm"))

        self.assertEqual([], items)

    def test_apm_irrelevant_article_is_rejected(self):
        sitemap = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.org/articles/social-event</loc><lastmod>2026-09-17</lastmod></url>
        </urlset>"""
        article = """<html><main><article><header>
          <time datetime="2026-09-17">17 Sept 2026</time><h1>Pictures from our social event</h1>
        </header><p>Members enjoyed an informal evening with food and music.</p></article></main></html>"""

        with mock.patch.object(
            self.collector.requests,
            "get",
            side_effect=[self.response(sitemap), self.response(article)],
        ):
            items = self.collector.fetch_sitemap_articles(self.source("apm-pm"))

        self.assertEqual([], items)

    def test_missing_publication_date_is_not_invented(self):
        sitemap = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.org/articles/ai-without-date</loc><lastmod>2026-09-17</lastmod></url>
        </urlset>"""
        article = """<html><main><article><header>
          <h1>Artificial Intelligence in project governance</h1>
        </header><p>Project leaders use a governance framework for responsible decisions.</p></article></main></html>"""

        with mock.patch.object(
            self.collector.requests,
            "get",
            side_effect=[self.response(sitemap), self.response(article)],
        ):
            items = self.collector.fetch_sitemap_articles(self.source())

        self.assertIsNone(items[0]["published_at"])
        self.assertEqual("degraded", items[0]["status"])

    def test_source_matrix_marks_gpm_apm_core_and_pmi_optional(self):
        sources = {
            source["id"]: source
            for source in json.loads(
                (ROOT / "sources.json").read_text(encoding="utf-8")
            )["sources"]
        }

        self.assertEqual("core", sources["gpm-project-management"]["status_type"])
        self.assertEqual("core", sources["apm-project-management"]["status_type"])
        self.assertEqual("optional", sources["pmi-ai"]["status_type"])

    def test_failed_pm_source_does_not_stop_remaining_sources(self):
        failed = self.source()
        working = {**self.source("working-pm"), "name": "Working PM Source"}
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        temporary_data = Path(temporary_directory.name)

        with mock.patch.object(self.collector, "DATA", temporary_data), mock.patch.object(
            self.collector,
            "SOURCES",
            {"sources": [failed, working]},
        ), mock.patch.object(
            self.collector,
            "collect_source",
            side_effect=[RuntimeError("offline"), [{
                "id": "working-item",
                "source_id": "working-pm",
                "source": "Working PM Source",
                "source_type": "primary",
                "source_url": "https://example.org/articles/working",
                "category": ["AI & PM"],
                "title": "Working article",
                "raw_excerpt": "Useful PMO guidance",
                "published_at": "2026-09-17",
                "collected_at": "2026-09-17T10:00:00+02:00",
                "verification": "primary",
                "status": "ok",
                "content_hash": "hash",
            }]],
        ):
            self.collector.main()

        payload = json.loads((temporary_data / "raw-items.json").read_text(encoding="utf-8"))
        statuses = {entry["name"]: entry for entry in payload["source_status"]}
        self.assertEqual("failed", statuses["Test PM Source"]["status"])
        self.assertEqual("core", statuses["Test PM Source"]["type"])
        self.assertEqual("ok", statuses["Working PM Source"]["status"])
        self.assertEqual(["working-item"], [item["id"] for item in payload["items"]])

    def test_source_status_preserves_supported_matrix_types(self):
        source_types = ("core", "optional", "standards", "research")
        sources = [
            {
                **self.source(f"source-{status_type}", status_type=status_type),
                "name": f"Source {status_type}",
            }
            for status_type in source_types
        ]
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        temporary_data = Path(temporary_directory.name)

        with mock.patch.object(self.collector, "DATA", temporary_data), mock.patch.object(
            self.collector,
            "SOURCES",
            {"sources": sources},
        ), mock.patch.object(self.collector, "collect_source", return_value=[]):
            self.collector.main()

        payload = json.loads((temporary_data / "raw-items.json").read_text(encoding="utf-8"))
        self.assertEqual(
            list(source_types),
            [entry["type"] for entry in payload["source_status"]],
        )


class ProjectLayoutTests(unittest.TestCase):
    def test_required_runtime_files_are_in_project_root(self):
        required = [
            "requirements.txt",
            "sources.json",
            "data/raw-items.json",
            "scripts/collector.py",
            "scripts/build_briefing.py",
            ".github/workflows/morning-intelligence.yml",
        ]
        missing = [name for name in required if not (ROOT / name).is_file()]
        self.assertEqual([], missing, f"Fehlende Dateien: {missing}")

    def test_source_ids_are_unique(self):
        config = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
        sources = config.get("sources", [])
        ids = [source.get("id") for source in sources]
        self.assertTrue(sources, "Mindestens eine Quelle wird benötigt.")
        self.assertNotIn(None, ids)
        self.assertEqual(len(ids), len(set(ids)), "Quellen-IDs müssen eindeutig sein.")


class RawContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads((ROOT / "data" / "raw-items.json").read_text(encoding="utf-8"))

    def test_raw_top_level_contract(self):
        self.assertEqual("1.0", self.raw.get("schema_version"))
        self.assertIsInstance(self.raw.get("collected_at"), str)
        self.assertIsInstance(self.raw.get("items"), list)
        self.assertIsInstance(self.raw.get("source_status"), list)

    def test_raw_items_have_required_fields_and_unique_ids(self):
        required = {
            "id",
            "source_id",
            "source",
            "source_type",
            "source_url",
            "category",
            "title",
            "raw_excerpt",
            "published_at",
            "collected_at",
            "verification",
            "status",
            "content_hash",
            "first_seen_at",
            "last_seen_at",
        }
        ids = []
        for position, item in enumerate(self.raw["items"], start=1):
            self.assertEqual(set(), required - set(item), f"Item {position} ist unvollständig.")
            ids.append(item["id"])
        self.assertEqual(len(ids), len(set(ids)), "Raw-Item-IDs müssen eindeutig sein.")

    def test_source_status_values_are_known(self):
        allowed = {"ok", "degraded", "failed"}
        for status in self.raw["source_status"]:
            self.assertIn(status.get("status"), allowed)


class SemanticReferenceTests(unittest.TestCase):
    def test_all_reference_items_are_complete_and_valid(self):
        reference = json.loads(
            (ROOT / "tests" / "fixtures" / "semantic_reference.json").read_text(
                encoding="utf-8"
            )
        )
        raw, _ = load_ranking_benchmark()
        known_item_ids = {item["id"] for item in raw["items"]}
        score_fields = (
            "expected_management_relevance",
            "expected_actionability",
            "expected_significance",
        )

        self.assertEqual(11, len(reference))
        reference_ids = [item["item_id"] for item in reference]
        self.assertEqual(len(reference_ids), len(set(reference_ids)))
        self.assertEqual(set(), set(reference_ids) - known_item_ids)

        for item in reference:
            with self.subTest(item_id=item["item_id"]):
                self.assertIn(
                    item.get("expected_assessment_status"),
                    {"scored", "insufficient_input"},
                )
                self.assertIsInstance(item.get("reference_note"), str)
                self.assertTrue(item["reference_note"].strip())

                scores = [item.get(field) for field in score_fields]
                self.assertTrue(
                    all(isinstance(score, int) and 0 <= score <= 3 for score in scores)
                )
                if item["expected_assessment_status"] == "insufficient_input":
                    self.assertEqual([0, 0, 0], scores)


class BriefingBuilderTests(unittest.TestCase):
    def setUp(self):
        self.builder = load_builder()
        self.raw = json.loads((ROOT / "data" / "raw-items.json").read_text(encoding="utf-8"))

    def test_candidate_filter_excludes_failed_and_social_items(self):
        items = [
            {
                "id": "primary-ok",
                "source": "Primary Source",
                "source_type": "primary",
                "verification": "primary",
                "status": "ok",
                "last_seen_at": "2026-09-01T10:00:00+02:00",
            },
            {
                "id": "social-ok",
                "source": "Social Source",
                "source_type": "social",
                "verification": "social",
                "status": "ok",
                "last_seen_at": "2026-09-02T10:00:00+02:00",
            },
            {
                "id": "primary-failed",
                "source": "Primary Source",
                "source_type": "primary",
                "verification": "primary",
                "status": "failed",
                "last_seen_at": "2026-09-03T10:00:00+02:00",
            },
        ]
        source_status = [
            {"name": "Primary Source", "type": "core", "status": "ok"},
            {"name": "Social Source", "type": "social", "status": "ok"},
        ]
        selected = self.builder.choose_candidates(items, source_status)
        self.assertEqual(["primary-ok"], [item["id"] for item in selected])

    def test_candidates_are_sorted_by_published_at_newest_first(self):
        items = [
            {
                "id": "new",
                "source": "Test Source",
                "source_type": "primary",
                "verification": "primary",
                "status": "ok",
                "published_at": "2026-09-03",
                "last_seen_at": "2026-09-03T10:00:00+02:00",
            },
            {
                "id": "old",
                "source": "Test Source",
                "source_type": "primary",
                "verification": "primary",
                "status": "ok",
                "published_at": "2026-09-01",
                "last_seen_at": "2026-09-01T10:00:00+02:00",
            },
            {
                "id": "mid",
                "source": "Test Source",
                "source_type": "primary",
                "verification": "primary",
                "status": "ok",
                "published_at": "2026-09-02",
                "last_seen_at": "2026-09-02T10:00:00+02:00",
            },
        ]

        source_status = [
            {"name": "Test Source", "type": "core", "status": "ok"},
        ]
        selected = self.builder.choose_candidates(items, source_status)

        self.assertEqual(["new", "mid", "old"], [item["id"] for item in selected])

    def test_missing_or_invalid_published_at_uses_first_seen_at_fallback(self):
        items = [
            {
                "id": "missing-published-at",
                "source": "Test Source",
                "source_type": "primary",
                "verification": "primary",
                "status": "ok",
                "published_at": None,
                "first_seen_at": "2026-09-03T10:00:00+02:00",
                "last_seen_at": "2026-09-04T10:00:00+02:00",
            },
            {
                "id": "invalid-published-at",
                "source": "Test Source",
                "source_type": "primary",
                "verification": "primary",
                "status": "ok",
                "published_at": "kein-datum",
                "first_seen_at": "2026-09-02T10:00:00+02:00",
                "last_seen_at": "2026-09-01T10:00:00+02:00",
            },
        ]

        source_status = [
            {"name": "Test Source", "type": "core", "status": "ok"},
        ]
        selected = self.builder.choose_candidates(items, source_status)

        self.assertEqual(
            ["missing-published-at", "invalid-published-at"],
            [item["id"] for item in selected],
        )

    def test_total_failure_is_rejected_without_writing_production_file(self):
        raw = {
            "items": [],
            "source_status": [
                {"name": "Source A", "type": "core", "status": "failed"},
                {"name": "Source B", "type": "core", "status": "failed"},
            ],
        }

        for existing_content in (None, "existing-production"):
            with self.subTest(existing_file=existing_content is not None):
                with tempfile.TemporaryDirectory() as directory:
                    temporary_data = Path(directory)
                    current = temporary_data / "morning-intelligence.json"
                    if existing_content is not None:
                        current.write_text(existing_content, encoding="utf-8")

                    self.builder.DATA = temporary_data

                    with self.assertRaisesRegex(RuntimeError, "nicht publishable"):
                        self.builder.build_edition("total-failure", raw)

                    if existing_content is None:
                        self.assertFalse(current.exists())
                    else:
                        self.assertEqual(existing_content, current.read_text(encoding="utf-8"))
                    self.assertFalse((temporary_data / "archive").exists())

    def test_usable_item_without_usable_core_source_is_rejected(self):
        raw = {
            "items": [
                {
                    "id": "orphaned-usable-item",
                    "source_type": "primary",
                    "verification": "primary",
                    "status": "ok",
                    "published_at": "2026-09-17",
                    "category": ["AI & PM"],
                    "title": "Orphaned usable item",
                    "source": "PMI",
                    "source_url": "https://example.invalid/orphaned",
                    "raw_excerpt": "Usable item but failed source",
                }
            ],
            "source_status": [
                {"name": "PMI", "type": "core", "status": "failed"},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            current = temporary_data / "morning-intelligence.json"
            self.builder.DATA = temporary_data

            with self.assertRaisesRegex(RuntimeError, "nicht publishable"):
                self.builder.build_edition("no-usable-core-source", raw)

            self.assertFalse(current.exists())
            self.assertFalse((temporary_data / "archive").exists())

    def test_partial_failure_remains_live_and_visible(self):
        raw = {
            "items": [
                {
                    "id": "usable-item",
                    "source_type": "primary",
                    "verification": "primary",
                    "status": "ok",
                    "published_at": "2026-09-17",
                    "category": ["EU AI Act"],
                    "title": "Usable item",
                    "source": "EU Commission",
                    "source_url": "https://example.invalid/usable",
                    "raw_excerpt": "Usable content",
                }
            ],
            "source_status": [
                {"name": "EU Commission", "type": "core", "status": "ok"},
                {"name": "EUR-Lex", "type": "core", "status": "ok"},
                {"name": "PMI", "type": "core", "status": "failed"},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            self.builder.DATA = temporary_data
            self.builder.build_edition("partial-failure", raw)

            result = json.loads(
                (temporary_data / "morning-intelligence.json").read_text(encoding="utf-8")
            )

            self.assertEqual("live", result["mode"])
            self.assertEqual(1, len(result["items"]))
            pmi = next(status for status in result["source_status"] if status["name"] == "PMI")
            self.assertEqual("failed", pmi["status"])

    def test_one_usable_item_and_one_degraded_core_source_is_publishable(self):
        raw = {
            "items": [
                {
                    "id": "minimum-usable-item",
                    "source_type": "primary",
                    "verification": "primary",
                    "status": "ok",
                    "published_at": "2026-09-17",
                    "category": ["EU AI Act"],
                    "title": "Minimum usable item",
                    "source": "EUR-Lex",
                    "source_url": "https://example.invalid/minimum",
                    "raw_excerpt": "Minimum usable content",
                }
            ],
            "source_status": [
                {"name": "EUR-Lex", "type": "core", "status": "degraded"},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            self.builder.DATA = temporary_data
            self.builder.build_edition("minimum-live", raw)

            result = json.loads(
                (temporary_data / "morning-intelligence.json").read_text(encoding="utf-8")
            )

            self.assertEqual("live", result["mode"])
            self.assertEqual(1, len(result["items"]))

    def test_item_from_currently_failed_source_is_excluded(self):
        raw = {
            "items": [
                {
                    "id": "old-pmi-item",
                    "source": "PMI",
                    "source_type": "primary",
                    "verification": "primary",
                    "status": "ok",
                    "published_at": "2026-09-17",
                    "category": ["AI & PM"],
                    "title": "Old PMI item",
                    "source_url": "https://example.invalid/pmi",
                    "raw_excerpt": "Previously collected PMI content",
                },
                {
                    "id": "current-eu-item",
                    "source": "EU Commission",
                    "source_type": "primary",
                    "verification": "primary",
                    "status": "ok",
                    "published_at": "2026-09-16",
                    "category": ["EU AI Act"],
                    "title": "Current EU item",
                    "source_url": "https://example.invalid/eu",
                    "raw_excerpt": "Current EU content",
                },
            ],
            "source_status": [
                {"name": "PMI", "type": "core", "status": "failed"},
                {"name": "EU Commission", "type": "core", "status": "ok"},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            self.builder.DATA = temporary_data
            self.builder.build_edition("failed-source-filter", raw)

            result = json.loads(
                (temporary_data / "morning-intelligence.json").read_text(encoding="utf-8")
            )

            self.assertEqual(["current-eu-item"], [item["id"] for item in result["items"]])

    def test_item_from_ok_source_remains_eligible(self):
        raw = {
            "items": [
                {
                    "id": "ok-source-item",
                    "source": "EU Commission",
                    "source_type": "primary",
                    "verification": "primary",
                    "status": "ok",
                    "published_at": "2026-09-17",
                    "category": ["EU AI Act"],
                    "title": "OK source item",
                    "source_url": "https://example.invalid/ok",
                    "raw_excerpt": "Content from an OK source",
                }
            ],
            "source_status": [
                {"name": "EU Commission", "type": "core", "status": "ok"},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            self.builder.DATA = temporary_data
            self.builder.build_edition("ok-source-filter", raw)

            result = json.loads(
                (temporary_data / "morning-intelligence.json").read_text(encoding="utf-8")
            )

            self.assertEqual(["ok-source-item"], [item["id"] for item in result["items"]])

    def test_item_from_degraded_source_remains_eligible(self):
        raw = {
            "items": [
                {
                    "id": "degraded-source-item",
                    "source": "EUR-Lex",
                    "source_type": "primary",
                    "verification": "primary",
                    "status": "ok",
                    "published_at": "2026-09-17",
                    "category": ["EU AI Act"],
                    "title": "Degraded source item",
                    "source_url": "https://example.invalid/degraded",
                    "raw_excerpt": "Content from a degraded source",
                }
            ],
            "source_status": [
                {"name": "EUR-Lex", "type": "core", "status": "degraded"},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            self.builder.DATA = temporary_data
            self.builder.build_edition("degraded-source-filter", raw)

            result = json.loads(
                (temporary_data / "morning-intelligence.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                ["degraded-source-item"],
                [item["id"] for item in result["items"]],
            )

    def test_builder_writes_current_and_archive_json_in_temporary_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            self.builder.DATA = temporary_data
            self.builder.build_edition("offline-test", self.raw)

            current = temporary_data / "morning-intelligence.json"
            self.assertTrue(current.is_file())
            result = json.loads(current.read_text(encoding="utf-8"))

            self.assertEqual("1.0", result.get("schema_version"))
            self.assertEqual("offline-test", result.get("edition"))
            self.assertEqual("live", result.get("mode"))
            self.assertLessEqual(len(result.get("items", [])), 5)
            self.assertEqual(self.raw["source_status"], result.get("source_status"))

            day = self.builder.now_local().strftime("%Y-%m-%d")
            archived = temporary_data / "archive" / day / "offline-test.json"
            self.assertTrue(archived.is_file())

    def test_manual_preview_never_changes_existing_live_json(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            current = temporary_data / "morning-intelligence.json"
            existing_live = b'{"protected":"live"}\n'
            current.write_bytes(existing_live)
            self.builder.DATA = temporary_data
            manual_time = datetime(2026, 9, 17, 7, 0, tzinfo=self.builder.TZ)

            with mock.patch.object(self.builder, "now_local", return_value=manual_time):
                with mock.patch.object(self.builder, "read_raw", return_value=self.raw):
                    with mock.patch.dict(
                        os.environ,
                        {
                            "GITHUB_EVENT_NAME": "workflow_dispatch",
                            "SNEKI_RANKING_MODE": "baseline",
                        },
                    ):
                        self.builder.main()

            self.assertEqual(existing_live, current.read_bytes())

    def test_manual_preview_is_written_to_separate_preview_file(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            self.builder.DATA = temporary_data
            manual_time = datetime(2026, 9, 17, 12, 0, tzinfo=self.builder.TZ)

            with mock.patch.object(self.builder, "now_local", return_value=manual_time):
                with mock.patch.object(self.builder, "read_raw", return_value=self.raw):
                    with mock.patch.dict(
                        os.environ,
                        {
                            "GITHUB_EVENT_NAME": "workflow_dispatch",
                            "SNEKI_RANKING_MODE": "baseline",
                        },
                    ):
                        self.builder.main()

            preview = temporary_data / "manual-preview.json"
            self.assertTrue(preview.is_file())
            self.assertEqual(
                "manual-preview",
                json.loads(preview.read_text(encoding="utf-8"))["edition"],
            )

    def test_scheduled_edition_still_updates_live_json(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_data = Path(directory)
            current = temporary_data / "morning-intelligence.json"
            current.write_text('{"old":"live"}\n', encoding="utf-8")
            self.builder.DATA = temporary_data
            scheduled_time = datetime(2026, 9, 17, 7, 0, tzinfo=self.builder.TZ)

            with mock.patch.object(self.builder, "now_local", return_value=scheduled_time):
                with mock.patch.object(self.builder, "read_raw", return_value=self.raw):
                    with mock.patch.dict(
                        os.environ,
                        {
                            "GITHUB_EVENT_NAME": "schedule",
                            "SNEKI_RANKING_MODE": "baseline",
                        },
                    ):
                        self.builder.main()

            result = json.loads(current.read_text(encoding="utf-8"))
            self.assertEqual("morning", result["edition"])


class BaselineRankingTests(unittest.TestCase):
    REFERENCE_AT = "2026-09-15T12:00:00+02:00"

    def setUp(self):
        self.builder = load_builder()
        self.raw, self.sources = load_ranking_benchmark()

    def make_item(
        self,
        item_id,
        *,
        source_id="source-a",
        source="Source A",
        published_at="2026-08-01T12:00:00+02:00",
        first_seen_at="2026-08-01T12:00:00+02:00",
        title="Neutral item",
        excerpt="Useful description",
        source_url="https://example.invalid/source-a/detail",
        category=None,
    ):
        return {
            "id": item_id,
            "source_id": source_id,
            "source": source,
            "source_type": "primary",
            "source_url": source_url,
            "category": category if category is not None else ["EU AI Act"],
            "title": title,
            "raw_excerpt": excerpt,
            "published_at": published_at,
            "first_seen_at": first_seen_at,
            "verification": "primary",
            "status": "ok",
        }

    def source_config(self, *source_ids):
        return [
            {
                "id": source_id,
                "url": f"https://example.invalid/{source_id}",
            }
            for source_id in source_ids
        ]

    def source_status(self, *sources):
        return [
            {"name": source, "type": "core", "status": "ok"}
            for source in sources
        ]

    def rank(self, items, source_ids=("source-a",), sources=("Source A",), limit=5):
        return self.builder.rank_candidates_baseline(
            items,
            self.source_status(*sources),
            self.source_config(*source_ids),
            self.REFERENCE_AT,
            limit,
        )

    def test_baseline_exact_score_calculation(self):
        item = self.make_item(
            "exact-score",
            title="Regulation with investment obligations",
        )

        result = self.rank([item])[0]

        self.assertEqual(2, result["recency_score"])
        self.assertEqual(3, result["quality_score"])
        self.assertEqual(2, result["management_score"])
        self.assertEqual(7, result["base_score"])
        self.assertEqual(0, result["source_penalty"])
        self.assertEqual(0.5, result["category_bonus"])
        self.assertEqual(7.5, result["final_score"])

    def test_baseline_recency_score_boundaries_and_first_seen_fallback(self):
        reference = datetime.fromisoformat(self.REFERENCE_AT)
        expected = {
            0: 4,
            7: 4,
            8: 3,
            30: 3,
            31: 2,
            90: 2,
            91: 1,
            180: 1,
            181: 0,
        }
        items = [
            self.make_item(
                f"age-{days}",
                published_at=(reference - timedelta(days=days)).isoformat(),
            )
            for days in expected
        ]
        items.append(
            self.make_item(
                "fallback-first-seen",
                published_at=None,
                first_seen_at=(reference - timedelta(days=7)).isoformat(),
            )
        )

        results = self.rank(items, limit=len(items))
        by_id = {result["item"]["id"]: result for result in results}

        for days, score in expected.items():
            self.assertEqual(score, by_id[f"age-{days}"]["recency_score"])
        self.assertEqual(4, by_id["fallback-first-seen"]["recency_score"])
        self.assertEqual(2, by_id["fallback-first-seen"]["quality_score"])

    def test_baseline_management_signal_is_capped_at_two_points(self):
        many_signals = self.make_item(
            "many-signals",
            title="Regulation enforcement obligations enter into force",
            excerpt="Guidelines for cybersecurity investment",
        )
        no_signal = self.make_item("no-signal")

        results = self.rank([many_signals, no_signal], limit=2)
        by_id = {result["item"]["id"]: result for result in results}

        self.assertEqual(2, by_id["many-signals"]["management_score"])
        self.assertEqual(0, by_id["no-signal"]["management_score"])

    def test_baseline_source_penalty_increases_per_selected_item(self):
        items = [self.make_item(item_id, category=[]) for item_id in ("a", "b", "c")]

        results = self.rank(items, limit=3)

        self.assertEqual(["a", "b", "c"], [result["item"]["id"] for result in results])
        self.assertEqual([0, 1, 2], [result["source_penalty"] for result in results])

    def test_baseline_category_bonus_rewards_new_existing_category(self):
        items = [
            self.make_item("a", category=["EU AI Act"]),
            self.make_item("b", category=["DSGVO & Ethik"]),
        ]

        results = self.rank(items, limit=2)

        self.assertEqual([0.5, 0.5], [result["category_bonus"] for result in results])

    def test_baseline_tie_breaker_uses_score_then_date_then_id(self):
        reference = datetime.fromisoformat(self.REFERENCE_AT)
        items = [
            self.make_item(
                "lower-score-newer",
                source_id="source-a",
                source="Source A",
                published_at=(reference - timedelta(days=1)).isoformat(),
                excerpt="",
                source_url="https://example.invalid/source-a",
                category=[],
            ),
            self.make_item(
                "higher-score-older",
                source_id="source-b",
                source="Source B",
                published_at=(reference - timedelta(days=31)).isoformat(),
                title="Regulation obligations",
                category=[],
            ),
        ]
        results = self.rank(
            items,
            source_ids=("source-a", "source-b"),
            sources=("Source A", "Source B"),
            limit=2,
        )
        self.assertEqual("higher-score-older", results[0]["item"]["id"])

        same_score = [
            self.make_item("older", published_at="2026-08-01T12:00:00+02:00", category=[]),
            self.make_item("newer", published_at="2026-08-02T12:00:00+02:00", category=[]),
        ]
        results = self.rank(same_score, limit=2)
        self.assertEqual("newer", results[0]["item"]["id"])

        same_date = [
            self.make_item("b-id", category=[]),
            self.make_item("a-id", category=[]),
        ]
        results = self.rank(same_date, limit=2)
        self.assertEqual("a-id", results[0]["item"]["id"])

    def test_baseline_fixture_top_five_is_reproducible(self):
        results = self.builder.rank_candidates_baseline(
            self.raw["items"],
            self.raw["source_status"],
            self.sources,
            self.raw["collected_at"],
            5,
        )

        self.assertEqual(
            [
                "675ab8b9c70584920356",
                "01c5434847cfafae5a0c",
                "076d3df9976c6ede52e9",
                "299bc3455f13fc48bf13",
                "c559fbd12af243b637ab",
            ],
            [result["item"]["id"] for result in results],
        )

    def test_production_selection_does_not_use_baseline(self):
        self.builder.rank_candidates_baseline = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Baseline darf nicht produktiv aufgerufen werden")
        )
        items = [self.make_item("production-item")]

        selected = self.builder.choose_candidates(
            items,
            self.source_status("Source A"),
            5,
        )

        self.assertEqual(["production-item"], [item["id"] for item in selected])


class HybridRankingIntegrationTests(unittest.TestCase):
    EXPECTED_TOP_FIVE = [
        "675ab8b9c70584920356",
        "01c5434847cfafae5a0c",
        "7fc7e1c4d2073d835bbc",
        "c559fbd12af243b637ab",
        "b4038eb822b1702a8e84",
    ]

    def setUp(self):
        self.builder = load_builder()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.cache_path = Path(self.temporary_directory.name) / "semantic-cache.json"
        self.raw, self.sources = load_ranking_benchmark()
        self.luna_result = json.loads(
            (ROOT / "tests" / "results" / "hybrid_c_luna.json").read_text(
                encoding="utf-8"
            )
        )
        self.v2_predictions = [
            {
                **prediction,
                "why_relevant": (
                    "Für Unternehmen relevant, weil die Meldung eine konkrete "
                    "Entwicklung mit möglicher Managementbedeutung beschreibt."
                ),
                "watch_next": "Weitere Konkretisierungen in der Originalquelle beobachten.",
            }
            for prediction in self.luna_result["predictions"]
        ]

    def select(self, *, mode, provider):
        return self.builder.select_candidates_for_mode(
            self.raw["items"],
            self.raw["source_status"],
            self.sources,
            self.raw["collected_at"],
            mode=mode,
            hybrid_provider=provider,
            cache_path=self.cache_path,
            limit=5,
        )

    def test_ranking_mode_defaults_to_baseline(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual("baseline", self.builder.get_ranking_mode())

    def test_baseline_mode_never_calls_hybrid_provider(self):
        provider = mock.Mock(side_effect=AssertionError("API darf nicht aufgerufen werden"))

        selected, metadata = self.select(mode="baseline", provider=provider)

        provider.assert_not_called()
        self.assertEqual("baseline", metadata["effective_mode"])
        self.assertEqual(5, len(selected))

    def test_hybrid_uses_stored_semantic_results(self):
        ranked = self.builder.rank_candidates_hybrid(
            self.raw["items"],
            self.raw["source_status"],
            self.sources,
            self.raw["collected_at"],
            self.luna_result["predictions"],
            limit=9,
        )
        by_id = {result["item"]["id"]: result for result in ranked}

        self.assertEqual(1.78, by_id["c559fbd12af243b637ab"]["semantic_component"])
        self.assertEqual(1.33, by_id["076d3df9976c6ede52e9"]["semantic_component"])

    def test_insufficient_input_is_not_ranked(self):
        ranked = self.builder.rank_candidates_hybrid(
            self.raw["items"],
            self.raw["source_status"],
            self.sources,
            self.raw["collected_at"],
            self.luna_result["predictions"],
            limit=20,
        )
        ranked_ids = {result["item"]["id"] for result in ranked}

        self.assertNotIn("299bc3455f13fc48bf13", ranked_ids)
        self.assertNotIn("fd26c6620cbb3b8fa54e", ranked_ids)

    def test_hybrid_error_uses_visible_baseline_fallback(self):
        provider = mock.Mock(side_effect=RuntimeError("offline provider failure"))
        output = io.StringIO()

        with redirect_stdout(output):
            selected, metadata = self.select(mode="hybrid", provider=provider)

        self.assertEqual("baseline_fallback", metadata["effective_mode"])
        self.assertIn("hybrid → baseline_fallback", output.getvalue())
        self.assertEqual(
            [
                "675ab8b9c70584920356",
                "01c5434847cfafae5a0c",
                "076d3df9976c6ede52e9",
                "c559fbd12af243b637ab",
                "7fc7e1c4d2073d835bbc",
            ],
            [item["id"] for item in selected],
        )

    def test_unknown_item_id_uses_baseline_fallback(self):
        predictions = [dict(item) for item in self.v2_predictions]
        predictions[0]["item_id"] = "unknown-item"
        provider = mock.Mock(return_value={"predictions": predictions, "usage": {}})

        selected, metadata = self.select(mode="hybrid", provider=provider)

        self.assertEqual("baseline_fallback", metadata["effective_mode"])
        self.assertEqual("c559fbd12af243b637ab", selected[3]["id"])

    def test_api_key_is_never_written_to_fallback_log(self):
        secret = "sk-offline-never-log-this-secret"
        provider = mock.Mock(side_effect=RuntimeError(f"request failed with {secret}"))
        output = io.StringIO()

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": secret}):
            with redirect_stdout(output):
                _, metadata = self.select(mode="hybrid", provider=provider)

        self.assertEqual("baseline_fallback", metadata["effective_mode"])
        self.assertNotIn(secret, output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())

    def test_saved_luna_result_reproduces_documented_hybrid_top_five(self):
        ranked = self.builder.rank_candidates_hybrid(
            self.raw["items"],
            self.raw["source_status"],
            self.sources,
            self.raw["collected_at"],
            self.luna_result["predictions"],
            limit=5,
        )

        self.assertEqual(
            self.EXPECTED_TOP_FIVE,
            [result["item"]["id"] for result in ranked],
        )


class SemanticCacheTests(unittest.TestCase):
    def setUp(self):
        self.builder = load_builder()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.cache_path = Path(self.temporary_directory.name) / "semantic-cache.json"
        self.raw, self.sources = load_ranking_benchmark()
        self.luna_result = json.loads(
            (ROOT / "tests" / "results" / "hybrid_c_luna.json").read_text(
                encoding="utf-8"
            )
        )
        self.prediction_by_id = {
            item["item_id"]: {
                **item,
                "why_relevant": (
                    "Für Unternehmen relevant, weil die Meldung eine konkrete "
                    "Entwicklung mit möglicher Managementbedeutung beschreibt."
                ),
                "watch_next": "Weitere Konkretisierungen in der Originalquelle beobachten.",
            }
            for item in self.luna_result["predictions"]
        }
        usable_sources = {
            source["name"]
            for source in self.raw["source_status"]
            if source["status"] in {"ok", "degraded"}
        }
        self.eligible = [
            item
            for item in self.raw["items"]
            if item["source_type"] != "social"
            and item["status"] == "ok"
            and item["source"] in usable_sources
        ]
        self.model_inputs = self.builder._hybrid_model_inputs(self.eligible)

    def cache_with_first_items(self, count):
        entries = {}
        for model_input in self.model_inputs[:count]:
            prediction = self.prediction_by_id[model_input["item_id"]]
            entry = self.builder.build_semantic_cache_entry(
                model_input,
                prediction,
                assessed_at="2026-09-17T12:00:00+00:00",
            )
            entries[entry["semantic_input_hash"]] = entry
        cache = {
            "cache_schema_version": "1.0",
            "entries": entries,
        }
        self.builder.write_semantic_cache(self.cache_path, cache)
        return cache

    def provider_for(self, captured_inputs):
        def provider(model_inputs):
            captured_inputs.extend(model_inputs)
            return {
                "model_id": "gpt-5.6-luna",
                "reasoning_effort": "low",
                "predictions": [
                    self.prediction_by_id[item["item_id"]]
                    for item in model_inputs
                ],
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "total_tokens": 30,
                    "estimated_cost_usd": 0.0001,
                },
            }
        return provider

    def select(self, provider):
        return self.builder.select_candidates_for_mode(
            self.raw["items"],
            self.raw["source_status"],
            self.sources,
            self.raw["collected_at"],
            mode="hybrid",
            hybrid_provider=provider,
            cache_path=self.cache_path,
            limit=5,
        )

    def test_same_semantic_input_produces_cache_hit_key(self):
        model_input = dict(self.model_inputs[0])
        self.assertEqual(
            self.builder.semantic_input_hash(model_input),
            self.builder.semantic_input_hash(dict(model_input)),
        )

    def test_changed_title_produces_cache_miss_key(self):
        original = self.model_inputs[0]
        changed = {**original, "title": original["title"] + " geändert"}
        self.assertNotEqual(
            self.builder.semantic_input_hash(original),
            self.builder.semantic_input_hash(changed),
        )

    def test_changed_excerpt_produces_cache_miss_key(self):
        original = self.model_inputs[0]
        changed = {**original, "raw_excerpt": original["raw_excerpt"] + " geändert"}
        self.assertNotEqual(
            self.builder.semantic_input_hash(original),
            self.builder.semantic_input_hash(changed),
        )

    def test_changed_category_produces_cache_miss_key(self):
        original = self.model_inputs[0]
        changed = {**original, "category": ["Andere Kategorie"]}
        self.assertNotEqual(
            self.builder.semantic_input_hash(original),
            self.builder.semantic_input_hash(changed),
        )

    def test_changed_prompt_version_produces_cache_miss_key(self):
        model_input = self.model_inputs[0]
        self.assertNotEqual(
            self.builder.semantic_input_hash(model_input, prompt_version="v1"),
            self.builder.semantic_input_hash(model_input, prompt_version="v2"),
        )

    def test_changed_model_produces_cache_miss_key(self):
        model_input = self.model_inputs[0]
        self.assertNotEqual(
            self.builder.semantic_input_hash(model_input, model_id="gpt-5.6-luna"),
            self.builder.semantic_input_hash(model_input, model_id="other-model"),
        )

    def test_changed_reasoning_effort_produces_cache_miss_key(self):
        model_input = self.model_inputs[0]
        self.assertNotEqual(
            self.builder.semantic_input_hash(model_input, reasoning_effort="low"),
            self.builder.semantic_input_hash(model_input, reasoning_effort="medium"),
        )

    def test_changed_schema_version_produces_cache_miss_key(self):
        model_input = self.model_inputs[0]
        self.assertNotEqual(
            self.builder.semantic_input_hash(model_input, schema_version="v1"),
            self.builder.semantic_input_hash(model_input, schema_version="v2"),
        )

    def test_changed_item_id_keeps_same_cache_key(self):
        original = self.model_inputs[0]
        changed = {**original, "item_id": "new-trace-id"}
        self.assertEqual(
            self.builder.semantic_input_hash(original),
            self.builder.semantic_input_hash(changed),
        )

    def test_complete_cache_skips_api_call(self):
        self.cache_with_first_items(len(self.model_inputs))
        provider = mock.Mock(side_effect=AssertionError("API darf nicht laufen"))

        selected, metadata = self.select(provider)

        provider.assert_not_called()
        self.assertEqual("hybrid", metadata["effective_mode"])
        self.assertEqual(11, metadata["cache_hits"])
        self.assertEqual(0, metadata["cache_misses"])
        self.assertFalse(metadata["api_call_performed"])
        self.assertEqual(5, len(selected))

    def test_partial_cache_sends_only_misses_in_one_batch(self):
        self.cache_with_first_items(5)
        captured_inputs = []
        provider = mock.Mock(side_effect=self.provider_for(captured_inputs))

        _, metadata = self.select(provider)

        provider.assert_called_once()
        self.assertEqual(6, len(captured_inputs))
        self.assertEqual(5, metadata["cache_hits"])
        self.assertEqual(6, metadata["cache_misses"])
        self.assertEqual(6, metadata["api_items_evaluated"])
        self.assertTrue(metadata["api_call_performed"])
        cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(11, len(cache["entries"]))

    def test_api_error_for_misses_uses_baseline_fallback(self):
        provider = mock.Mock(side_effect=RuntimeError("offline api failure"))

        selected, metadata = self.select(provider)

        provider.assert_called_once()
        self.assertEqual("baseline_fallback", metadata["effective_mode"])
        self.assertEqual("c559fbd12af243b637ab", selected[3]["id"])

    def test_api_error_does_not_damage_existing_cache(self):
        self.cache_with_first_items(1)
        before = self.cache_path.read_bytes()
        provider = mock.Mock(side_effect=RuntimeError("offline api failure"))

        _, metadata = self.select(provider)

        self.assertEqual("baseline_fallback", metadata["effective_mode"])
        self.assertEqual(before, self.cache_path.read_bytes())

    def test_secret_is_absent_from_cache_and_log(self):
        self.cache_with_first_items(1)
        secret = "sk-cache-offline-secret-value"
        provider = mock.Mock(side_effect=RuntimeError(f"failed with {secret}"))
        output = io.StringIO()

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": secret}):
            with redirect_stdout(output):
                self.select(provider)

        self.assertNotIn(secret, output.getvalue())
        self.assertNotIn(secret, self.cache_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
