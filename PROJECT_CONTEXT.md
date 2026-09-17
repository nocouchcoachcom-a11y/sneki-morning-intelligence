# sneKI Morning Intelligence · Projektkontext

## Projektziel und Business-Nutzen

sneKI Morning Intelligence verdichtet öffentliche Primärquellen zu einem
kurzen, nachvollziehbaren Management-Briefing. Verantwortliche sollen relevante
Entwicklungen schneller erkennen, Originalquellen direkt prüfen und daraus
Prüf-, Entscheidungs- oder Beobachtungsbedarf ableiten können.

Das Ziel ist eine kleine professionelle Lösung: wenige belastbare Meldungen,
klare Herkunft, kontrollierte Kosten und ein nachvollziehbarer Fehlerpfad.

## Zielgruppe

- Geschäftsführerinnen und Geschäftsführer
- KI- und Governance-Verantwortliche
- IT- und Security-Verantwortliche
- Projekt- und Transformationsverantwortliche

## Aktuelle Architektur

```text
Primärquellen
→ Python Collector
→ raw-items.json
→ deterministische Zulässigkeitsfilter
→ optionale Hybrid-C-Semantik
→ deterministische Bewertung und Diversität
→ SNE Q-LOOP / Output-Validierung
→ morning-intelligence.json
→ GitHub Pages
→ bestehendes Dashboard
```

GitHub Actions automatisiert Sammlung, Builder, Validierung, Tests und das
Speichern erfolgreicher Datenänderungen. Gleichzeitige Läufe werden verhindert.

## Deterministisch versus KI

Deterministisch bleiben:

- Quellenstatus und Fehlerisolation
- Zulässigkeit einer Meldung
- Veröffentlichungsdatum und Fallback auf `first_seen_at`
- Datenqualität und Datenvertrag
- Deduplizierung
- Publishability
- Quellen- und Kategorien-Diversität
- Tie-Breaker, Validierung und Fehlerpfad

Die KI übernimmt nur die verbleibende semantische Frage: Wie relevant ist eine
Meldung für Geschäftsführung sowie KI-, IT- und Projektverantwortliche?

## Hybrid C

Hybrid C verwendet `gpt-5.6-luna` mit `reasoning_effort=low`. Bewertet werden
Management-Relevanz, Handlungsnähe und fachliche Bedeutung mit jeweils 0 bis 3
Punkten. Die strukturierte Antwort wird streng validiert und auf eine
Semantikkomponente von 0 bis 2 normalisiert.

Bei unzureichendem Inhalt muss das Modell `insufficient_input` liefern und alle
drei Scores auf 0 setzen. Solche Einträge sind im Hybrid-Ranking nicht rankbar.
Ground Truth und menschliche Referenzwerte gelangen niemals in den Modellprompt.

## Baseline und Fehlerpfad

`SNEKI_RANKING_MODE=baseline` verwendet ausschließlich die deterministische
Baseline. `SNEKI_RANKING_MODE=hybrid` aktiviert Hybrid C.

Fehlt der API-Key oder scheitern Netzwerk, API, JSON-Verarbeitung,
Schema-Validierung oder Item-Zuordnung, wird der Fehler sichtbar protokolliert
und das Briefing mit der Baseline weitergeführt:

```text
hybrid → baseline_fallback
```

Es gibt keine automatischen API-Retries.

## Semantik-Cache

Der persistente Cache liegt getrennt von den Rohdaten unter
`data/semantic-cache.json`. Sein SHA-256-Key wird aus Titel, Rohtext, Quelle,
Kategorie, Modell, Reasoning-, Prompt- und Schema-Version erzeugt. Die Item-ID
gehört nicht zum Key.

- identischer semantischer Inhalt → vorhandene Bewertung wiederverwenden
- neuer oder geänderter Inhalt → neu bewerten
- alle Misses eines Laufs → ein gemeinsamer Batch
- vollständiger Cache → kein API-Aufruf

Neue Einträge werden nur nach einer vollständig erfolgreichen Bewertung atomar
gespeichert. Ein Fehler beschädigt bestehende Cache-Einträge nicht.

## Kostenkontrolle

Pro Hybrid-Lauf werden Cache-Hits, Cache-Misses, bewertete API-Items, Modell,
Tokenverbrauch und geschätzte Kosten protokolliert. Ein vollständiger echter
11-Item-Testlauf kostete in den bisherigen Messungen ungefähr
**0,0015–0,0018 USD**. Cache-Hits verursachen keinen neuen Modellaufruf.

Diese Größenordnung ist eine Momentaufnahme und keine Preisgarantie.

## Security und Datenschutz

- `OPENAI_API_KEY` ausschließlich als Umgebungsvariable beziehungsweise GitHub
  Repository Secret
- Secret nur im Builder-Schritt verfügbar
- keine Secrets in Code, Cache, Daten, Logs oder Commits
- nur die fünf erlaubten Meldungsfelder werden an das Modell übertragen
- Eingabetext wird ausdrücklich als Dateninhalt und nicht als Anweisung behandelt
- keine Rechtsberatung und keine Ergänzung fehlender Fakten oder Fristen
- Originalquellen und KI-Bewertungen bleiben getrennt

## Qualität und aktueller Teststand

Der aktuelle Stand besitzt **83 von 83 erfolgreiche Offline-Tests**. Geprüft
werden unter anderem Datenvertrag, Aktualität, Publishability, Quellenausfälle,
Baseline-Ranking, Hybrid-Fallback, Cache, Secret-Schutz, Fehlerdiagnosen,
Workflow-Struktur und Output-Validierung.

Neu oder verändert erzeugte Briefings müssen das vollständige Schema inklusive
`ranking` erfüllen. Ein unverändertes Legacy-Briefing darf in einem
Nicht-Editionslauf übersprungen werden; Raw-Daten und Cache bleiben trotzdem
prüfpflichtig.

## Gemessener MVP-Nachweis

Auf dem eingefrorenen menschlich bewerteten Snapshot wurden gemessen:

| Vergleich | Ergebnis |
|---|---:|
| Baseline B ↔ Human Top 5 | 60 % |
| Hybrid C ↔ Human Top 5 | 100 % |
| Semantik-MAE Baseline B | 0,6167 |
| Semantik-MAE Hybrid C | 0,1967 |
| Verbesserung | 68,11 % |

**Wichtige Grenze:** Diese Werte stammen aus einem kleinen Snapshot mit nur
11 Fällen. Sie belegen die technische und fachliche Machbarkeit des MVP, sind
aber **kein allgemeiner Qualitätsnachweis** für andere Themen, Quellen oder
zukünftige Meldungen.

## Bekannte offene Punkte

- EDPB- und DSK-Startseiten durch belastbarere Einzelmeldungsadapter verbessern
- PMI-Zugriff mit HTTP 403 weiter als sichtbaren Quellenausfall behandeln
- tatsächliche Datenübernahme im bestehenden Dashboard produktiv verifizieren
- einfache Zusammenfassungs- und Relevanztexte später getrennt bewerten
- Rankinggewichte erst mit einem größeren Referenzdatensatz erneut prüfen
- Betriebsmonitoring und Langzeitbeobachtung der Quellenqualität ausbauen
- Reddit und X bewusst außerhalb des Kern-MVP belassen

## IHK- und Kursrelevanz

Das Projekt zeigt eine nachvollziehbare Architekturentscheidung statt unnötiger
Komplexität: deterministische Regeln sichern Daten und Betrieb, KI wird nur für
die semantische Aufgabe eingesetzt. Messbarer Business-Nutzen, Kostenkontrolle,
Security, Fehlerbehandlung, Tests, Cache-Strategie und dokumentierte Grenzen
machen die Lösung fachlich erklärbar und prüfbar.
