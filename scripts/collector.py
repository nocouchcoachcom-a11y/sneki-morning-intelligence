from __future__ import annotations

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import re
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

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

HEADERS = {
    "User-Agent":
    "sneKI-Morning-Intelligence/1.0 "
    "(public research dashboard)"
}


# ---------------------------------------------------------
# Allgemeine Hilfsfunktionen
# ---------------------------------------------------------

def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def clean_text(text: str | None) -> str:
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
        f"{title}|{desc}".encode("utf-8")
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
        return value[:10]

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
            continue

    return None


def extract_published_at(
    soup: BeautifulSoup
) -> str | None:

    """
    Allgemeine Datumserkennung
    für normale Webseiten.
    """

    candidates = [
        {"property": "article:published_time"},
        {"name": "date"},
        {"name": "DC.date"},
        {"name": "dcterms.date"},
        {"name": "datePublished"}
    ]

    for attrs in candidates:

        meta = soup.find(
            "meta",
            attrs=attrs
        )

        if meta and meta.get("content"):

            value = normalize_date_string(
                meta["content"]
            )

            if value:
                return value

    for time_tag in soup.find_all("time"):

        value = (
            time_tag.get("datetime")
            or time_tag.get_text(
                " ",
                strip=True
            )
        )

        normalized = normalize_date_string(
            value
        )

        if normalized:
            return normalized

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

            normalized = normalize_date_string(
                match.group(1)
            )

            if normalized:
                return normalized

    return None


# ---------------------------------------------------------
# Standard-Webadapter
# ---------------------------------------------------------

def fetch_web(
    source: dict
) -> list[dict]:

    r = requests.get(
        source["url"],
        headers=HEADERS,
        timeout=25
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
            attrs={"name": "description"}
        )
        or
        soup.find(
            "meta",
            attrs={"property": "og:description"}
        )
    )

    if meta and meta.get("content"):
        desc = clean_text(meta["content"])

    return [{
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
        source.get("category", []),

        "title":
        title,

        "raw_excerpt":
        desc[:800],

        "published_at":
        extract_published_at(soup),

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
    }]


# ---------------------------------------------------------
# Offizielle Artikel-Sitemaps
# ---------------------------------------------------------

def _matches_keywords(
    title: str,
    excerpt: str,
    keywords: list[str]
) -> bool:

    text = f"{title} {excerpt}"

    return any(
        re.search(
            rf"(?<!\w){re.escape(keyword)}(?!\w)",
            text,
            flags=re.IGNORECASE
        )
        for keyword in keywords
    )


def _article_excerpt(
    soup: BeautifulSoup,
    heading
) -> str:

    meta = (
        soup.find(
            "meta",
            attrs={"name": "description"}
        )
        or
        soup.find(
            "meta",
            attrs={"property": "og:description"}
        )
    )

    if meta and meta.get("content"):
        return clean_text(meta["content"])

    article = (
        heading.find_parent("article")
        if heading
        else None
    )

    container = article or soup.find("main") or soup

    for paragraph in container.find_all("p"):

        excerpt = clean_text(
            paragraph.get_text(
                " ",
                strip=True
            )
        )

        if len(excerpt) >= 60:
            return excerpt

    return ""


def _article_published_at(
    soup: BeautifulSoup,
    heading
) -> str | None:

    if heading:

        for parent in list(heading.parents)[:7]:

            time_tag = parent.find("time")

            if not time_tag:
                continue

            value = (
                time_tag.get("datetime")
                or time_tag.get_text(
                    " ",
                    strip=True
                )
            )

            normalized = normalize_date_string(
                value
            )

            if normalized:
                return normalized

    return extract_published_at(soup)


def fetch_sitemap_articles(
    source: dict
) -> list[dict]:

    """
    Nutzt die offizielle XML-Sitemap zur Entdeckung.
    Nur die dort verlinkten Originalartikel werden gelesen.
    """

    candidates = []
    request_timeout = source.get(
        "timeout_seconds",
        10
    )

    for sitemap_url in source.get(
        "sitemap_urls",
        []
    ):

        response = requests.get(
            sitemap_url,
            headers=HEADERS,
            timeout=request_timeout
        )

        response.raise_for_status()

        root = ET.fromstring(
            response.text
        )

        for node in root:

            values = {
                child.tag.rsplit("}", 1)[-1]:
                clean_text(child.text)
                for child in node
            }

            url = values.get("loc", "")
            path = urlparse(url).path

            if not any(
                path.startswith(prefix)
                for prefix in source.get(
                    "article_path_prefixes",
                    []
                )
            ):
                continue

            hostname = (
                urlparse(url).hostname
                or ""
            ).lower()

            if hostname not in {
                domain.lower()
                for domain in source.get(
                    "allowed_domains",
                    []
                )
            }:
                continue

            candidates.append((
                values.get("lastmod", ""),
                url
            ))

    candidates = sorted(
        set(candidates),
        reverse=True
    )

    if not candidates:
        raise RuntimeError(
            "Offizielle Sitemap enthält keine "
            "passenden Artikel-URLs."
        )

    items = []
    detail_pages_read = 0

    for _, url in candidates[:source.get(
        "scan_limit",
        12
    )]:

        try:

            detail = requests.get(
                url,
                headers=HEADERS,
                timeout=request_timeout
            )

            detail.raise_for_status()
            detail_pages_read += 1

            soup = BeautifulSoup(
                detail.text,
                "html.parser"
            )

            heading = soup.find("h1")
            title = clean_text(
                heading.get_text(
                    " ",
                    strip=True
                )
                if heading
                else ""
            )

            excerpt = _article_excerpt(
                soup,
                heading
            )

            if not title or not _matches_keywords(
                title,
                excerpt,
                source.get("keywords", [])
            ):
                continue

            published_at = _article_published_at(
                soup,
                heading
            )

            is_degraded = not (
                published_at
                and excerpt
            )

            items.append({
                "id": stable_id(
                    source["id"],
                    url,
                    title
                ),
                "source_id": source["id"],
                "source": source["name"],
                "source_type": source["role"],
                "source_url": url,
                "category": source.get(
                    "category",
                    []
                ),
                "title": title,
                "raw_excerpt": excerpt[:800],
                "published_at": published_at,
                "collected_at": now_iso(),
                "verification": "primary",
                "status": (
                    "degraded"
                    if is_degraded
                    else "ok"
                ),
                "collector_note": (
                    "Datum oder Kurztext fehlt."
                    if is_degraded
                    else None
                ),
                "content_hash": content_hash(
                    title,
                    excerpt
                )
            })

            if len(items) >= source.get(
                "max_items",
                10
            ):
                break

        except Exception as exc:

            print(
                "Sitemap-Artikel übersprungen: "
                f"{url}: {exc}"
            )

    if detail_pages_read == 0:
        raise RuntimeError(
            "Kein Artikel aus der offiziellen "
            "Sitemap war erreichbar."
        )

    return items


# ---------------------------------------------------------
# EU-Kommission / AI Office
# ---------------------------------------------------------

def fetch_eu_ai_news(
    source: dict
) -> list[dict]:

    """
    Liest echte einzelne News-Meldungen
    von Shaping Europe's Digital Future.
    """

    r = requests.get(
        source["url"],
        headers=HEADERS,
        timeout=25
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
            link.get("href")
        )

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
                headers=HEADERS,
                timeout=25
            )

            detail.raise_for_status()

            detail_soup = BeautifulSoup(
                detail.text,
                "html.parser"
            )

            h1 = detail_soup.find("h1")

            if h1:

                candidate = clean_text(
                    h1.get_text(
                        " ",
                        strip=True
                    )
                )

                if candidate:
                    title = candidate

            desc = ""

            meta = (
                detail_soup.find(
                    "meta",
                    attrs={"name": "description"}
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

            if meta and meta.get("content"):
                desc = clean_text(
                    meta["content"]
                )

            published_at = (
                extract_published_at(
                    detail_soup
                )
            )

            items.append({
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
            })

        except Exception as exc:

            print(
                f"EU-News übersprungen: "
                f"{url}: {exc}"
            )

        if len(items) >= 10:
            break

    if not items:

        raise RuntimeError(
            "EU-News-Adapter hat keine "
            "Einzelmeldungen gefunden."
        )

    return items


# ---------------------------------------------------------
# EUR-Lex / CELLAR
# ---------------------------------------------------------

def fetch_eurlex_cellar(
    source: dict
) -> list[dict]:

    """
    EUR-Lex über das offizielle
    Machine-to-Machine-System CELLAR.

    Kein HTML-Scraping.

    CELEX Original:
    32024R1689

    Konsolidierte Fassungen:
    02024R1689-YYYYMMDD
    """

    celex = source.get(
        "celex",
        "32024R1689"
    )

    consolidation_prefix = source.get(
        "consolidation_prefix",
        "02024R1689"
    )

    cellar_url = (
        "https://publications.europa.eu/"
        f"resource/celex/{celex}"
        "?language=en"
    )

    cellar_headers = {
        **HEADERS,
        "Accept":
        "application/xml;notice=tree"
    }

    detected_version = None
    collector_note = None

    try:

        r = requests.get(
            cellar_url,
            headers=cellar_headers,
            timeout=30,
            allow_redirects=True
        )

        r.raise_for_status()

        xml_text = r.text

        # CELLAR verwendet stabile CELEX-Kennungen.
        #
        # Beispiel:
        # 02024R1689-20260727

        pattern = (
            re.escape(
                consolidation_prefix
            )
            + r"-(\d{8})"
        )

        versions = sorted(
            set(
                re.findall(
                    pattern,
                    xml_text,
                    flags=re.IGNORECASE
                )
            )
        )

        if versions:

            newest = max(versions)

            detected_version = (
                f"{newest[0:4]}-"
                f"{newest[4:6]}-"
                f"{newest[6:8]}"
            )

    except Exception as exc:

        collector_note = (
            "CELLAR-Abfrage fehlgeschlagen: "
            + str(exc)[:160]
        )

    # -----------------------------------------------------
    # Sicherheitsnetz
    #
    # Wir wollen nicht wieder die ganze Pipeline verlieren,
    # nur weil EUR-Lex/CELLAR zeitweise nicht antwortet.
    #
    # Dieser Wert ist NICHT unsichtbar:
    # Status wird dann 'degraded'.
    # -----------------------------------------------------

    if not detected_version:

        fallback_version = source.get(
            "fallback_current_version"
        )

        if not fallback_version:

            raise RuntimeError(
                "EUR-Lex/CELLAR: "
                "keine konsolidierte Fassung erkannt "
                "und kein Fallback konfiguriert."
            )

        detected_version = (
            fallback_version
        )

        collector_note = (
            collector_note
            or
            "CELLAR lieferte keine erkennbare "
            "konsolidierte CELEX-Fassung."
        )

    version_url = (
        "https://eur-lex.europa.eu/"
        "eli/reg/2024/1689/"
        f"{detected_version}/eng"
    )

    is_degraded = (
        collector_note is not None
    )

    title = (
        "AI Act – konsolidierte Fassung "
        f"{detected_version}"
    )

    desc = (
        "Aktuelle konsolidierte Fassung "
        "der Regulation (EU) 2024/1689 "
        "(Artificial Intelligence Act). "
        f"Stand: {detected_version}."
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
        desc,

        "published_at":
        detected_version,

        "collected_at":
        now_iso(),

        "verification":
        "primary",

        "status":
        (
            "degraded"
            if is_degraded
            else "ok"
        ),

        "collector_note":
        collector_note,

        "content_hash":
        content_hash(
            title,
            desc
        )
    }

    return [item]


# ---------------------------------------------------------
# Bestehende Daten
# ---------------------------------------------------------

def load_existing() -> list[dict]:

    path = DATA / "raw-items.json"

    if not path.exists():
        return []

    try:

        return json.loads(
            path.read_text(
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

    adapter = source.get("adapter")

    if adapter == "eu_ai_news":

        return fetch_eu_ai_news(
            source
        )

    if adapter == "eurlex_cellar":

        return fetch_eurlex_cellar(
            source
        )

    if adapter == "sitemap_articles":

        return fetch_sitemap_articles(
            source
        )

    return fetch_web(
        source
    )


# ---------------------------------------------------------
# Hauptlauf
# ---------------------------------------------------------

def main():

    DATA.mkdir(
        exist_ok=True
    )

    previous = load_existing()

    by_key = {
        item.get("id"): item
        for item in previous
        if item.get("id")
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

            # EUR-Lex:
            # nur die aktuelle konsolidierte
            # Fassung behalten.
            #
            # Damit verschwinden auch die
            # alten V1-Einträge sauber.

            if source.get(
                "replace_previous",
                False
            ):

                source_id = source["id"]

                by_key = {
                    key: value
                    for key, value
                    in by_key.items()
                    if value.get(
                        "source_id"
                    ) != source_id
                }

            # Alte V1-Startseite
            # der EU-Kommission entfernen.

            if (
                source.get("adapter")
                == "eu_ai_news"
            ):

                source_id = source["id"]
                source_url = source["url"]

                by_key = {
                    key: value
                    for key, value
                    in by_key.items()
                    if not (
                        value.get(
                            "source_id"
                        ) == source_id
                        and
                        value.get(
                            "source_url"
                        ) == source_url
                    )
                }

            for item in items:

                old = by_key.get(
                    item["id"]
                )

                if (
                    old
                    and
                    old.get("content_hash")
                    ==
                    item.get("content_hash")
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

                    # Status aktualisieren
                    old["status"] = (
                        item.get(
                            "status",
                            "ok"
                        )
                    )

                    old["collector_note"] = (
                        item.get(
                            "collector_note"
                        )
                    )

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

            degraded_items = [
                item
                for item in items
                if item.get("status")
                == "degraded"
            ]

            if degraded_items:

                source_status.append({
                    "name":
                    source["name"],

                    "type":
                    source.get(
                        "status_type",
                        "core"
                    ),

                    "status":
                    "degraded",

                    "last_update":
                    now_iso(),

                    "items_found":
                    len(items),

                    "note":
                    degraded_items[0].get(
                        "collector_note"
                    )
                })

            else:

                source_status.append({
                    "name":
                    source["name"],

                    "type":
                    source.get(
                        "status_type",
                        "core"
                    ),

                    "status":
                    "ok",

                    "last_update":
                    now_iso(),

                    "items_found":
                    len(items)
                })

        except Exception as exc:

            source_status.append({
                "name":
                source["name"],

                "type":
                source.get(
                    "status_type",
                    "core"
                ),

                "status":
                "failed",

                "last_update":
                now_iso(),

                "note":
                str(exc)[:240]
            })

    payload = {
        "schema_version":
        "1.0",

        "collected_at":
        now_iso(),

        "items":
        sorted(
            by_key.values(),
            key=lambda item:
            item.get(
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
