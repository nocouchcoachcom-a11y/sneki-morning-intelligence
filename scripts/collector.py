from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib, json, re
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCES = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
TZ = ZoneInfo(SOURCES.get("timezone", "Europe/Berlin"))

def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def stable_id(source_id: str, url: str, title: str) -> str:
    raw = f"{source_id}|{url}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]

def fetch_web(source: dict) -> list[dict]:
    """
    Robuster Minimal-Collector:
    - holt eine offizielle Seite
    - extrahiert Titel + Meta-Beschreibung als Änderungssignal
    - speichert KEINE vollständigen Artikeltexte
    - dient als kostengünstige V1
    """
    headers = {
        "User-Agent": "sneKI-Morning-Intelligence/1.0 (+public research dashboard)"
    }
    r = requests.get(source["url"], headers=headers, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else source["name"])
    desc = ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if meta and meta.get("content"):
        desc = clean_text(meta["content"])

    item = {
        "id": stable_id(source["id"], source["url"], title),
        "source_id": source["id"],
        "source": source["name"],
        "source_type": source["role"],
        "source_url": source["url"],
        "category": source.get("category", []),
        "title": title,
        "raw_excerpt": desc[:800],
        "published_at": None,
        "collected_at": now_iso(),
        "verification": "primary" if source["role"] == "primary" else source["role"],
        "status": "ok",
        "content_hash": hashlib.sha256((title + "|" + desc).encode("utf-8")).hexdigest()
    }
    return [item]

def load_existing() -> list[dict]:
    p = DATA / "raw-items.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except Exception:
        return []

def main():
    DATA.mkdir(exist_ok=True)
    previous = load_existing()
    by_key = {x.get("id"): x for x in previous if x.get("id")}
    source_status = []

    for source in SOURCES["sources"]:
        if not source.get("enabled", True):
            continue
        try:
            items = fetch_web(source)
            for item in items:
                old = by_key.get(item["id"])
                if old and old.get("content_hash") == item.get("content_hash"):
                    # Bestehenden ersten Fund behalten, nur last_seen aktualisieren.
                    old["last_seen_at"] = item["collected_at"]
                    by_key[item["id"]] = old
                else:
                    item["first_seen_at"] = item["collected_at"]
                    item["last_seen_at"] = item["collected_at"]
                    by_key[item["id"]] = item
            source_status.append({
                "name": source["name"], "type": "core",
                "status": "ok", "last_update": now_iso()
            })
        except Exception as e:
            source_status.append({
                "name": source["name"], "type": "core",
                "status": "failed", "last_update": now_iso(),
                "note": str(e)[:240]
            })

    payload = {
        "schema_version": "1.0",
        "collected_at": now_iso(),
        "items": sorted(by_key.values(), key=lambda x: x.get("last_seen_at",""), reverse=True),
        "source_status": source_status
    }
    (DATA / "raw-items.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(payload['items'])} Items gespeichert")

if __name__ == "__main__":
    main()
