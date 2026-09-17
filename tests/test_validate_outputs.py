"""Offline-Tests für Output-Vertrag und GitHub-Workflow-Struktur."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    path = ROOT / "scripts" / "validate_outputs.py"
    spec = importlib.util.spec_from_file_location("validate_outputs", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Validator konnte nicht geladen werden: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OutputValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.data = Path(self.temporary_directory.name)

    def write_json(self, name, payload):
        (self.data / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def valid_source_status(self):
        return [
            {
                "name": "Test Source",
                "type": "core",
                "status": "ok",
            }
        ]

    def valid_raw(self):
        return {
            "schema_version": "1.0",
            "collected_at": "2026-09-17T12:00:00+02:00",
            "items": [
                {
                    "id": "item-1",
                    "source": "Test Source",
                    "source_url": "https://example.invalid/item-1",
                }
            ],
            "source_status": self.valid_source_status(),
        }

    def valid_briefing(self):
        return {
            "schema_version": "1.0",
            "generated_at": "2026-09-17T12:01:00+02:00",
            "mode": "live",
            "edition": "test",
            "briefing": ["Test"],
            "items": [
                {
                    "id": "item-1",
                    "source": "Test Source",
                    "source_url": "https://example.invalid/item-1",
                }
            ],
            "signals": {},
            "source_status": self.valid_source_status(),
            "ranking": {
                "requested_mode": "hybrid",
                "effective_mode": "hybrid",
            },
        }

    def valid_cache(self):
        cache_hash = "a" * 64
        return {
            "cache_schema_version": "1.0",
            "entries": {
                cache_hash: {
                    "semantic_input_hash": cache_hash,
                    "item_id": "item-1",
                    "model_id": "gpt-5.6-luna",
                    "reasoning_effort": "low",
                    "prompt_version": "v1",
                    "schema_version": "v1",
                    "assessed_at": "2026-09-17T12:00:00+00:00",
                    "assessment_status": "scored",
                    "management_relevance": 2,
                    "actionability": 1,
                    "significance": 2,
                    "reason": "Offline-Testbegründung",
                    "summary": "Offline-Testzusammenfassung",
                }
            },
        }

    def test_valid_raw_file_passes(self):
        self.write_json("raw-items.json", self.valid_raw())
        self.validator.validate_outputs(self.data)

    def test_invalid_raw_file_fails(self):
        payload = self.valid_raw()
        del payload["items"][0]["source_url"]
        self.write_json("raw-items.json", payload)

        with self.assertRaisesRegex(self.validator.ValidationError, "source_url"):
            self.validator.validate_outputs(self.data)

    def test_valid_briefing_file_passes(self):
        self.write_json("raw-items.json", self.valid_raw())
        self.write_json("morning-intelligence.json", self.valid_briefing())
        self.validator.validate_outputs(self.data)

    def test_invalid_briefing_file_fails(self):
        payload = self.valid_briefing()
        del payload["items"][0]["id"]
        self.write_json("raw-items.json", self.valid_raw())
        self.write_json("morning-intelligence.json", payload)

        with self.assertRaisesRegex(self.validator.ValidationError, "id"):
            self.validator.validate_outputs(self.data)

    def test_valid_semantic_cache_passes(self):
        self.write_json("raw-items.json", self.valid_raw())
        self.write_json("semantic-cache.json", self.valid_cache())
        self.validator.validate_outputs(self.data)

    def test_damaged_semantic_cache_fails(self):
        self.write_json("raw-items.json", self.valid_raw())
        (self.data / "semantic-cache.json").write_text("{kein-json", encoding="utf-8")

        with self.assertRaisesRegex(self.validator.ValidationError, "gültiges JSON"):
            self.validator.validate_outputs(self.data)

    def test_obvious_secret_in_cache_fails(self):
        payload = self.valid_cache()
        entry = next(iter(payload["entries"].values()))
        entry["api_key"] = "sk-this-must-never-be-stored"
        self.write_json("raw-items.json", self.valid_raw())
        self.write_json("semantic-cache.json", payload)

        with self.assertRaisesRegex(self.validator.ValidationError, "Secret"):
            self.validator.validate_outputs(self.data)

    def test_missing_optional_cache_does_not_fail(self):
        self.write_json("raw-items.json", self.valid_raw())
        self.assertFalse((self.data / "semantic-cache.json").exists())
        self.validator.validate_outputs(self.data)

    def test_legacy_briefing_passes_only_when_explicitly_skipped(self):
        legacy = self.valid_briefing()
        del legacy["ranking"]
        self.write_json("raw-items.json", self.valid_raw())
        self.write_json("morning-intelligence.json", legacy)

        exit_code = self.validator.main(
            ["--data-dir", str(self.data), "--skip-briefing"]
        )

        self.assertEqual(0, exit_code)

    def test_changed_legacy_briefing_without_ranking_fails_strict_validation(self):
        legacy = self.valid_briefing()
        del legacy["ranking"]
        self.write_json("raw-items.json", self.valid_raw())
        self.write_json("morning-intelligence.json", legacy)

        with self.assertRaisesRegex(self.validator.ValidationError, "ranking"):
            self.validator.validate_outputs(self.data)

    def test_changed_briefing_with_valid_ranking_passes_strict_validation(self):
        self.write_json("raw-items.json", self.valid_raw())
        self.write_json("morning-intelligence.json", self.valid_briefing())

        validated = self.validator.validate_outputs(self.data)

        self.assertIn("morning-intelligence.json", validated)

    def test_skip_briefing_still_validates_raw_and_cache(self):
        invalid_raw = self.valid_raw()
        del invalid_raw["items"][0]["source_url"]
        self.write_json("raw-items.json", invalid_raw)

        with self.assertRaisesRegex(self.validator.ValidationError, "source_url"):
            self.validator.validate_outputs(self.data, skip_briefing=True)

        self.write_json("raw-items.json", self.valid_raw())
        (self.data / "semantic-cache.json").write_text(
            "{kein-json",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(self.validator.ValidationError, "gültiges JSON"):
            self.validator.validate_outputs(self.data, skip_briefing=True)


class WorkflowStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (
            ROOT / ".github" / "workflows" / "morning-intelligence.yml"
        ).read_text(encoding="utf-8")

    def test_concurrency_serializes_main_runs(self):
        self.assertIn("group: sneki-morning-intelligence-main", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_checkout_is_fixed_to_main(self):
        checkout = self.workflow.index("uses: actions/checkout@v4")
        setup_python = self.workflow.index("uses: actions/setup-python@v5")
        checkout_block = self.workflow[checkout:setup_python]
        self.assertIn("fetch-depth: 0", checkout_block)
        self.assertIn("ref: main", checkout_block)

    def test_hybrid_secret_is_scoped_only_to_builder_step(self):
        self.assertEqual(1, self.workflow.count("OPENAI_API_KEY:"))
        builder = self.workflow.index("name: Edition prüfen und erzeugen")
        validator = self.workflow.index("name: Generierte Daten validieren")
        builder_block = self.workflow[builder:validator]
        self.assertIn("SNEKI_RANKING_MODE: hybrid", builder_block)
        self.assertIn("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}", builder_block)

    def test_validator_runs_after_builder_and_before_commit(self):
        builder = self.workflow.index("name: Edition prüfen und erzeugen")
        validator = self.workflow.index("name: Generierte Daten validieren")
        commit = self.workflow.index("name: Änderungen speichern")
        self.assertLess(builder, validator)
        self.assertLess(validator, commit)
        self.assertIn("python scripts/validate_outputs.py", self.workflow)

    def test_full_tests_run_after_builder_and_before_commit(self):
        builder = self.workflow.index("name: Edition prüfen und erzeugen")
        post_tests = self.workflow.index("name: Offline-Tests nach Build ausführen")
        commit = self.workflow.index("name: Änderungen speichern")
        self.assertLess(builder, post_tests)
        self.assertLess(post_tests, commit)
        self.assertIn("python -m unittest discover -s tests -v", self.workflow[post_tests:commit])

    def test_existing_hourly_schedule_is_unchanged(self):
        self.assertIn('cron: "7 * * * *"', self.workflow)

    def test_workflow_skips_briefing_only_when_git_reports_it_unchanged(self):
        validator = self.workflow.index("name: Generierte Daten validieren")
        post_tests = self.workflow.index("name: Offline-Tests nach Build ausführen")
        validation_block = self.workflow[validator:post_tests]

        self.assertIn(
            "git diff --quiet -- data/morning-intelligence.json",
            validation_block,
        )
        self.assertIn("python scripts/validate_outputs.py --skip-briefing", validation_block)

    def test_workflow_strictly_validates_changed_briefing(self):
        validator = self.workflow.index("name: Generierte Daten validieren")
        post_tests = self.workflow.index("name: Offline-Tests nach Build ausführen")
        validation_block = self.workflow[validator:post_tests]
        condition = validation_block.index(
            "git diff --quiet -- data/morning-intelligence.json"
        )
        skip_call = validation_block.index(
            "python scripts/validate_outputs.py --skip-briefing"
        )
        strict_call = validation_block.index("python scripts/validate_outputs.py", skip_call + 1)

        self.assertLess(condition, skip_call)
        self.assertLess(skip_call, strict_call)


if __name__ == "__main__":
    unittest.main()
