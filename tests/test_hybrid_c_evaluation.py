"""Reine Offline-Tests für die isolierte Hybrid-C-Evaluation."""

from __future__ import annotations

from contextlib import redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
from unittest import mock
import unittest
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]


def load_evaluator():
    path = ROOT / "scripts" / "evaluate_hybrid_c.py"
    spec = importlib.util.spec_from_file_location("evaluate_hybrid_c", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Evaluator konnte nicht geladen werden: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HybridCEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = load_evaluator()
        self.reference = self.evaluator.load_reference()

    def test_model_input_contains_only_the_five_allowed_fields(self):
        model_inputs = self.evaluator.build_model_inputs(self.reference)

        self.assertEqual(11, len(model_inputs))
        for item in model_inputs:
            self.assertEqual(set(self.evaluator.MODEL_INPUT_FIELDS), set(item))

    def test_request_payload_does_not_contain_ground_truth(self):
        model_inputs = self.evaluator.build_model_inputs(self.reference)
        payload = self.evaluator.build_request_payload(model_inputs)
        serialized_input = payload["input"][0]["content"][0]["text"]

        self.assertNotIn("expected_", serialized_input)
        self.assertNotIn("reference_note", serialized_input)
        self.assertEqual("gpt-5.6-luna", payload["model"])
        self.assertEqual("low", payload["reasoning"]["effort"])
        self.assertFalse(payload["store"])

    def test_structured_output_schema_is_strict_and_complete(self):
        model_inputs = self.evaluator.build_model_inputs(self.reference)
        payload = self.evaluator.build_request_payload(model_inputs)
        output_format = payload["text"]["format"]
        item_schema = output_format["schema"]["properties"]["items"]["items"]

        self.assertEqual("json_schema", output_format["type"])
        self.assertTrue(output_format["strict"])
        self.assertFalse(item_schema["additionalProperties"])
        self.assertEqual(7, len(item_schema["required"]))

    def test_test_a_is_zero_for_predictions_equal_to_ground_truth(self):
        predictions = [
            {
                "item_id": item["item_id"],
                "assessment_status": item["expected_assessment_status"],
                "management_relevance": item["expected_management_relevance"],
                "actionability": item["expected_actionability"],
                "significance": item["expected_significance"],
                "reason": "Offline-Testbegründung",
                "summary": "Offline-Testzusammenfassung",
            }
            for item in self.reference
        ]

        result = self.evaluator.evaluate_test_a(predictions, self.reference)

        self.assertEqual(
            {
                "management_relevance": 0.0,
                "actionability": 0.0,
                "significance": 0.0,
            },
            result["dimension_mae"],
        )
        self.assertEqual(0.0, result["mean_total_absolute_error"])
        self.assertEqual(11, result["status_correct"])
        self.assertEqual(2, result["insufficient_input_correct"])
        self.assertEqual(0, result["false_insufficient_input"])

    def test_insufficient_input_with_nonzero_score_is_rejected(self):
        predictions = [
            {
                "item_id": item["item_id"],
                "assessment_status": item["expected_assessment_status"],
                "management_relevance": item["expected_management_relevance"],
                "actionability": item["expected_actionability"],
                "significance": item["expected_significance"],
                "reason": "Offline-Testbegründung",
                "summary": "Offline-Testzusammenfassung",
            }
            for item in self.reference
        ]
        insufficient = next(
            item
            for item in predictions
            if item["assessment_status"] == "insufficient_input"
        )
        insufficient["significance"] = 1

        with self.assertRaisesRegex(ValueError, "drei Nullwerte"):
            self.evaluator.evaluate_test_a(predictions, self.reference)

    def test_missing_api_key_aborts_before_any_request(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with mock.patch.object(self.evaluator, "urlopen") as request:
                with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                    self.evaluator.run_hybrid_c()

        request.assert_not_called()

    def test_cost_estimate_uses_documented_token_rates(self):
        cost = self.evaluator.estimate_cost_usd(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )

        self.assertEqual(1.40, cost)

    def run_main_with_mocked_urlopen(self, *, side_effect=None, response_body=None):
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-offline-test-secret"}):
            with mock.patch.object(self.evaluator, "urlopen") as urlopen:
                if side_effect is not None:
                    urlopen.side_effect = side_effect
                else:
                    response = mock.MagicMock()
                    response.status = 200
                    response.read.return_value = response_body
                    urlopen.return_value.__enter__.return_value = response
                with redirect_stderr(stderr):
                    exit_code = self.evaluator.main(["--execute"])
        return exit_code, stderr.getvalue()

    def make_http_error(self, status, message="Sichere API-Fehlermeldung"):
        body = json.dumps({"error": {"message": message}}).encode("utf-8")
        return HTTPError(
            self.evaluator.API_URL,
            status,
            "HTTP error",
            {},
            io.BytesIO(body),
        )

    def assert_diagnostic(self, stderr, error_class, exit_code, http_status=None):
        self.assertIn(f"Fehlerklasse: {error_class}", stderr)
        if http_status is not None:
            self.assertIn(f"HTTP-Status: {http_status}", stderr)
        self.assertIn(f"Exit-Code: {exit_code}", stderr)

    def test_http_400_is_classified_as_invalid_request(self):
        exit_code, stderr = self.run_main_with_mocked_urlopen(
            side_effect=self.make_http_error(400)
        )

        self.assertEqual(20, exit_code)
        self.assert_diagnostic(stderr, "REQUEST_INVALID", 20, 400)

    def test_http_401_is_classified_as_authentication_and_redacted(self):
        exit_code, stderr = self.run_main_with_mocked_urlopen(
            side_effect=self.make_http_error(
                401,
                "Invalid key sk-offline-test-secret; Authorization: Bearer top-secret",
            )
        )

        self.assertEqual(21, exit_code)
        self.assert_diagnostic(stderr, "AUTHENTICATION", 21, 401)
        self.assertNotIn("sk-offline-test-secret", stderr)
        self.assertNotIn("top-secret", stderr)
        self.assertIn("[REDACTED]", stderr)

    def test_http_403_is_classified_as_authorization(self):
        exit_code, stderr = self.run_main_with_mocked_urlopen(
            side_effect=self.make_http_error(403)
        )

        self.assertEqual(22, exit_code)
        self.assert_diagnostic(stderr, "AUTHORIZATION", 22, 403)

    def test_http_404_is_classified_as_endpoint_or_model(self):
        exit_code, stderr = self.run_main_with_mocked_urlopen(
            side_effect=self.make_http_error(404)
        )

        self.assertEqual(23, exit_code)
        self.assert_diagnostic(stderr, "ENDPOINT_OR_MODEL", 23, 404)

    def test_http_429_is_classified_as_rate_limit_or_quota(self):
        exit_code, stderr = self.run_main_with_mocked_urlopen(
            side_effect=self.make_http_error(429)
        )

        self.assertEqual(24, exit_code)
        self.assert_diagnostic(stderr, "RATE_LIMIT_OR_QUOTA", 24, 429)

    def test_http_500_is_classified_as_api_service(self):
        exit_code, stderr = self.run_main_with_mocked_urlopen(
            side_effect=self.make_http_error(500)
        )

        self.assertEqual(25, exit_code)
        self.assert_diagnostic(stderr, "API_SERVICE", 25, 500)

    def test_timeout_is_classified_as_transport_timeout(self):
        exit_code, stderr = self.run_main_with_mocked_urlopen(
            side_effect=socket.timeout("timed out")
        )

        self.assertEqual(30, exit_code)
        self.assert_diagnostic(stderr, "TRANSPORT_TIMEOUT", 30)

    def test_invalid_http_response_json_is_classified_as_response_parsing(self):
        exit_code, stderr = self.run_main_with_mocked_urlopen(
            response_body=b"not-json"
        )

        self.assertEqual(40, exit_code)
        self.assert_diagnostic(stderr, "RESPONSE_PARSING", 40, 200)

    def test_invalid_structured_output_is_classified_as_schema_validation(self):
        response_body = json.dumps(
            {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"items": []}),
                            }
                        ]
                    }
                ]
            }
        ).encode("utf-8")

        exit_code, stderr = self.run_main_with_mocked_urlopen(
            response_body=response_body
        )

        self.assertEqual(41, exit_code)
        self.assert_diagnostic(stderr, "SCHEMA_VALIDATION", 41, 200)


if __name__ == "__main__":
    unittest.main()
