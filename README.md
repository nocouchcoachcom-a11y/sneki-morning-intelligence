# sneKI // Morning Intelligence – GitHub V1

## Ziel

- **stündlich**: Quellen einsammeln
- **07:00 Europe/Berlin**: Morning Edition erzeugen
- **15:00 Europe/Berlin**: Afternoon Update erzeugen
- aktuelle Ausgabe: `data/morning-intelligence.json`
- Archiv: `data/archive/YYYY-MM-DD/morning.json` und `afternoon.json`

## Warum der GitHub-Workflow stündlich läuft

GitHub Actions verwendet UTC. Statt zwei komplizierter Cron-Ausdrücke mit Sommer-/Winterzeit
läuft der Job jede Stunde. Python prüft anschließend mit `Europe/Berlin`, ob lokal gerade
07:00 oder 15:00 Uhr ist. Dadurch bleibt die Logik DST-sicher.

## V1 bewusst ohne LLM

Die erste produktive Stufe sammelt, normalisiert und dedupliziert deterministisch.

Noch NICHT enthalten:
- kostenpflichtige LLM-API
- Reddit
- X
- automatische juristische Interpretation
- erfundene Signal-Scores

Später kann in `build_briefing.py` genau **ein Batch-Schritt** für Zusammenfassung,
Ranking und „Warum relevant“ ergänzt werden.

## GitHub Pages

Wenn das Repository öffentlich ist, kann `data/morning-intelligence.json`
später über GitHub Pages per HTTPS bereitgestellt werden.

Beispiel:
`https://USERNAME.github.io/REPO/data/morning-intelligence.json`

Diese URL kommt anschließend in die Sites-Konfiguration als `external_data_url`.

## Sicherheit

- keine Secrets im Frontend
- keine API-Keys im Repository
- nur öffentliche Primärquellen in V1
- Social Radar bleibt deaktiviert
- Ausfall einer Quelle stoppt die anderen Quellen nicht

## Wichtige V1-Grenze

Der Minimal-Collector erkennt Änderungen auf den angegebenen offiziellen Seiten.
Für hochwertige echte News-Einträge bauen wir im nächsten Schritt pro Quelle bessere
Adapter (RSS/API/News-Listing), sobald deren konkrete Feed-Struktur verifiziert ist.
