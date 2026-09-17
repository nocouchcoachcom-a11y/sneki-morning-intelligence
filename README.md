# sneKI Morning Intelligence

## Zweck

sneKI Morning Intelligence erstellt aus ausgewählten öffentlichen Primärquellen
ein kompaktes Management-Briefing zu KI, Regulierung, Datenschutz, Security und
Projektverantwortung. Ziel sind wenige nachvollziehbare Meldungen mit
Originalquelle – nicht möglichst viel News-Content.

## Architektur

```text
Primärquellen
→ Python Collector
→ data/raw-items.json
→ deterministische Filter
→ Hybrid C / GPT-5.6 Luna
→ deterministisches Ranking
→ SNE Q-LOOP / Validierung
→ data/morning-intelligence.json
→ GitHub Pages
→ bestehendes Dashboard
```

Die Aufgaben bleiben bewusst getrennt:

- Der Collector lädt, normalisiert und dedupliziert Quelldaten und dokumentiert
  den Status jeder Quelle.
- Deterministische Regeln entscheiden über Zulässigkeit, Datum, Datenqualität,
  Publishability, Diversität und Tie-Breaker.
- Hybrid C bewertet ausschließlich die semantische Management-Relevanz der
  bereits zulässigen Kandidaten.
- Der Validator prüft die erzeugten JSON-Dateien, bevor Daten committed werden.

Die KI entscheidet damit niemals über Quellenstatus, Datenvertrag,
Deduplizierung oder die technische Veröffentlichung.

## Ranking-Modi

Der Betriebsmodus wird über `SNEKI_RANKING_MODE` gewählt:

- `baseline` ist der sichere Standard für lokale Starts und verwendet nur
  deterministische Regeln.
- `hybrid` ergänzt die semantische Bewertung mit `gpt-5.6-luna` und verwendet
  anschließend wieder das deterministische Ranking.

Der GitHub-Workflow setzt den Builder gezielt auf `hybrid`. Scheitert Hybrid C
wegen eines fehlenden API-Keys, eines Netzwerk-/API-Fehlers oder einer ungültigen
Modellantwort, wird sichtbar auf die Baseline zurückgefallen:

```text
hybrid → baseline_fallback
```

Ein einzelner Quellenausfall verhindert ein LIVE-Briefing nicht, solange
verwertbare Meldungen und mindestens eine brauchbare Kernquelle vorhanden sind.
Ein objektiv unbrauchbarer Gesamtlauf wird dagegen nicht veröffentlicht.

## Semantik-Cache

`data/semantic-cache.json` speichert bereits geprüfte semantische Bewertungen.
Der Cache-Key berücksichtigt Inhalt, Modell, Reasoning-, Prompt- und
Schema-Version, aber nicht die Item-ID.

- unveränderter Inhalt → Cache-Hit, kein API-Aufruf
- neuer oder veränderter Inhalt → Cache-Miss
- mehrere Misses → genau ein gemeinsamer LLM-Batch
- vollständiger Cache → kein LLM-Aufruf

Der Cache wird getrennt von den Rohdaten geführt und darf keine Secrets
enthalten.

## Automatisierung mit GitHub Actions

Der Workflow läuft stündlich bei Minute 07. Python entscheidet in der Zeitzone
`Europe/Berlin`, ob um 07 Uhr eine Morning Edition oder um 15 Uhr ein Afternoon
Update erzeugt wird. So bleibt die Zeitlogik unabhängig von Sommer- und
Winterzeit.

Reihenfolge:

1. Repository `main` vollständig auschecken
2. Abhängigkeiten installieren und Offline-Tests ausführen
3. Quellen sammeln
4. Briefing im Hybrid-Modus bauen
5. neue oder veränderte Ausgaben validieren
6. vollständige Offline-Test-Suite erneut ausführen
7. erst danach geänderte Daten committen und pushen

Ein Parallelitätsschutz verhindert gleichzeitig laufende Jobs und damit
konkurrierende Cache-Änderungen oder doppelte API-Kosten.

## Secrets und Sicherheit

`OPENAI_API_KEY` wird ausschließlich als GitHub Repository Secret oder lokale
Umgebungsvariable bereitgestellt. Der Schlüssel gehört niemals in Code,
JSON-Dateien, Logs oder Commits. Im Workflow erhält nur der Builder-Schritt das
Secret; Collector, Tests und Validator erhalten es nicht.

Die Pipeline verwendet öffentliche Originalquellen. KI-Ausgaben ersetzen weder
die Originalquelle noch eine rechtliche oder fachliche Prüfung.

## Tests und Validierung

Die vollständige Offline-Suite umfasst aktuell **83 Tests**:

```bash
python -m unittest discover -s tests -v
```

Die vorhandenen Daten können separat geprüft werden:

```bash
python scripts/validate_outputs.py
```

Bei einem Nicht-Editionslauf darf ein nachweislich unverändertes älteres
Briefing migrationssicher übersprungen werden. Raw-Daten und Semantik-Cache
werden trotzdem geprüft:

```bash
python scripts/validate_outputs.py --skip-briefing
```

Der GitHub-Workflow verwendet diese Option nur, wenn Git bestätigt, dass
`data/morning-intelligence.json` in diesem Lauf unverändert blieb. Jede neue
oder veränderte Ausgabe wird streng geprüft; dabei ist `ranking` Pflicht.

## Daten und GitHub Pages

- aktueller Rohbestand: `data/raw-items.json`
- aktuelle Ausgabe: `data/morning-intelligence.json`
- Semantik-Cache: `data/semantic-cache.json`
- Archiv: `data/archive/YYYY-MM-DD/morning.json` beziehungsweise
  `afternoon.json`

Die aktuelle JSON-Ausgabe kann über GitHub Pages bereitgestellt und vom
bestehenden Dashboard als externe Datenquelle gelesen werden. Das Frontend
behält seinen Demo-Fallback, falls keine Live-Datei erreichbar ist.

## Bekannte Grenzen

- EDPB und DSK liefern derzeit teilweise nur schwache Startseiteninformationen;
  quellspezifische Einzelmeldungsadapter bleiben offen.
- PMI kann mit HTTP 403 ausfallen; dieser Fehler wird isoliert angezeigt.
- Hybrid C verbessert die Auswahl, erzeugt aber noch keinen allgemeinen
  Qualitätsnachweis. Der bisherige Referenztest umfasst nur 11 Fälle.
- Zusammenfassung und Relevanztexte im Briefing sind noch bewusst einfach; die
  KI wird aktuell nur als optionale semantische Ranking-Schicht eingesetzt.
- Reddit und X gehören nicht zum Kern-MVP.
- Rankinggewichte und Cache-Versionen dürfen nur kontrolliert und mit erneuten
  Offline-Tests geändert werden.
