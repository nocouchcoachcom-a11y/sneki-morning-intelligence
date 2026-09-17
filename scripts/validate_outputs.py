"""Validiert erzeugte sneKI-JSON-Dateien ohne Netzwerk oder KI-Aufruf."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCE_STATUS_VALUES = {"ok", "degraded", "failed"}
ASSESSMENT_STATUS_VALUES = {"scored", "insufficient_input"}
CACHE_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
    re.compile(r"\bbearer\s+[^\s,;]+", re.IGNORECASE),
)
SECRET_FIELD_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "access_token",
    "refresh_token",
)


class ValidationError(RuntimeError):
    """Sicher ausgebbarer Fehler eines lokalen Datenvertrags."""


def _load_json(path, *, required):
    path = Path(path)
    if not path.exists():
        if required:
            raise ValidationError(f"Pflichtdatei fehlt: {path.name}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{path.name} ist kein gültiges JSON.") from error
    if not isinstance(payload, dict):
        raise ValidationError(f"{path.name} muss ein JSON-Objekt enthalten.")
    return payload


def _require_keys(payload, required, label):
    missing = sorted(set(required) - set(payload))
    if missing:
        raise ValidationError(f"{label}: notwendige Felder fehlen: {', '.join(missing)}")


def _require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} muss ein nicht leerer Text sein.")


def _validate_source_status(source_status, label):
    if not isinstance(source_status, list):
        raise ValidationError(f"{label}.source_status muss eine Liste sein.")
    for position, source in enumerate(source_status, start=1):
        if not isinstance(source, dict):
            raise ValidationError(f"{label}.source_status[{position}] muss ein Objekt sein.")
        _require_keys(source, {"name", "type", "status"}, f"{label}.source_status[{position}]")
        _require_text(source["name"], f"{label}.source_status[{position}].name")
        _require_text(source["type"], f"{label}.source_status[{position}].type")
        if source["status"] not in SOURCE_STATUS_VALUES:
            raise ValidationError(
                f"{label}.source_status[{position}].status ist ungültig."
            )


def _validate_items(items, label, *, require_nonempty=False):
    if not isinstance(items, list):
        raise ValidationError(f"{label}.items muss eine Liste sein.")
    if require_nonempty and not items:
        raise ValidationError(f"{label}.items darf nicht leer sein.")

    item_ids = []
    for position, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"{label}.items[{position}] muss ein Objekt sein.")
        _require_keys(
            item,
            {"id", "source", "source_url"},
            f"{label}.items[{position}]",
        )
        _require_text(item["id"], f"{label}.items[{position}].id")
        _require_text(item["source"], f"{label}.items[{position}].source")
        _require_text(item["source_url"], f"{label}.items[{position}].source_url")
        item_ids.append(item["id"])

    if len(item_ids) != len(set(item_ids)):
        raise ValidationError(f"{label}.items enthält doppelte IDs.")


def validate_raw(payload):
    label = "raw-items.json"
    _require_keys(payload, {"schema_version", "collected_at", "items", "source_status"}, label)
    _require_text(payload["schema_version"], f"{label}.schema_version")
    _require_text(payload["collected_at"], f"{label}.collected_at")
    _validate_items(payload["items"], label)
    _validate_source_status(payload["source_status"], label)


def validate_briefing(payload, label="morning-intelligence.json"):
    _require_keys(
        payload,
        {
            "schema_version",
            "generated_at",
            "mode",
            "edition",
            "briefing",
            "items",
            "signals",
            "source_status",
            "ranking",
        },
        label,
    )
    for field in ("schema_version", "generated_at", "mode", "edition"):
        _require_text(payload[field], f"{label}.{field}")
    if not isinstance(payload["briefing"], list):
        raise ValidationError(f"{label}.briefing muss eine Liste sein.")
    if not isinstance(payload["signals"], dict):
        raise ValidationError(f"{label}.signals muss ein Objekt sein.")
    if not isinstance(payload["ranking"], dict):
        raise ValidationError(f"{label}.ranking muss ein Objekt sein.")
    _require_keys(
        payload["ranking"],
        {"requested_mode", "effective_mode"},
        f"{label}.ranking",
    )
    _validate_items(payload["items"], label, require_nonempty=True)
    _validate_source_status(payload["source_status"], label)


def _find_obvious_secret(value, path="cache"):
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if any(marker in normalized for marker in SECRET_FIELD_MARKERS):
                return f"verdächtiges Feld {path}.{key}"
            found = _find_obvious_secret(nested, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for position, nested in enumerate(value):
            found = _find_obvious_secret(nested, f"{path}[{position}]")
            if found:
                return found
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS):
            return f"verdächtiger Wert in {path}"
    return None


def validate_semantic_cache(payload):
    label = "semantic-cache.json"
    secret_finding = _find_obvious_secret(payload)
    if secret_finding:
        raise ValidationError(f"{label}: offensichtliches Secret erkannt ({secret_finding}).")

    _require_keys(payload, {"cache_schema_version", "entries"}, label)
    _require_text(payload["cache_schema_version"], f"{label}.cache_schema_version")
    entries = payload["entries"]
    if not isinstance(entries, dict):
        raise ValidationError(f"{label}.entries muss ein Objekt sein.")

    required_entry_fields = {
        "semantic_input_hash",
        "item_id",
        "model_id",
        "reasoning_effort",
        "prompt_version",
        "schema_version",
        "assessed_at",
        "assessment_status",
        "management_relevance",
        "actionability",
        "significance",
        "reason",
        "summary",
    }
    for cache_key, entry in entries.items():
        if not CACHE_HASH_PATTERN.fullmatch(cache_key):
            raise ValidationError(f"{label}: ungültiger Cache-Key.")
        if not isinstance(entry, dict):
            raise ValidationError(f"{label}: Cache-Eintrag muss ein Objekt sein.")
        _require_keys(entry, required_entry_fields, f"{label}.entries[{cache_key}]")
        if entry["semantic_input_hash"] != cache_key:
            raise ValidationError(f"{label}: Hash und Cache-Key stimmen nicht überein.")
        for field in (
            "item_id",
            "model_id",
            "reasoning_effort",
            "prompt_version",
            "schema_version",
            "assessed_at",
            "reason",
            "summary",
        ):
            _require_text(entry[field], f"{label}.entries[{cache_key}].{field}")

        status = entry["assessment_status"]
        if status not in ASSESSMENT_STATUS_VALUES:
            raise ValidationError(f"{label}: ungültiger assessment_status.")
        scores = [
            entry["management_relevance"],
            entry["actionability"],
            entry["significance"],
        ]
        if not all(isinstance(score, int) and 0 <= score <= 3 for score in scores):
            raise ValidationError(f"{label}: ungültiger semantischer Score.")
        if status == "insufficient_input" and scores != [0, 0, 0]:
            raise ValidationError(
                f"{label}: insufficient_input benötigt drei Nullwerte."
            )


def validate_outputs(data_dir=DATA, *, skip_briefing=False, preview=False):
    data_dir = Path(data_dir)
    raw = _load_json(data_dir / "raw-items.json", required=True)
    validate_raw(raw)
    validated = ["raw-items.json"]

    if not skip_briefing:
        briefing_name = "manual-preview.json" if preview else "morning-intelligence.json"
        briefing = _load_json(data_dir / briefing_name, required=preview)
        if briefing is not None:
            validate_briefing(briefing, briefing_name)
            validated.append(briefing_name)

    cache = _load_json(data_dir / "semantic-cache.json", required=False)
    if cache is not None:
        validate_semantic_cache(cache)
        validated.append("semantic-cache.json")

    return validated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    briefing_mode = parser.add_mutually_exclusive_group()
    briefing_mode.add_argument(
        "--skip-briefing",
        action="store_true",
        help="Überspringt nur ein nachweislich unverändertes bestehendes Briefing.",
    )
    briefing_mode.add_argument(
        "--preview",
        action="store_true",
        help="Validiert eine neu erzeugte manual-preview.json streng.",
    )
    args = parser.parse_args(argv)
    try:
        validated = validate_outputs(
            args.data_dir,
            skip_briefing=args.skip_briefing,
            preview=args.preview,
        )
    except ValidationError as error:
        print(f"Output-Validierung fehlgeschlagen: {error}")
        return 1
    print(f"Output-Validierung erfolgreich: {', '.join(validated)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
