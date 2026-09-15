from __future__ import annotations

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

SOURCES = json.loads(
    (ROOT / "sources.json").read_text(encoding="utf-8")
)

TZ = ZoneInfo(
    SOURCES.get("timezone", "Europe/Berlin")
)


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def stable_id(
    source_id: str,
    url: str,
    title: str
) -> str:

    raw = f"{source_id}|{url}|{title}".encode("utf-8")

    return hashlib.sha256(raw).hexdigest()[:20]


def content_hash(
    title: str,
    desc: str
) -> str:

    return hashlib.sha256(
        (title + "|" + desc).encode("utf-8")
    ).hexdigest()


def normalize_date_string(
    value: str | None
) -> str | None:

    if not value:
        return None

    value = clean_text(value)

    if re.match(
        r"^\d{4}-\d{2}-\d{2}",
        value
    ):
        return value

    formats = [
        "%d %B %Y",
        "%d %b %Y",
        "%d/%m/%Y",
        "%d.%m.%Y"
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(
                value,
                fmt
            )

            return parsed.date().isoformat()

        except ValueError:
            pass

    return value


def extract_published_at(
    soup: BeautifulSoup
) -> str | None:

    """
    Allgemeine Datumserkennung.

    Reihenfolge:
    1. Meta-Daten
    2. <time>-Elemente
    3. sichtbarer Text
    """

    meta_candidates = [
        {
            "property":
            "article:published_time"
        },
        {
            "name":
            "date"
        },
        {
            "name":
            "DC.date"
        },
        {
            "name":
            "dcterms.date"
        },
        {
            "name":
            "datePublished"
        }
    ]

    for attrs in meta_candidates:

        meta = soup.find(
            "meta",
            attrs=attrs
        )

        if (
            meta
            and meta.get("content")
        ):

            return normalize_date_string(
                meta.get("content")
            )

    for time_tag in soup.find_all("time"):

        value = (
            time_tag.get("datetime")
            or clean_text(
                time_tag.get_text(
                    " ",
                    strip=True
                )
            )
        )

        if value:

            return normalize_date_string(
                value
            )

    page_text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    patterns = [
        r"\bPublication\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b",
        r"\bPublished\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            page_text,
            flags=re.IGNORECASE
        )

        if match:

            return normalize_date_string(
                match.group(1)
            )

    return None


def fetch_web(
    source: dict
) -> list[dict]:

    """
    Standard-Fallback für Quellen
    ohne Spezialadapter.
    """

    headers = {
        "User-Agent":
        "sneKI-Morning-Intelligence/1.0 "
        "(+public research dashboard)"
    }

    r = requests.get(
        source["url"],
        headers=headers,
        timeout=20
    )

    r.raise_for_status()

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    title = clean_text(
        soup.title.get_text(
            " ",
            strip=True
        )
        if soup.title
        else source["name"]
    )

    desc = ""

    meta = (
        soup.find(
            "meta",
            attrs={
                "name":
                "description"
            }
        )
        or
        soup.find(
            "meta",
            attrs={
                "property":
                "og:description"
            }
        )
    )

    if (
        meta
        and meta.get("content")
    ):

        desc = clean_text(
            meta["content"]
        )

    item = {
        "id":
        stable_id(
            source["id"],
            source["url"],
            title
        ),

        "source_id":
        source["id"],

        "source":
        source["name"],

        "source_type":
        source["role"],

        "source_url":
        source["url"],

        "category":
        source.get(
            "category",
            []
        ),

        "title":
        title,

        "raw_excerpt":
        desc[:800],

        "published_at":
        extract_published_at(
            soup
        ),

        "collected_at":
        now_iso(),

        "verification":
        (
            "primary"
            if source["role"] == "primary"
            else source["role"]
        ),

        "status":
        "ok",

        "content_hash":
        content_hash(
            title,
            desc
        )
    }

    return [item]


def fetch_eu_ai_news(
    source: dict
) -> list[dict]:

    """
    EU-Kommission Spezialadapter.

    Liest einzelne News-Meldungen.
    """

    headers = {
        "User-Agent":
        "sneKI-Morning-Intelligence/1.0 "
        "(+public research dashboard)"
    }

    r = requests.get(
        source["url"],
        headers=headers,
        timeout=20
    )

    r.raise_for_status()

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    items = []
    seen_urls = set()

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = clean_text(
            link.get(
                "href",
                ""
            )
        )

        if not href:
            continue

        if "/en/news/" not in href:
            continue

        url = urljoin(
            source["url"],
            href
        )

        if url in seen_urls:
            continue

        title = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if len(title) < 20:
            continue

        seen_urls.add(url)

        try:

            detail = requests.get(
                url,
                headers=headers,
                timeout=20
            )

            detail.raise_for_status()

            detail_soup = BeautifulSoup(
                detail.text,
                "html.parser"
            )

            h1 = detail_soup.find("h1")

            if h1:

                detail_title = clean_text(
                    h1.get_text(
                        " ",
                        strip=True
                    )
                )

                if detail_title:
                    title = detail_title

            desc = ""

            meta = (
                detail_soup.find(
                    "meta",
                    attrs={
                        "name":
                        "description"
                    }
                )
                or
                detail_soup.find(
                    "meta",
                    attrs={
                        "property":
                        "og:description"
                    }
                )
            )

            if (
                meta
                and meta.get("content")
            ):

                desc = clean_text(
                    meta["content"]
                )

            published_at = (
                extract_published_at(
                    detail_soup
                )
            )

            item = {
                "id":
                stable_id(
                    source["id"],
                    url,
                    title
                ),

                "source_id":
                source["id"],

                "source":
                source["name"],

                "source_type":
                source["role"],

                "source_url":
                url,

                "category":
                source.get(
                    "category",
                    []
                ),

                "title":
                title,

                "raw_excerpt":
                desc[:800],

                "published_at":
                published_at,

                "collected_at":
                now_iso(),

                "verification":
                "primary",

                "status":
                "ok",

                "content_hash":
                content_hash(
                    title,
                    desc
                )
            }

            items.append(item)

        except Exception as e:

            print(
                "EU-Detailseite "
                f"übersprungen: {url}: {e}"
            )

        if len(items) >= 10:
            break

    if not items:

        raise RuntimeError(
            "EU-News-Adapter hat "
            "keine Einzelmeldungen gefunden."
        )

    return items


def fetch_eurlex_ai_act(
    source: dict
) -> list[dict]:

    """
    Spezialadapter für EUR-Lex.

    Ermittelt die aktuell konsolidierte
    Fassung des EU AI Act.
    """

    headers = {
        "User-Agent":
        "sneKI-Morning-Intelligence/1.0 "
        "(+public research dashboard)"
    }

    r = requests.get(
        source["url"],
        headers=headers,
        timeout=25
    )

    r.raise_for_status()

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    page_text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    current_date = None

    patterns = [
        r"Current consolidated version\s*:\s*(\d{2}/\d{2}/\d{4})",
        r"Access current version\s*\((\d{2}/\d{2}/\d{4})\)",
        r"current version\s*\((\d{2}/\d{2}/\d{4})\)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            page_text,
            flags=re.IGNORECASE
        )

        if match:

            current_date = (
                normalize_date_string(
                    match.group(1)
                )
            )

            break

    if not current_date:

        match = re.search(
            r"02024R1689.*?"
            r"(\d{2}\.\d{2}\.\d{4})",
            page_text,
            flags=re.IGNORECASE
        )

        if match:

            current_date = (
                normalize_date_string(
                    match.group(1)
                )
            )

    if not current_date:

        match = re.search(
            r"02024R1689-(\d{8})",
            page_text,
            flags=re.IGNORECASE
        )

        if match:

            raw = match.group(1)

            current_date = (
                f"{raw[0:4]}-"
                f"{raw[4:6]}-"
                f"{raw[6:8]}"
            )

    if not current_date:

        raise RuntimeError(
            "EUR-Lex: aktuelle "
            "konsolidierte Fassung "
            "konnte nicht erkannt werden."
        )

    version_url = (
        "https://eur-lex.europa.eu/"
        "eli/reg/2024/1689/"
        f"{current_date}/eng"
    )

    amendments = []

    amendment_patterns = [
        r"REGULATION \(EU\)\s+(\d{4}/\d{4})",
        r"Regulation \(EU\)\s+(\d{4}/\d{4})"
    ]

    for pattern in amendment_patterns:

        matches = re.findall(
            pattern,
            page_text,
            flags=re.IGNORECASE
        )

        for amendment in matches:

            if amendment == "2024/1689":
                continue

            if amendment not in amendments:
                amendments.append(
                    amendment
                )

    amendment_text = ""

    if amendments:

        amendment_text = (
            " Änderungen erkannt: "
            + ", ".join(
                f"Regulation (EU) {x}"
                for x in amendments
            )
            + "."
        )

    title = (
        "AI Act – konsolidierte Fassung "
        f"{current_date}"
    )

    desc = (
        "Aktuelle konsolidierte Fassung "
        "der Regulation (EU) 2024/1689 "
        "(Artificial Intelligence Act) "
        f"mit Stand {current_date}."
        f"{amendment_text}"
    )

    item = {
        "id":
        stable_id(
            source["id"],
            version_url,
            title
        ),

        "source_id":
        source["id"],

        "source":
        source["name"],

        "source_type":
        source["role"],

        "source_url":
        version_url,

        "category":
        source.get(
            "category",
            []
        ),

        "title":
        title,

        "raw_excerpt":
        desc[:800],

        "published_at":
        current_date,

        "collected_at":
        now_iso(),

        "verification":
        "primary",

        "status":
        "ok",

        "content_hash":
        content_hash(
            title,
            desc
        )
    }

    return [item]


def load_existing() -> list[dict]:

    p = DATA / "raw-items.json"

    if not p.exists():
        return []

    try:

        return json.loads(
            p.read_text(
                encoding="utf-8"
            )
        ).get(
            "items",
            []
        )

    except Exception:

        return []


def collect_source(
    source: dict
) -> list[dict]:

    adapter = source.get(
        "adapter"
    )

    if adapter == "eu_ai_news":

        return fetch_eu_ai_news(
            source
        )

    if adapter == "eurlex_ai_act":

        return fetch_eurlex_ai_act(
            source
        )

    return fetch_web(
        source
    )


def main():

    DATA.mkdir(
        exist_ok=True
    )

    previous = load_existing()

    by_key = {
        x.get("id"): x
        for x in previous
        if x.get("id")
    }

    source_status = []

    for source in SOURCES["sources"]:

        if not source.get(
            "enabled",
            True
        ):

            continue

        try:

            items = collect_source(
                source
            )

            for item in items:

                old = by_key.get(
                    item["id"]
                )

                if (
                    old
                    and
                    old.get(
                        "content_hash"
                    )
                    ==
                    item.get(
                        "content_hash"
                    )
                ):

                    old[
                        "last_seen_at"
                    ] = item[
                        "collected_at"
                    ]

                    if (
                        not old.get(
                            "published_at"
                        )
                        and
                        item.get(
                            "published_at"
                        )
                    ):

                        old[
                            "published_at"
                        ] = item[
                            "published_at"
                        ]

                    by_key[
                        item["id"]
                    ] = old

                else:

                    item[
                        "first_seen_at"
                    ] = item[
                        "collected_at"
                    ]

                    item[
                        "last_seen_at"
                    ] = item[
                        "collected_at"
                    ]

                    by_key[
                        item["id"]
                    ] = item

            source_status.append({
                "name":
                source["name"],

                "type":
                "core",

                "status":
                "ok",

                "last_update":
                now_iso(),

                "items_found":
                len(items)
            })

        except Exception as e:

            source_status.append({
                "name":
                source["name"],

                "type":
                "core",

                "status":
                "failed",

                "last_update":
                now_iso(),

                "note":
                str(e)[:240]
            })

    payload = {
        "schema_version":
        "1.0",

        "collected_at":
        now_iso(),

        "items":
        sorted(
            by_key.values(),
            key=lambda x:
            x.get(
                "last_seen_at",
                ""
            ),
            reverse=True
        ),

        "source_status":
        source_status
    }

    output_path = (
        DATA
        / "raw-items.json"
    )

    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"{len(payload['items'])} "
        "Items gespeichert"
    )


if __name__ == "__main__":
    main()
