from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import importlib.util
import json
import os
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TZ = ZoneInfo("Europe/Berlin")

BASELINE_MANAGEMENT_TERMS = (
    "pflicht",
    "obligation",
    "durchsetzung",
    "enforcement",
    "enforcing",
    "inkrafttreten",
    "enters into force",
    "entry into force",
    "leitlinie",
    "guideline",
    "regulierung",
    "regulation",
    "cybersecurity",
    "investition",
    "investment",
)

EDITION_HOURS = {
    7: "morning",
    15: "afternoon",
}

RANKING_MODES = {"baseline", "hybrid"}
HYBRID_MODEL_ID = "gpt-5.6-luna"
HYBRID_REASONING_EFFORT = "low"
HYBRID_PROMPT_VERSION = "v2"
HYBRID_SCHEMA_VERSION = "v2"
SEMANTIC_CACHE_SCHEMA_VERSION = "1.0"
V2_SEMANTIC_SIMILARITY_BAND = 0.25
OLD_WHY_RELEVANT_PLACEHOLDER = (
    "Für sneKI prüfen: Relevanz für Regulierung, Governance, Datenschutz "
    "oder AI-Projektmanagement."
)
OLD_WATCH_NEXT_PLACEHOLDER = "Primärquelle auf konkrete Änderungen prüfen."

def now_local():
    return datetime.now(TZ)

def read_raw():
    p = DATA / "raw-items.json"
    if not p.exists():
        return {"items": [], "source_status": []}
    return json.loads(p.read_text(encoding="utf-8"))

def read_source_config():
    return json.loads((ROOT / "sources.json").read_text(encoding="utf-8")).get(
        "sources",
        [],
    )

def get_ranking_mode(environ=None):
    environment = os.environ if environ is None else environ
    configured = (environment.get("SNEKI_RANKING_MODE") or "baseline").strip().lower()
    if configured not in RANKING_MODES:
        print(
            f"Unbekannter SNEKI_RANKING_MODE={configured!r}; verwende baseline."
        )
        return "baseline"
    return configured

def parse_sort_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)

    return parsed.timestamp()

def publication_sort_timestamp(item):
    published = parse_sort_timestamp(item.get("published_at"))
    if published is not None:
        return published

    # Fallback: first_seen_at ist nur der Zeitpunkt der ersten Entdeckung,
    # nicht das Veröffentlichungsdatum. Unbekannte Werte kommen zuletzt.
    first_seen = parse_sort_timestamp(item.get("first_seen_at"))
    return first_seen if first_seen is not None else float("-inf")

def _eligible_items(items, source_status):
    usable_sources = {
        source.get("name")
        for source in source_status
        if source.get("status") in {"ok", "degraded"}
    }
    return [
        item
        for item in items
        if item.get("source_type") != "social"
        and item.get("status") == "ok"
        and item.get("source") in usable_sources
    ]

def choose_candidates(items, source_status, limit=5):
    """
    V1 bewusst deterministisch:
    - Core/Primary bevorzugen
    - neueste zuerst
    - keine Social-Quellen
    - maximal 5
    Später kann HIER ein einziger AI-Batch ergänzt werden.
    """
    filtered = _eligible_items(items, source_status)
    filtered.sort(
        key=lambda x: (
            0 if x.get("verification") == "primary" else 1,
            -publication_sort_timestamp(x)
        ),
        reverse=False
    )
    return filtered[:limit]

def _baseline_recency_score(item, reference_timestamp):
    effective_timestamp = publication_sort_timestamp(item)
    if effective_timestamp == float("-inf"):
        return 0

    age_days = (reference_timestamp - effective_timestamp) / 86400
    if age_days <= 7:
        return 4
    if age_days <= 30:
        return 3
    if age_days <= 90:
        return 2
    if age_days <= 180:
        return 1
    return 0

def _baseline_quality_score(item, source_by_id):
    score = 0
    if parse_sort_timestamp(item.get("published_at")) is not None:
        score += 1
    if (item.get("raw_excerpt") or "").strip():
        score += 1

    configured_url = source_by_id.get(item.get("source_id"), {}).get("url")
    if configured_url and item.get("source_url") != configured_url:
        score += 1
    return score

def _baseline_management_score(item):
    text = " ".join(
        [
            item.get("title") or "",
            item.get("raw_excerpt") or "",
        ]
    ).lower()
    return 2 if any(term in text for term in BASELINE_MANAGEMENT_TERMS) else 0

def _rank_candidates(
    items,
    source_status,
    source_config,
    reference_at,
    semantic_scores,
    score_field,
    limit,
):
    """Gemeinsame deterministische Bewertung und Diversitätsauswahl."""
    reference_timestamp = parse_sort_timestamp(reference_at)
    if reference_timestamp is None:
        raise ValueError("Ranking benötigt einen gültigen Referenzzeitpunkt.")

    source_by_id = {
        source.get("id"): source
        for source in source_config
        if source.get("id")
    }
    remaining = []
    for item in _eligible_items(items, source_status):
        item_id = item.get("id")
        if item_id not in semantic_scores:
            continue

        recency_score = _baseline_recency_score(item, reference_timestamp)
        quality_score = _baseline_quality_score(item, source_by_id)
        semantic_score = semantic_scores[item_id]
        remaining.append({
            "item": item,
            "recency_score": recency_score,
            "quality_score": quality_score,
            score_field: semantic_score,
            "base_score": recency_score + quality_score + semantic_score,
            "effective_timestamp": publication_sort_timestamp(item),
        })

    selected = []
    selected_per_source = {}
    represented_categories = set()

    while remaining and len(selected) < limit:
        evaluated = []
        for candidate in remaining:
            item = candidate["item"]
            source_key = item.get("source_id") or item.get("source")
            source_penalty = selected_per_source.get(source_key, 0)
            category_bonus = (
                0.5
                if any(
                    category not in represented_categories
                    for category in item.get("category", [])
                )
                else 0
            )
            evaluated.append({
                **candidate,
                "source_penalty": source_penalty,
                "category_bonus": category_bonus,
                "final_score": (
                    candidate["base_score"]
                    - source_penalty
                    + category_bonus
                ),
            })

        winner = min(
            evaluated,
            key=lambda result: (
                -result["final_score"],
                -result["effective_timestamp"],
                result["item"].get("id", ""),
            ),
        )
        selected.append(winner)
        remaining.remove(
            next(
                candidate
                for candidate in remaining
                if candidate["item"] is winner["item"]
            )
        )

        item = winner["item"]
        source_key = item.get("source_id") or item.get("source")
        selected_per_source[source_key] = selected_per_source.get(source_key, 0) + 1
        represented_categories.update(item.get("category", []))

    return selected

def rank_candidates_baseline(
    items,
    source_status,
    source_config,
    reference_at,
    limit=5,
):
    """Berechnet die B-light-Vergleichsbaseline ohne produktive Verwendung."""
    semantic_scores = {
        item["id"]: _baseline_management_score(item)
        for item in _eligible_items(items, source_status)
    }
    return _rank_candidates(
        items,
        source_status,
        source_config,
        reference_at,
        semantic_scores,
        "management_score",
        limit,
    )

def _validate_hybrid_predictions(predictions, expected_item_ids):
    if not isinstance(predictions, list):
        raise ValueError("Hybrid-Ausgabe muss eine Liste von Bewertungen enthalten.")

    expected = set(expected_item_ids)
    actual_ids = [prediction.get("item_id") for prediction in predictions]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("Hybrid-Ausgabe enthält doppelte item_id-Werte.")
    if set(actual_ids) != expected:
        raise ValueError("Hybrid-Ausgabe enthält fehlende oder unbekannte item_id-Werte.")

    required = {
        "item_id",
        "assessment_status",
        "management_relevance",
        "actionability",
        "significance",
        "reason",
        "summary",
    }
    for prediction in predictions:
        if set(prediction) != required:
            raise ValueError("Hybrid-Ausgabe verletzt das Structured-Output-Schema.")
        status = prediction["assessment_status"]
        if status not in {"scored", "insufficient_input"}:
            raise ValueError("Hybrid-Ausgabe enthält einen ungültigen Status.")
        scores = [
            prediction["management_relevance"],
            prediction["actionability"],
            prediction["significance"],
        ]
        if not all(isinstance(score, int) and 0 <= score <= 3 for score in scores):
            raise ValueError("Hybrid-Ausgabe enthält ungültige Scores.")
        if status == "insufficient_input" and scores != [0, 0, 0]:
            raise ValueError("insufficient_input benötigt drei Nullwerte.")
        if not all(
            isinstance(prediction[field], str) and prediction[field].strip()
            for field in ("reason", "summary")
        ):
            raise ValueError("Hybrid-Ausgabe enthält leere Texte.")

def rank_candidates_hybrid(
    items,
    source_status,
    source_config,
    reference_at,
    predictions,
    limit=5,
):
    """Ersetzt ausschließlich das Keyword-Signal durch validierte C-Semantik."""
    eligible = _eligible_items(items, source_status)
    expected_item_ids = [item["id"] for item in eligible]
    _validate_hybrid_predictions(predictions, expected_item_ids)

    semantic_scores = {}
    for prediction in predictions:
        if prediction["assessment_status"] == "insufficient_input":
            continue
        semantic_raw = (
            prediction["management_relevance"]
            + prediction["actionability"]
            + prediction["significance"]
        )
        semantic_scores[prediction["item_id"]] = round(semantic_raw * 2 / 9, 2)

    return _rank_candidates(
        items,
        source_status,
        source_config,
        reference_at,
        semantic_scores,
        "semantic_component",
        limit,
    )


def _rank_candidates_v2(
    items,
    source_status,
    source_config,
    reference_at,
    semantic_scores,
    limit,
):
    """Weiche Diversity nur innerhalb eines engen semantischen Qualitätsbands."""
    reference_timestamp = parse_sort_timestamp(reference_at)
    if reference_timestamp is None:
        raise ValueError("Ranking benötigt einen gültigen Referenzzeitpunkt.")

    source_by_id = {
        source.get("id"): source
        for source in source_config
        if source.get("id")
    }
    remaining = []
    for item in _eligible_items(items, source_status):
        item_id = item.get("id")
        if item_id not in semantic_scores:
            continue
        semantic_score = semantic_scores[item_id]
        recency_score = _baseline_recency_score(item, reference_timestamp)
        quality_score = _baseline_quality_score(item, source_by_id)
        remaining.append({
            "item": item,
            "semantic_component": semantic_score,
            "recency_score": recency_score,
            "quality_score": quality_score,
            "base_score": semantic_score + recency_score + quality_score,
            "effective_timestamp": publication_sort_timestamp(item),
        })

    selected = []
    selected_per_source = {}
    selected_per_category = {}

    while remaining and len(selected) < limit:
        strongest_semantic = max(
            candidate["semantic_component"]
            for candidate in remaining
        )
        similar = [
            candidate
            for candidate in remaining
            if strongest_semantic - candidate["semantic_component"]
            <= V2_SEMANTIC_SIMILARITY_BAND
        ]

        newest_recency_band = max(
            candidate["recency_score"]
            for candidate in similar
        )
        similar = [
            candidate
            for candidate in similar
            if candidate["recency_score"] == newest_recency_band
        ]

        best_quality = max(
            candidate["quality_score"]
            for candidate in similar
        )
        similar = [
            candidate
            for candidate in similar
            if candidate["quality_score"] == best_quality
        ]

        evaluated = []
        for candidate in similar:
            item = candidate["item"]
            categories = item.get("category") or []
            category_repetitions = sum(
                selected_per_category.get(category, 0)
                for category in categories
            )
            source_key = item.get("source_id") or item.get("source")
            source_repetitions = selected_per_source.get(source_key, 0)
            evaluated.append({
                **candidate,
                "category_repetitions": category_repetitions,
                "source_repetitions": source_repetitions,
                "diversity_rule": "soft_tiebreaker_v2",
            })

        winner = min(
            evaluated,
            key=lambda result: (
                result["category_repetitions"],
                result["source_repetitions"],
                -result["semantic_component"],
                -result["effective_timestamp"],
                result["item"].get("id", ""),
            ),
        )
        selected.append(winner)
        remaining.remove(
            next(
                candidate
                for candidate in remaining
                if candidate["item"] is winner["item"]
            )
        )

        item = winner["item"]
        source_key = item.get("source_id") or item.get("source")
        selected_per_source[source_key] = selected_per_source.get(source_key, 0) + 1
        for category in item.get("category") or []:
            selected_per_category[category] = selected_per_category.get(category, 0) + 1

    return selected


def _validate_hybrid_predictions_v2(predictions, expected_item_ids):
    if not isinstance(predictions, list):
        raise ValueError("Hybrid-Ausgabe muss eine Liste von Bewertungen enthalten.")

    expected = set(expected_item_ids)
    actual_ids = [prediction.get("item_id") for prediction in predictions]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected:
        raise ValueError("Hybrid-Ausgabe enthält fehlende oder doppelte item_id-Werte.")

    required = {
        "item_id",
        "assessment_status",
        "management_relevance",
        "actionability",
        "significance",
        "reason",
        "summary",
        "why_relevant",
        "watch_next",
    }
    for prediction in predictions:
        if set(prediction) != required:
            raise ValueError("Hybrid-Ausgabe verletzt das Structured-Output-Schema V2.")
        status = prediction["assessment_status"]
        scores = [
            prediction["management_relevance"],
            prediction["actionability"],
            prediction["significance"],
        ]
        if status not in {"scored", "insufficient_input"}:
            raise ValueError("Hybrid-Ausgabe enthält einen ungültigen Status.")
        if not all(isinstance(score, int) and 0 <= score <= 3 for score in scores):
            raise ValueError("Hybrid-Ausgabe enthält ungültige Scores.")
        if status == "insufficient_input" and scores != [0, 0, 0]:
            raise ValueError("insufficient_input benötigt drei Nullwerte.")
        if not all(
            isinstance(prediction[field], str) and prediction[field].strip()
            for field in ("reason", "summary", "why_relevant", "watch_next")
        ):
            raise ValueError("Hybrid-Ausgabe enthält leere Texte.")
        if (
            prediction["why_relevant"].strip() == OLD_WHY_RELEVANT_PLACEHOLDER
            or prediction["watch_next"].strip() == OLD_WATCH_NEXT_PLACEHOLDER
        ):
            raise ValueError("Hybrid-Ausgabe enthält einen alten generischen Platzhalter.")
        why_word_count = len(prediction["why_relevant"].split())
        if not 10 <= why_word_count <= 40:
            raise ValueError("why_relevant besitzt keine geeignete Satzlänge.")


def rank_candidates_hybrid_v2(
    items,
    source_status,
    source_config,
    reference_at,
    predictions,
    limit=5,
):
    """Aktives Hybrid-V2-Ranking mit redaktionellen Texten und weicher Vielfalt."""
    eligible = _eligible_items(items, source_status)
    expected_item_ids = [item["id"] for item in eligible]
    _validate_hybrid_predictions_v2(predictions, expected_item_ids)

    semantic_scores = {}
    prediction_by_id = {}
    for prediction in predictions:
        if prediction["assessment_status"] == "insufficient_input":
            continue
        semantic_raw = (
            prediction["management_relevance"]
            + prediction["actionability"]
            + prediction["significance"]
        )
        semantic_scores[prediction["item_id"]] = round(semantic_raw * 2 / 9, 2)
        prediction_by_id[prediction["item_id"]] = prediction

    ranked = _rank_candidates_v2(
        items,
        source_status,
        source_config,
        reference_at,
        semantic_scores,
        limit,
    )
    for result in ranked:
        item = dict(result["item"])
        prediction = prediction_by_id[item["id"]]
        item["_hybrid_content"] = {
            "summary": prediction["summary"].strip(),
            "why_relevant": prediction["why_relevant"].strip(),
            "watch_next": prediction["watch_next"].strip(),
        }
        result["item"] = item
    return ranked


def rank_candidates_baseline_v2(
    items,
    source_status,
    source_config,
    reference_at,
    limit=5,
):
    """Produktiver deterministischer Fallback mit der weichen V2-Auswahl."""
    semantic_scores = {
        item["id"]: _baseline_management_score(item)
        for item in _eligible_items(items, source_status)
    }
    return _rank_candidates_v2(
        items,
        source_status,
        source_config,
        reference_at,
        semantic_scores,
        limit,
    )

def _hybrid_model_inputs(items):
    return [
        {
            "item_id": item["id"],
            "title": item.get("title") or "",
            "raw_excerpt": item.get("raw_excerpt") or "",
            "source": item.get("source") or "",
            "category": item.get("category") or [],
        }
        for item in items
    ]

def semantic_input_hash(
    model_input,
    *,
    model_id=HYBRID_MODEL_ID,
    reasoning_effort=HYBRID_REASONING_EFFORT,
    prompt_version=HYBRID_PROMPT_VERSION,
    schema_version=HYBRID_SCHEMA_VERSION,
):
    """Hash über den semantischen Inhalt und den vollständigen Bewertungsvertrag."""
    canonical = {
        "title": model_input.get("title") or "",
        "raw_excerpt": model_input.get("raw_excerpt") or "",
        "source": model_input.get("source") or "",
        "category": sorted(model_input.get("category") or []),
        "model_id": model_id,
        "reasoning_effort": reasoning_effort,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()

def build_semantic_cache_entry(
    model_input,
    prediction,
    *,
    assessed_at=None,
):
    _validate_hybrid_predictions_v2([prediction], [model_input["item_id"]])
    return {
        "semantic_input_hash": semantic_input_hash(model_input),
        "item_id": model_input["item_id"],
        "model_id": HYBRID_MODEL_ID,
        "reasoning_effort": HYBRID_REASONING_EFFORT,
        "prompt_version": HYBRID_PROMPT_VERSION,
        "schema_version": HYBRID_SCHEMA_VERSION,
        "assessed_at": assessed_at or datetime.now(timezone.utc).isoformat(),
        "assessment_status": prediction["assessment_status"],
        "management_relevance": prediction["management_relevance"],
        "actionability": prediction["actionability"],
        "significance": prediction["significance"],
        "reason": prediction["reason"],
        "summary": prediction["summary"],
        "why_relevant": prediction["why_relevant"],
        "watch_next": prediction["watch_next"],
    }

def read_semantic_cache(path):
    cache_path = Path(path)
    if not cache_path.exists():
        return {
            "cache_schema_version": SEMANTIC_CACHE_SCHEMA_VERSION,
            "entries": {},
        }

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    if (
        not isinstance(cache, dict)
        or cache.get("cache_schema_version") != SEMANTIC_CACHE_SCHEMA_VERSION
        or not isinstance(cache.get("entries"), dict)
    ):
        raise ValueError("Semantik-Cache besitzt ein ungültiges Dateiformat.")
    return cache

def write_semantic_cache(path, cache):
    """Schreibt vollständig in eine temporäre Datei und ersetzt dann atomar."""
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{cache_path.name}.",
        suffix=".tmp",
        dir=cache_path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, cache_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

def _prediction_from_cache_entry(entry, model_input, expected_hash):
    if not isinstance(entry, dict):
        return None
    metadata_matches = (
        entry.get("semantic_input_hash") == expected_hash
        and entry.get("model_id") == HYBRID_MODEL_ID
        and entry.get("reasoning_effort") == HYBRID_REASONING_EFFORT
        and entry.get("prompt_version") == HYBRID_PROMPT_VERSION
        and entry.get("schema_version") == HYBRID_SCHEMA_VERSION
        and isinstance(entry.get("assessed_at"), str)
        and bool(entry["assessed_at"].strip())
    )
    if not metadata_matches:
        return None

    prediction = {
        "item_id": model_input["item_id"],
        "assessment_status": entry.get("assessment_status"),
        "management_relevance": entry.get("management_relevance"),
        "actionability": entry.get("actionability"),
        "significance": entry.get("significance"),
        "reason": entry.get("reason"),
        "summary": entry.get("summary"),
        "why_relevant": entry.get("why_relevant"),
        "watch_next": entry.get("watch_next"),
    }
    try:
        _validate_hybrid_predictions_v2([prediction], [model_input["item_id"]])
    except (AttributeError, TypeError, ValueError):
        return None
    return prediction

def _load_hybrid_evaluator():
    path = Path(__file__).with_name("evaluate_hybrid_c.py")
    spec = importlib.util.spec_from_file_location("sneki_hybrid_evaluator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Hybrid-C-Evaluator konnte nicht geladen werden.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def request_hybrid_semantics(model_inputs):
    """Genau ein Batch; der Evaluator besitzt bewusst keine Retry-Logik."""
    evaluator = _load_hybrid_evaluator()
    if (
        evaluator.MODEL_ID != HYBRID_MODEL_ID
        or evaluator.REASONING_EFFORT != HYBRID_REASONING_EFFORT
        or evaluator.HYBRID_PROMPT_VERSION != HYBRID_PROMPT_VERSION
        or evaluator.HYBRID_SCHEMA_VERSION != HYBRID_SCHEMA_VERSION
    ):
        raise RuntimeError("Hybrid-C-Vertragsversionen stimmen nicht überein.")
    return evaluator.request_hybrid_assessments(model_inputs)

def _safe_log_message(error):
    message = str(error)
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s;,]+",
        r"\1[REDACTED]",
        message,
    )
    message = re.sub(r"(?i)(bearer\s+)[^\s;,]+", r"\1[REDACTED]", message)
    message = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", message)
    return message[:500]

def _safe_usage(usage):
    usage = usage if isinstance(usage, dict) else {}
    return {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
        "estimated_cost_usd": float(usage.get("estimated_cost_usd", 0)),
    }

def filter_source_freshness(items, source_config, reference_at):
    """Konfiguriertes Nachrichtenalter prüfen, bevor eine KI bewertet.

    Ältere Rohdaten bleiben erhalten. Unbekannte und zukünftige
    Veröffentlichungsdaten zählen nicht als aktuelle Nachrichten.
    Quellen ohne Altersregel behalten ihre bisherige Behandlung.
    """
    policies = {
        source["id"]: source["max_news_age_days"]
        for source in source_config
        if "max_news_age_days" in source
    }
    reference = parse_sort_timestamp(reference_at)
    if policies and reference is None:
        raise ValueError("Aktualitätsprüfung benötigt einen gültigen Bezugszeitpunkt.")
    result = []
    for item in items:
        max_days = policies.get(item.get("source_id"))
        if max_days is None:
            result.append(item)
            continue
        published = parse_sort_timestamp(item.get("published_at"))
        if published is not None and 0 <= reference - published <= max_days * 86400:
            result.append(item)
    return result


def select_candidates_for_mode(
    items,
    source_status,
    source_config,
    reference_at,
    *,
    mode=None,
    hybrid_provider=None,
    cache_path=None,
    limit=5,
):
    items = filter_source_freshness(items, source_config, reference_at)
    requested_mode = mode or get_ranking_mode()
    if requested_mode not in RANKING_MODES:
        requested_mode = "baseline"

    if requested_mode == "baseline":
        ranked = rank_candidates_baseline_v2(
            items, source_status, source_config, reference_at, limit
        )
        return [result["item"] for result in ranked], {
            "requested_mode": "baseline",
            "effective_mode": "baseline",
        }

    provider = hybrid_provider or request_hybrid_semantics
    eligible = _eligible_items(items, source_status)
    model_inputs = _hybrid_model_inputs(eligible)
    semantic_cache_path = (
        Path(cache_path)
        if cache_path is not None
        else DATA / "semantic-cache.json"
    )
    cache_hits = 0
    cache_misses = len(model_inputs)
    api_items_evaluated = 0
    api_call_performed = False
    try:
        cache = read_semantic_cache(semantic_cache_path)
        cached_predictions = []
        misses = []
        for model_input in model_inputs:
            cache_key = semantic_input_hash(model_input)
            prediction = _prediction_from_cache_entry(
                cache["entries"].get(cache_key),
                model_input,
                cache_key,
            )
            if prediction is None:
                misses.append(model_input)
            else:
                cached_predictions.append(prediction)

        cache_hits = len(cached_predictions)
        cache_misses = len(misses)
        usage = _safe_usage({})
        model = HYBRID_MODEL_ID
        reasoning_effort = HYBRID_REASONING_EFFORT
        new_predictions = []

        if misses:
            api_call_performed = True
            api_items_evaluated = len(misses)
            response = provider(misses)
            if isinstance(response, dict):
                new_predictions = response.get("predictions")
                usage = _safe_usage(response.get("usage"))
                model = response.get("model_id") or HYBRID_MODEL_ID
                reasoning_effort = (
                    response.get("reasoning_effort") or HYBRID_REASONING_EFFORT
                )
            else:
                new_predictions = response

            if model != HYBRID_MODEL_ID or reasoning_effort != HYBRID_REASONING_EFFORT:
                raise ValueError("Hybrid-Antwort verwendet einen unerwarteten Modellvertrag.")
            _validate_hybrid_predictions_v2(
                new_predictions,
                [model_input["item_id"] for model_input in misses],
            )

            prediction_by_id = {
                prediction["item_id"]: prediction
                for prediction in new_predictions
            }
            updated_cache = {
                "cache_schema_version": SEMANTIC_CACHE_SCHEMA_VERSION,
                "entries": dict(cache["entries"]),
            }
            assessed_at = datetime.now(timezone.utc).isoformat()
            for model_input in misses:
                entry = build_semantic_cache_entry(
                    model_input,
                    prediction_by_id[model_input["item_id"]],
                    assessed_at=assessed_at,
                )
                updated_cache["entries"][entry["semantic_input_hash"]] = entry
            write_semantic_cache(semantic_cache_path, updated_cache)

        predictions = cached_predictions + new_predictions

        ranked = rank_candidates_hybrid_v2(
            items,
            source_status,
            source_config,
            reference_at,
            predictions,
            limit,
        )
        print(
            "hybrid cache: "
            f"cache_hits={cache_hits}, cache_misses={cache_misses}, "
            f"api_items_evaluated={api_items_evaluated}, "
            f"api_call={'Ja' if api_call_performed else 'Nein'}, "
            f"model={model}, input_tokens={usage['input_tokens']}, "
            f"output_tokens={usage['output_tokens']}, "
            f"total_tokens={usage['total_tokens']}, "
            f"estimated_cost_usd={usage['estimated_cost_usd']:.8f}"
        )
        return [result["item"] for result in ranked], {
            "requested_mode": "hybrid",
            "effective_mode": "hybrid",
            "model": model,
            "reasoning_effort": reasoning_effort,
            "prompt_version": HYBRID_PROMPT_VERSION,
            "schema_version": HYBRID_SCHEMA_VERSION,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "api_items_evaluated": api_items_evaluated,
            "api_call_performed": api_call_performed,
            "usage": usage,
        }
    except Exception as error:
        print(
            "hybrid cache: "
            f"cache_hits={cache_hits}, cache_misses={cache_misses}, "
            f"api_items_evaluated={api_items_evaluated}, "
            f"api_call={'Ja' if api_call_performed else 'Nein'}, "
            "input_tokens=0, output_tokens=0, total_tokens=0, "
            "estimated_cost_usd=0.00000000"
        )
        print(
            "hybrid → baseline_fallback: "
            f"{type(error).__name__}: {_safe_log_message(error)}"
        )
        ranked = rank_candidates_baseline_v2(
            items, source_status, source_config, reference_at, limit
        )
        return [result["item"] for result in ranked], {
            "requested_mode": "hybrid",
            "effective_mode": "baseline_fallback",
            "error_class": type(error).__name__,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "api_items_evaluated": api_items_evaluated,
            "api_call_performed": api_call_performed,
        }

def deduplicate_source_urls(items, source_config):
    """Nur identische URLs oder ausdrücklich bestätigte URL-Aliase zusammenführen."""
    aliases = {source.get("id"): source.get("url_aliases", {}) for source in source_config}
    selected = {}
    for item in items:
        source_id = item.get("source_id")
        url = item.get("source_url")
        canonical = aliases.get(source_id, {}).get(url, url)
        # Ohne URL keine Gleichheit ableiten.
        key = (source_id, canonical) if canonical else (source_id, item.get("id"))
        previous = selected.get(key)
        def preference(value):
            return (value.get("source_url") == canonical,
                    parse_sort_timestamp(value.get("last_seen_at")) or 0,
                    parse_sort_timestamp(value.get("collected_at")) or 0,
                    str(value.get("id", "")))
        if previous is None or preference(item) > preference(previous):
            selected[key] = item
    return list(selected.values())


def editorial_topic(item):
    """Konservative Einordnung anhand des gelieferten Inhalts, nicht des Quellenlabels."""
    text = " ".join(str(item.get(key) or "") for key in ("title", "raw_excerpt"))
    ai = bool(re.search(r"\b(?:AI|KI|LLM|GenAI|artificial intelligence|künstliche intelligenz|machine learning)\b", text, re.I))
    if re.search(r"\b(?:AI Act|KI-Verordnung)\b", text, re.I):
        return "EU AI Act", True
    if re.search(r"\b(?:DSGVO|GDPR|Datenschutz|data protection|privacy)\b", text, re.I):
        return "DSGVO & Ethik", True
    if re.search(r"\b(?:cyber\w*|IT-Sicherheit|security|Sicherheitslücke|NIS2|Cyber Resilience Act)\b", text, re.I):
        return "IT Security", True
    if ai:
        if re.search(r"\b(?:governance|governancepflichten)\b", text, re.I):
            return "AI Governance", True
        if re.search(r"\b(?:project management|Projektmanagement|PMO)\b", text, re.I):
            return "AI & PM", True
        return "KI & Technologie", True
    if re.search(r"\b(?:project management|Projektmanagement|PMO)\b", text, re.I):
        return "Projektmanagement", False
    return "Digitalisierung & Kontext", False


def bundle_reporting_sources(items):
    """Nur klar gleiche CRA-Meldestart-Ereignisse am selben Tag bündeln."""
    grouped, result = {}, []
    for item in items:
        text = " ".join(str(item.get(key) or "") for key in ("title", "raw_excerpt"))
        reporting = bool(re.search(r"(?:CRA|Cyber Resilience Act|Single Reporting Platform)", text, re.I)
                         and re.search(r"(?:Meldepflicht|reporting|Meldestart)", text, re.I))
        key = (str(item.get("published_at") or "")[:10], "cra-reporting") if reporting else None
        if key and key in grouped:
            index = grouped[key]
            previous = result[index]
            # Deutscher BSI-Quellenauszug erklärt hier die Bedeutung ausführlicher.
            preferred, other = (item, previous) if item.get("source_id") == "bsi-security" else (previous, item)
            related = [*previous.get("_related_sources", []),
                       {"name": other.get("source"), "url": other.get("source_url")}]
            result[index] = {**preferred, "_related_sources": related}
        else:
            if key:
                grouped[key] = len(result)
            result.append(dict(item))
    return result


def select_useful_background(items, reference_at, limit):
    """Zielbezug zuerst, dann Aktualität; Quellenprestige verdrängt keine KI-/PM-Praxis."""
    reference = parse_sort_timestamp(reference_at)
    candidates = bundle_reporting_sources(items)
    def usefulness(item):
        topic, core = editorial_topic(item)
        fit = 3 if topic == "AI & PM" else 2 if core else 1 if topic == "Projektmanagement" else 0
        age = reference - parse_sort_timestamp(item.get("published_at"))
        recency = 2 if age <= 30 * 86400 else 1 if age <= 90 * 86400 else 0
        return fit * 4 + recency + bool(item.get("_hybrid_content"))
    selected, counts = [], {}
    while candidates and len(selected) < limit:
        winner = min(candidates, key=lambda item: (
            -(usefulness(item) - 3 * counts.get(editorial_topic(item)[0], 0)),
            -publication_sort_timestamp(item), item.get("id", "")))
        selected.append(winner)
        topic = editorial_topic(winner)[0]
        counts[topic] = counts.get(topic, 0) + 1
        candidates.remove(winner)
    return selected


def select_edition_candidates(items, source_status, source_config, reference_at, *, mode=None, hybrid_provider=None, cache_path=None, limit=5):
    """Aktuelle Nachrichten getrennt von Hintergrund auswählen; keine KI für Altinhalte."""
    reference = parse_sort_timestamp(reference_at)
    if reference is None:
        raise ValueError("Aktualitätsprüfung benötigt einen gültigen Bezugszeitpunkt.")
    current, background = [], []
    for item in deduplicate_source_urls(_eligible_items(items, source_status), source_config):
        published = parse_sort_timestamp(item.get("published_at"))
        # Unbekannte oder zukünftige Daten sind keine belastbare Nachricht.
        # Die Originale bleiben in raw-items.json erhalten.
        if published is None or published > reference:
            continue
        if reference - published <= 7 * 86400 and editorial_topic(item)[1]:
            current.append(item)
        elif reference - published <= 7 * 86400:
            text = " ".join(str(item.get(key) or "") for key in ("title", "raw_excerpt"))
            if editorial_topic(item)[0] == "Projektmanagement" or re.search(
                r"\b(?:digital innovation|digital infrastructure|Digitalisierung)\b", text, re.I
            ):
                background.append({**item, "_reading": True})
        else:
            background.append(item)
    news, ranking = select_candidates_for_mode(
        current, source_status, source_config, reference_at, mode=mode,
        hybrid_provider=hybrid_provider, cache_path=cache_path, limit=limit,
    )
    # Vorhandene Redaktionstexte nutzen, bevor Nutzwert und Vielfalt bewertet werden.
    try:
        cache = read_semantic_cache(Path(cache_path) if cache_path is not None else DATA / "semantic-cache.json")
    except (ValueError, OSError):
        cache = {"entries": {}}
    enriched = []
    for item in background:
        model_input = _hybrid_model_inputs([item])[0]
        key = semantic_input_hash(model_input)
        prediction = _prediction_from_cache_entry(cache["entries"].get(key), model_input, key)
        if prediction and prediction["assessment_status"] == "scored":
            item = {**item, "_hybrid_content": {field: prediction[field] for field in ("summary", "why_relevant", "watch_next")}}
        enriched.append(item)
    selected_background = select_useful_background(enriched, reference_at, limit)
    ranking["selection"] = {
        "recent_core_candidates": len(current),
        "recent_core_not_selected": len(current) - len(news),
        "unavailable_sources": [source["name"] for source in source_status
                                if source.get("status") not in {"ok", "degraded"}],
    }
    return news, selected_background, ranking


def ensure_publishable(candidates, source_status):
    if not candidates:
        raise RuntimeError(
            "Briefing nicht publishable: keine verwendbare Meldung vorhanden."
        )

    usable_core_source = any(
        source.get("type") == "core"
        and source.get("status") in {"ok", "degraded"}
        for source in source_status
    )
    if not usable_core_source:
        raise RuntimeError(
            "Briefing nicht publishable: keine Kernquelle mit Status ok oder degraded."
        )


def _deterministic_editorial_fallback(item):
    """Neutrale Texte aus vorhandener Kategorie; keine neuen Tatsachenbehauptungen."""
    categories = set(item.get("category") or [])

    if "AI & PM" in categories:
        return {
            "why_relevant": (
                "Für IT- und Projektverantwortliche relevant, weil die Meldung eine "
                "konkrete Entwicklung an der Schnittstelle von KI und Projektmanagement beschreibt."
            ),
            "watch_next": (
                "Weitere Konkretisierungen und Praxisbeispiele in der Originalquelle verfolgen."
            ),
        }
    if categories & {"EU AI Act", "AI Governance"}:
        return {
            "why_relevant": (
                "Für Unternehmen relevant, weil die Meldung eine konkrete Entwicklung "
                "zu KI-Regulierung oder Governance beschreibt, die strategisch eingeordnet werden sollte."
            ),
            "watch_next": (
                "Weitere Guidance und Konkretisierungen zum Anwendungsbereich in der Originalquelle beobachten."
            ),
        }
    if "DSGVO & Ethik" in categories:
        return {
            "why_relevant": (
                "Für Unternehmen relevant, weil die Meldung eine konkrete Entwicklung "
                "zu Datenschutz oder verantwortungsvoller KI-Nutzung beschreibt."
            ),
            "watch_next": (
                "Neue Guidance und weitere Konkretisierungen der zuständigen Quelle beobachten."
            ),
        }

    category = next(iter(categories), "dem betreffenden Fachgebiet")
    return {
        "why_relevant": (
            "Für Verantwortliche relevant, weil die Meldung eine konkrete Entwicklung "
            f"aus dem Bereich {category} beschreibt."
        ),
        "watch_next": (
            "Weitere Aktualisierungen und belastbare Konkretisierungen in der Originalquelle beobachten."
        ),
    }


def make_story(item, rank, *, content_kind="current"):
    excerpt = item.get("raw_excerpt") or "Zusammenfassung nicht verfügbar; Titel und Quelldaten bleiben sichtbar."
    topic, _ = editorial_topic(item)
    editorial = item.get("_hybrid_content") or _deterministic_editorial_fallback({**item, "category": [topic]})
    summary = editorial.get("summary") or excerpt
    if item.get("_reading"):
        content_kind = "reading"
    return {
        "id": item["id"],
        "category": topic,
        "rank": rank,
        "title": item.get("title") or item.get("source"),
        "summary": summary[:420],
        "summary_origin": "generated" if editorial.get("summary") else "source_excerpt",
        "why_relevant": editorial["why_relevant"],
        "watch_next": editorial["watch_next"],
        "source": item.get("source"),
        "source_type": item.get("source_type"),
        "source_url": item.get("source_url"),
        "published_at": item.get("published_at"),
        "collected_at": item.get("collected_at"),
        "verification": item.get("verification"),
        "status": item.get("status", "ok"),
        "is_top5": content_kind == "current",
        "content_kind": content_kind,
        "related_sources": item.get("_related_sources", []),
        "social_verified": False
    }

def build_edition(name, raw, *, preview=False):
    now = now_local()
    source_status = raw.get("source_status", [])
    eligible = _eligible_items(raw.get("items", []), source_status)
    ensure_publishable(eligible, source_status)
    candidates, background, ranking = select_edition_candidates(
        raw.get("items", []),
        source_status,
        read_source_config(),
        now.isoformat(),
        limit=5,
    )
    ensure_publishable(candidates + background, source_status)
    briefing_mode = (
        "Hybrid-C-Semantik mit deterministischem Ranking."
        if ranking["effective_mode"] == "hybrid"
        else "Deterministische Ranking-Baseline ohne kostenpflichtige KI-API."
    )
    result = {
        "schema_version": "1.0",
        "generated_at": now.isoformat(timespec="seconds"),
        "mode": "live",
        "edition": name,
        "briefing": [
            briefing_mode,
            "Primärquellen werden bevorzugt; Social Radar ist deaktiviert.",
            ("Aktuelle Meldungen: Veröffentlichungen der letzten 7 Tage. Lesestücke und ältere Inhalte sind separat eingeordnet."
             if candidates else "Keine aktuellen Kernmeldungen in der verfügbaren Auswahl der letzten 7 Tage. Lesestücke und Hintergrund bleiben verfügbar.")
        ],
        "items": ([make_story(x, i+1) for i, x in enumerate(candidates)]
                  + [make_story(x, len(candidates)+i+1, content_kind="background")
                     for i, x in enumerate(background)]),
        "freshness": {"news_window_days": 7, "current_count": len(candidates),
                      "background_count": len(background)},
        "signals": {
            "history_state": "building",
            "days_available": 1,
            "topics": []
        },
        "source_status": raw.get("source_status", []),
        "ranking": ranking,
    }

    selection = ranking.get("selection", {})
    lead = result["items"][0]
    result["editorial_brief"] = {
        "title": "Aktuelle Auswahl" if candidates else "Zuletzt relevant für KI und Projektmanagement",
        "summary": lead["summary"],
        "why_relevant": lead["why_relevant"],
        "watch_next": lead["watch_next"],
        "item_id": lead["id"],
        "published_at": lead["published_at"],
        "context": ("Ausgewählte Kernmeldungen aus dem Zeitfenster der letzten 7 Tage."
                    if candidates else "Im Zeitfenster der letzten 7 Tage wurde keine ausreichend belegte Kernmeldung ausgewählt. Die folgenden Beiträge dienen zur Einordnung."),
        "limits": ([f"Nach der Inhaltsbewertung nicht ausgewählte aktuelle Kandidaten: {selection['recent_core_not_selected']}."]
                   if selection.get("recent_core_not_selected") else [])
                  + (["Letzter Abruf eingeschränkt: " + ", ".join(selection["unavailable_sources"]) + "."]
                     if selection.get("unavailable_sources") else []),
    }
    serialized = json.dumps(result, ensure_ascii=False, indent=2)

    if preview:
        # Ein manueller Testlauf schreibt ausschließlich eine separate Preview.
        # Die bestehende Live-Datei und das Produktionsarchiv bleiben unangetastet.
        (DATA / "manual-preview.json").write_text(serialized, encoding="utf-8")
        print(f"{name}-Edition gebaut: {len(candidates)} aktuelle Meldungen, {len(background)} Hintergrundinformationen")
        return

    # Aktuelle Edition für Sites
    (DATA / "morning-intelligence.json").write_text(
        serialized, encoding="utf-8"
    )

    # Edition zusätzlich archivieren
    daydir = DATA / "archive" / now.strftime("%Y-%m-%d")
    daydir.mkdir(parents=True, exist_ok=True)
    (daydir / f"{name}.json").write_text(
        serialized, encoding="utf-8"
    )
    print(f"{name}-Edition gebaut: {len(candidates)} aktuelle Meldungen, {len(background)} Hintergrundinformationen")

def main():
    now = now_local()
    raw = read_raw()

    # Bei manuellem Workflow-Start immer eine Preview bauen.
    import os
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    edition = EDITION_HOURS.get(now.hour)
    if manual:
        build_edition("manual-preview", raw, preview=True)
    elif edition:
        build_edition(edition, raw)
    else:
        print(f"{now:%H:%M}: nur Collection, keine Edition.")

if __name__ == "__main__":
    main()
