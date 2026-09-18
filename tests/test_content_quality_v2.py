"""Offline-Regressionstests für Content Quality und Hybrid-C-Vertrag V2."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Script konnte nicht geladen werden: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContentQualityV2Tests(unittest.TestCase):
    def setUp(self):
        self.builder = load_script("build_briefing.py")
        self.evaluator = load_script("evaluate_hybrid_c.py")

    @staticmethod
    def item(item_id, source_id, source, category, date="2026-09-17"):
        return {
            "id": item_id,
            "source_id": source_id,
            "source": source,
            "source_type": "primary",
            "source_url": f"https://example.invalid/{source_id}/{item_id}",
            "category": [category],
            "title": f"Konkrete Entwicklung {item_id}",
            "raw_excerpt": "Die Quelle beschreibt eine konkrete Entwicklung für Projekte.",
            "published_at": date,
            "first_seen_at": f"{date}T08:00:00+02:00",
            "verification": "primary",
            "status": "ok",
        }

    @staticmethod
    def prediction(item_id, scores=(3, 3, 3)):
        return {
            "item_id": item_id,
            "assessment_status": "scored",
            "management_relevance": scores[0],
            "actionability": scores[1],
            "significance": scores[2],
            "reason": "Die Quelldaten beschreiben eine konkrete Entwicklung.",
            "summary": "Konkrete Entwicklung aus der Originalquelle.",
            "why_relevant": (
                "Für Unternehmen relevant, weil die beschriebene Entwicklung "
                "Entscheidungen in laufenden Projekten nachvollziehbar beeinflussen kann."
            ),
            "watch_next": (
                "Weitere Konkretisierungen und Praxisbeispiele in der Originalquelle beobachten."
            ),
        }

    @staticmethod
    def statuses(*sources):
        return [
            {"name": source, "type": "core", "status": "ok"}
            for source in sources
        ]

    @staticmethod
    def configs(*source_ids):
        return [
            {"id": source_id, "url": f"https://example.invalid/{source_id}"}
            for source_id in source_ids
        ]

    def rank(self, items, predictions, limit=None):
        return self.builder.rank_candidates_hybrid_v2(
            items,
            self.statuses(*(dict.fromkeys(item["source"] for item in items))),
            self.configs(*(dict.fromkeys(item["source_id"] for item in items))),
            "2026-09-18T08:00:00+02:00",
            predictions,
            limit=limit or len(items),
        )

    def test_similarly_relevant_candidates_use_diversity_tiebreaker(self):
        items = [
            self.item("anchor", "a", "Source A", "Governance"),
            self.item("repeat", "a", "Source A", "Governance"),
            self.item("diverse", "b", "Source B", "AI & PM"),
        ]
        predictions = [
            self.prediction("anchor", (3, 3, 3)),
            self.prediction("repeat", (3, 3, 2)),
            self.prediction("diverse", (3, 3, 2)),
        ]

        ranked = self.rank(items, predictions)

        self.assertEqual(["anchor", "diverse", "repeat"], [x["item"]["id"] for x in ranked])

    def test_clear_relevance_advantage_is_never_displaced_by_diversity(self):
        items = [
            self.item("strong", "a", "Source A", "Governance"),
            self.item("diverse-weaker", "b", "Source B", "AI & PM"),
        ]
        predictions = [
            self.prediction("strong", (3, 3, 3)),
            self.prediction("diverse-weaker", (2, 2, 2)),
        ]

        ranked = self.rank(items, predictions)

        self.assertEqual("strong", ranked[0]["item"]["id"])

    def test_source_diversity_breaks_an_otherwise_equal_tie(self):
        items = [
            self.item("anchor", "a", "Source A", "Governance"),
            self.item("same-source", "a", "Source A", "AI & PM"),
            self.item("new-source", "b", "Source B", "AI & PM"),
        ]
        predictions = [self.prediction(item["id"]) for item in items]

        ranked = self.rank(items, predictions)

        self.assertEqual("new-source", ranked[1]["item"]["id"])

    def test_category_diversity_precedes_source_diversity(self):
        items = [
            self.item("anchor", "a", "Source A", "Governance"),
            self.item("new-category", "a", "Source A", "AI & PM"),
            self.item("new-source-repeat-category", "b", "Source B", "Governance"),
        ]
        predictions = [self.prediction(item["id"]) for item in items]

        ranked = self.rank(items, predictions)

        self.assertEqual("new-category", ranked[1]["item"]["id"])

    def test_v2_cache_key_differs_from_v1(self):
        model_input = {
            "item_id": "one",
            "title": "Title",
            "raw_excerpt": "Excerpt",
            "source": "Source",
            "category": ["AI & PM"],
        }

        self.assertEqual("v2", self.builder.HYBRID_PROMPT_VERSION)
        self.assertNotEqual(
            self.builder.semantic_input_hash(model_input),
            self.builder.semantic_input_hash(
                model_input,
                prompt_version="v1",
                schema_version="v1",
            ),
        )

    def test_structured_output_v2_is_complete(self):
        schema = self.evaluator.build_output_schema(["one"])
        item_schema = schema["properties"]["items"]["items"]

        self.assertEqual("v2", self.evaluator.HYBRID_PROMPT_VERSION)
        self.assertEqual(9, len(item_schema["required"]))
        self.assertIn("why_relevant", item_schema["required"])
        self.assertIn("watch_next", item_schema["required"])
        self.assertEqual(
            "hybrid_c_luna_v2.json",
            self.evaluator.DEFAULT_RESULT_PATH.name,
        )

    def test_missing_why_relevant_is_rejected(self):
        prediction = self.prediction("one")
        prediction.pop("why_relevant")

        with self.assertRaises(ValueError):
            self.evaluator.validate_predictions([prediction], ["one"])

    def test_missing_watch_next_is_rejected(self):
        prediction = self.prediction("one")
        prediction.pop("watch_next")

        with self.assertRaises(ValueError):
            self.evaluator.validate_predictions([prediction], ["one"])

    def test_old_generic_placeholders_are_rejected(self):
        prediction = self.prediction("one")
        prediction["why_relevant"] = (
            "Für sneKI prüfen: Relevanz für Regulierung, Governance, Datenschutz "
            "oder AI-Projektmanagement."
        )
        prediction["watch_next"] = "Primärquelle auf konkrete Änderungen prüfen."

        with self.assertRaisesRegex(ValueError, "Platzhalter"):
            self.evaluator.validate_predictions([prediction], ["one"])

    def test_deterministic_fallback_contains_safe_specific_texts(self):
        item = self.item("fallback", "gpm", "GPM", "AI & PM")

        story = self.builder.make_story(item, 1)

        self.assertNotIn("Für sneKI prüfen", story["why_relevant"])
        self.assertNotEqual(
            "Primärquelle auf konkrete Änderungen prüfen.",
            story["watch_next"],
        )
        self.assertIn("Projektverantwortliche", story["why_relevant"])

    def test_hybrid_editorial_texts_are_used_in_story(self):
        item = self.item("hybrid", "apm", "APM", "AI & PM")
        prediction = self.prediction("hybrid")
        item["_hybrid_content"] = {
            "why_relevant": prediction["why_relevant"],
            "watch_next": prediction["watch_next"],
        }

        story = self.builder.make_story(item, 1)

        self.assertEqual(prediction["why_relevant"], story["why_relevant"])
        self.assertEqual(prediction["watch_next"], story["watch_next"])


if __name__ == "__main__":
    unittest.main()
