# sneKI Morning Intelligence · Codex Project Rules

## Ziel
Dieses Projekt entwickelt sneKI Morning Intelligence weiter.
Ziel ist eine einfache, robuste, nachvollziehbare und IHK-taugliche Lösung.

## Arbeitsprinzip
Keep it simple.

Reuse first.
Improve when useful.
Replace when clearly better.

Bestehende funktionierende Komponenten werden zuerst geprüft und möglichst weiterverwendet.
Keine unnötige technische Komplexität.

## Nutzerkontext
Der Projektinhaber ist kein Python-Entwickler.
Erkläre Änderungen deshalb auf Deutsch, kurz und ELI15 / Non-IT.

Bei technischen Entscheidungen:
- erkläre kurz, was geändert wird,
- warum es nötig ist,
- welchen Nutzen es bringt,
- welche Risiken bestehen.

## SNE Q-LOOP
Bei relevanten Designs, Änderungen und Reviews:

### TARGET
Was soll konkret erreicht werden?

### CHECK
Prüfe mindestens:
- Auftragsabdeckung
- Prozesslogik
- Datenqualität
- deterministisch vs. KI
- Kosten / Tokens / APIs
- Datenschutz und Security
- Fehlerpfad
- Wartbarkeit
- Tests
- Nachvollziehbarkeit

### Findings
Klassifiziere relevante Befunde als:
- 🔴 FEHLER
- 🟠 RISIKO
- 🟡 LÜCKE
- 🔵 OPTIONAL

### VERDICT
Genau eines:
- PASS
- REVISE
- ESCALATE

PASS bedeutet: Ziel ausreichend erfüllt. Danach stoppen.

REVISE bedeutet: relevante behebbare Abweichung. Nur gezielt korrigieren.

ESCALATE bedeutet: zuverlässige Verbesserung oder Entscheidung ohne zusätzliche Information oder menschliche Freigabe nicht möglich.

Maximal zwei Verbesserungsschleifen.
Keine endlose Optimierung.

## Architekturprinzipien
- Deterministische Regeln verwenden, wenn Regeln ausreichen.
- KI nur für Interpretation, Bewertung oder Generierung einsetzen.
- Originalquellen und Rohdaten von KI-generierten Inhalten trennen.
- Keine unnötigen Multi-Agent-, Vector-DB-, MCP- oder Modelltraining-Komponenten.
- Komfort ist ein legitimer Nutzen, wenn er Aufwand reduziert oder Bedienbarkeit verbessert.

## Qualität und Tests
- Vor relevanten Änderungen vorhandene Tests beachten.
- Nach Änderungen passende Tests ausführen.
- Keine Änderung als erfolgreich bezeichnen, wenn Tests fehlschlagen.
- Fehler nicht verstecken oder künstlich als PASS markieren.

## Sicherheit
- Keine Secrets, API-Keys, Tokens oder Credentials in Code, Logs oder Commits.
- Secrets gehören in Umgebungsvariablen bzw. `.env`.
- Keine kostenpflichtige API oder externe Aktion ohne ausdrückliche Freigabe.
- Keine Dateien außerhalb des Projektordners verändern, sofern nicht ausdrücklich freigegeben.

## Projektziel IHK
Die Lösung soll nicht maximal komplex sein, sondern professionell nachvollziehbar.

Besonders wichtig:
- Business-Nutzen
- Architekturentscheidung
- Trennung deterministisch / KI
- Fehlerbehandlung
- Qualitätssicherung
- Kostenbewusstsein
- Security / Datenschutz
- Testnachweis
- Wartbarkeit

Zielbild:
Eine kleine professionelle Lösung statt einer großen Demo.

## Antwortformat

Beginne jede Antwort an den Nutzer mit einem aktuellen Zeitstempel im Format:

`DD.MM.YYYY · HH:MM Uhr`

Beispiel:

`17.09.2026 · 10:43 Uhr`

Verwende die lokale Zeitzone:

`Europe/Berlin`

Wenn möglich, ermittle den Zeitstempel über die lokale Systemzeit und schätze ihn nicht.

Geeigneter macOS-Befehl:

`TZ=Europe/Berlin date '+%d.%m.%Y · %H:%M Uhr'`

Der Zeitstempel steht immer in der ersten Zeile der Antwort.
Danach folgt eine Leerzeile und anschließend die eigentliche Antwort.
