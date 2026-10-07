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
