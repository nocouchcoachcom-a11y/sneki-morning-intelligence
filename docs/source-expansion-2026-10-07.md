# KI-/PM-Quellen erweitern · 7. Oktober 2026

## Änderung
- heise Atom-Feed mit KI-Themenfilter: maximal acht Kandidaten, sieben Tage Aktualitätsfenster, verification secondary. Keine Volltextübernahme.
- APM: zwei aktuelle Artikelübersichten priorisieren, Sitemap zusätzlich; jeweils verbleibende Methode nutzen, wenn die andere beim Abruf ausfällt. Datum weiterhin ausschließlich aus dem Originalartikel.
- APM/GPM: maximal 20 Artikel statt sechs prüfen, maximal zehn Treffer statt fünf; Themen um Steuerung, Zusammenarbeit, Stakeholder und Nutzen ergänzt.
- Website-Source-Matrix vor Collector-Aktivierung aktualisiert und privat bereitgestellt; heise als redaktionelle Sekundärquelle.

## Nachweise
- heise https://www.heise.de/rss/heise-atom.xml: HTTP 200, 156 Einträge beim ersten Test; vollständiger Adapter-Test liefert acht passende Meldungen, darunter ReviewBench, Anthropic-Cyberprogramme und lokale KI/Ollama vom 7. Oktober.
- GPM: zehn Treffer im erweiterten Abruf; darunter ein CAPEX-Projektportfolio-Beitrag vom 6. Oktober. Mehrere einzelne Originalartikel liefen in einen Timeout und wurden übersprungen.
- APM: erster erweiterter Live-Test durch Sitemap-Timeout abgebrochen. Deshalb Fehlerpfad verbessert: bei Sitemap-Ausfall die Artikelübersichten trotzdem prüfen. Dieser Fehlerpfad offline nachgewiesen; erfolgreicher kompletter APM-Live-Abruf noch offen.
- 164 Produktionstests bestanden; fünf zusätzliche lokale Tests des inaktiven X-Prototyps ebenfalls bestanden. Regression für Reihenfolge, Duplikate, fremde Hosts, Artikeldaten, Sekundärquellenrolle und Sitemap-Timeout.

## Kosten und Grenzen
Keine zusätzlichen Modellläufe oder Editionszeiten. Zusätzliche Kandidaten erhöhen gegebenenfalls die Eingabemenge des vorhandenen Batches; freigegebene Budgets und bestehende Kostenprüfungen bleiben erhalten. Öffentliche Artikelabrufe nehmen zu. Keine Vollständigkeitsgarantie. Sekundärberichte sind keine unabhängig bestätigten Fakten; Originalquellen für wichtige Aussagen prüfen. Die nächste reguläre Ausgabe muss noch Ende-zu-Ende geprüft werden.

SNE Q-LOOP: REVISE für die Gesamtintegration bis zum nachgewiesenen regulären Editionslauf und einem erfolgreichen vollständigen APM-Abruf. heise-/GPM-Entdeckung und Offline-Verhalten sind nachgewiesen.

## Nachprüfung 07.10.2026, 12:26 Uhr (Berlin)
- Erweiterten APM-Adapter separat mit aktueller Konfiguration ausgeführt: 10 Treffer in 130,6 Sekunden. Ein Originalartikel nach 10-Sekunden-Timeout übersprungen; übriger Abruf erfolgreich.
- Neueste gefundene Veröffentlichung: 06.10.2026, „Meet the rocket builders: The people behind propulsion“. Datum ohne Uhrzeit; nicht als 24-Stunden-Tagesnews vom 07.10. ausgeben. Ebenfalls gefunden: „The revolution starts here: How launch is changing?“ (05.10.) und „Project management lessons from The Odyssey“ (01.10.).
- APM-Adapter-Live-Prüfung damit bestanden. Kein neuer Modellaufruf, kein Schreiben in Rohdaten oder Ausgabe durch diesen Test.
- GitHub-Abfrage: letzte gespeicherte Sammlung 11:27:20 Uhr, vor dieser Quellenerweiterung; letzter bestätigter regulärer Collector-Lauf 37600634770 erfolgreich. Die gespeicherte Ausgabe bleibt 09:37:16 Uhr. Deshalb weiterhin kein bestätigter regulärer Lauf der Erweiterung und keine aktuelle Website-Endabnahme.
- Gesamtintegration weiterhin REVISE. Nächste reguläre Sammlung und Nachmittagsausgabe getrennt prüfen; Zeitplan ist kein Beleg eines erfolgreichen Laufs.

## IHK-Arbeitsstand und bestätigte Motivation
- Onepager und zehn Folien Version 11 als Arbeitsstand erstellt. Informationswert und Inhaltsprüfung ergänzt, echter automatisch angereicherter GPM-Beitrag als Workflow-Beispiel, Nachweise im gemeinsamen PDF sichtbar, Governance-Gewichtung begründet, Kurzprüfung vor Abgabe vom späteren Zehntage-Pilot getrennt.
- Steffen bestätigt als Motivation: praktische KI-Kompetenz aufbauen und die berufliche Ausrichtung um KI-Transformation/Beratung erweitern (Antwort „Beides verbinden“). Diese persönliche Formulierung in die nächste Endfassung übernehmen.
- Offene Abgabe-Nachweise: aktuelle Website-Ausgabe und Screenshot, Terminstatus, bestätigte persönliche Angaben. Zeit-/ROI-Werte weiterhin ausdrücklich Szenario; keine tatsächlich gemessenen Einsparungen.

## Reguläre Sammlung bestätigt: 12:26:58 Uhr
Während der Nachprüfung erfolgte die nächste reguläre Sammlung. Commit 379f03c34288614e49597cfe2e9eecf7a394a5f8 speichert APM 10, GPM 10 und heise 8 Treffer, jeweils Quellenstatus ok. PMI weiterhin HTTP403. Damit ist auch die erweiterte reguläre Sammlung nachgewiesen. Dies erzeugt außerhalb der Editionszeiten keine neue KI-Ausgabe: Ausgabe weiterhin 09:37:16 Uhr. Gesamtintegration der Nachmittagsausgabe und aktuelle Website-Endabnahme bleiben offen.
