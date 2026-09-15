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
    (ROOT / "sources.json").read_text(
        encoding="utf-8"
    )
)

TZ = ZoneInfo(
    SOURCES.get(
        "timezone",
        "Europe/Berlin"
    )
)


def now_iso() -> str:
    return datetime.now(
        TZ
    ).isoformat(
        timespec="seconds"
    )


def clean_text(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        text or ""
    ).strip()


def stable_id(
    source_id: str,
    url: str,
    title: str
) -> str:

    raw = (
        f"{source_id}|{url}|{title}"
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        raw
    ).hexdigest()[:20]


def content_hash(
    title: str,
    desc: str
) -> str:

    return hashlib.sha256(
        (
            title
            + "|"
            + desc
        ).encode(
            "utf-8"
        )
    ).hexdigest()


def fetch_web(
    source: dict
) -> list[dict]:

    """
    Standard-Collector für Quellen
    ohne Spezialadapter.

    Liest:
    - Seitentitel
    - Meta-Beschreibung

    Dient weiterhin als einfache
    Fallback-Variante.
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
        and meta.get(
            "content"
        )
    ):
        desc = clean_text(
            meta[
                "content"
            ]
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
        None,

        "collected_at":
        now_iso(),

        "verification":
        (
            "primary"
            if source["role"]
            == "primary"
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

    return [
        item
    ]


def extract_published_at(
    soup: BeautifulSoup
) -> str | None:

    """
    Versucht das Veröffentlichungsdatum
    möglichst robust zu finden.

    Reihenfolge:

    1. strukturierte Meta-Daten
    2. HTML <time>-Element
    3. sonst None
    """

    published_at = None

    date_meta = (
        soup.find(
            "meta",
            attrs={
                "property":
                "article:published_time"
            }
        )
        or
        soup.find(
            "meta",
            attrs={
                "name":
                "date"
            }
        )
        or
        soup.find(
            "meta",
            attrs={
                "name":
                "DC.date"
            }
        )
        or
        soup.find(
            "meta",
            attrs={
                "name":
                "dcterms.date"
            }
        )
    )

    if (
        date_meta
        and date_meta.get(
            "content"
        )
    ):

        published_at = clean_text(
            date_meta[
                "content"
            ]
        )

    if not published_at:

        time_tag = soup.find(
            "time"
        )

        if time_tag:

            published_at = (
                time_tag.get(
                    "datetime"
                )
                or
                clean_text(
                    time_tag.get_text(
                        " ",
                        strip=True
                    )
                )
            )

    return published_at


def fetch_eu_ai_news(
    source: dict
) -> list[dict]:

    """
    Spezialadapter für:

    European Commission /
    Shaping Europe's Digital Future

    Ziel:

    Nicht nur die Startseite speichern,
    sondern einzelne News-Meldungen
    erfassen.

    Gespeichert werden:

    - Titel
    - Original-URL
    - Veröffentlichungsdatum
    - Meta-Beschreibung
    - Zeitstempel der Sammlung

    Es werden KEINE vollständigen
    Artikeltexte gespeichert.
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

        # Nur echte News-Links
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

        # Navigation,
        # leere Links,
        # Mini-Texte ignorieren
        if len(
            title
        ) < 20:
            continue

        seen_urls.add(
            url
        )

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

            # Detail-H1 bevorzugen

            h1 = detail_soup.find(
                "h1"
            )

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
                and meta.get(
                    "content"
                )
            ):

                desc = clean_text(
                    meta[
                        "content"
                    ]
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

            items.append(
                item
            )

        except Exception as e:

            print(
                "EU-Detailseite "
                "übersprungen: "
                f"{url}: {e}"
            )

        # Erst einmal bewusst begrenzen
        if len(
            items
        ) >= 10:
            break

    if not items:

        raise RuntimeError(
            "EU-News-Adapter hat "
            "keine Einzelmeldungen "
            "gefunden."
        )

    return items


def load_existing() -> list[dict]:

    """
    Bereits vorhandene Rohdaten laden.

    Dadurch verlieren wir ältere
    Meldungen nicht bei jedem Lauf.
    """

    p = (
        DATA
        / "raw-items.json"
    )

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

    """
    Entscheidet,
    welcher Adapter verwendet wird.

    adapter = eu_ai_news
    -> EU-Spezialadapter

    kein Adapter
    -> Standard-Collector
    """

    adapter = source.get(
        "adapter"
    )

    if (
        adapter
        == "eu_ai_news"
    ):

        return fetch_eu_ai_news(
            source
        )

    return fetch_web(
        source
    )


def main():

    DATA.mkdir(
        exist_ok=True
    )

    previous = (
        load_existing()
    )

    by_key = {
        x.get("id"): x
        for x in previous
        if x.get("id")
    }

    source_status = []

    for source in SOURCES[
        "sources"
    ]:

        if not source.get(
            "enabled",
            True
        ):
            continue

        try:

            items = (
                collect_source(
                    source
                )
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

                    # Falls beim alten Eintrag
                    # noch kein published_at
                    # vorhanden war,
                    # übernehmen wir jetzt
                    # ein neu gefundenes Datum.

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
                len(
                    items
                )
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
                str(
                    e
                )[:240]
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
