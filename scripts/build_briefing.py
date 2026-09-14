from __future__ import annotations
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TZ = ZoneInfo("Europe/Berlin")

EDITION_HOURS = {
    7: "morning",
    15: "afternoon",
}

def now_local():
    return datetime.now(TZ)

def read_raw():
    p = DATA / "raw-items.json"
    if not p.exists():
        return {"items": [], "source_status": []}
    return json.loads(p.read_text(encoding="utf-8"))

def choose_candidates(items, limit=5):
    """
    V1 bewusst deterministisch:
    - Core/Primary bevorzugen
    - neueste zuerst
    - keine Social-Quellen
    - maximal 5
    Später kann HIER ein einziger AI-Batch ergänzt werden.
    """
    filtered = [
        x for x in items
        if x.get("source_type") != "social"
        and x.get("status") == "ok"
    ]
    filtered.sort(
        key=lambda x: (
            0 if x.get("verification") == "primary" else 1,
            x.get("last_seen_at","")
        ),
        reverse=False
    )
    return filtered[:limit]

def make_story(item, rank):
    excerpt = item.get("raw_excerpt") or "Neue bzw. geänderte Information an der Quelle erkannt."
    return {
        "id": item["id"],
        "category": (item.get("category") or ["General AI"])[0],
        "rank": rank,
        "title": item.get("title") or item.get("source"),
        "summary": excerpt[:420],
        "why_relevant": "Für sneKI prüfen: Relevanz für Regulierung, Governance, Datenschutz oder AI-Projektmanagement.",
        "watch_next": "Primärquelle auf konkrete Änderungen prüfen.",
        "source": item.get("source"),
        "source_type": item.get("source_type"),
        "source_url": item.get("source_url"),
        "published_at": item.get("published_at"),
        "collected_at": item.get("collected_at"),
        "verification": item.get("verification"),
        "status": item.get("status", "ok"),
        "is_top5": True,
        "social_verified": False
    }

def build_edition(name, raw):
    now = now_local()
    candidates = choose_candidates(raw.get("items", []), 5)
    result = {
        "schema_version": "1.0",
        "generated_at": now.isoformat(timespec="seconds"),
        "mode": "live",
        "edition": name,
        "briefing": [
            "Automatisch erzeugte V1 ohne kostenpflichtige KI-API.",
            "Primärquellen werden bevorzugt; Social Radar ist deaktiviert."
        ],
        "items": [make_story(x, i+1) for i, x in enumerate(candidates)],
        "signals": {
            "history_state": "building",
            "days_available": 1,
            "topics": []
        },
        "source_status": raw.get("source_status", [])
    }

    # Aktuelle Edition für Sites
    (DATA / "morning-intelligence.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Edition zusätzlich archivieren
    daydir = DATA / "archive" / now.strftime("%Y-%m-%d")
    daydir.mkdir(parents=True, exist_ok=True)
    (daydir / f"{name}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{name}-Edition gebaut: {len(candidates)} Items")

def main():
    now = now_local()
    raw = read_raw()

    # Bei manuellem Workflow-Start immer eine Preview bauen.
    import os
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    edition = EDITION_HOURS.get(now.hour)
    if edition:
        build_edition(edition, raw)
    elif manual:
        build_edition("manual-preview", raw)
    else:
        print(f"{now:%H:%M}: nur Collection, keine Edition.")

if __name__ == "__main__":
    main()
