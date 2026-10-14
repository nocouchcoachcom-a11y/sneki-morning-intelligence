# Mehr Themen und mehr Tiefe: redaktioneller Pilot

Stand: 7. Oktober 2026. Ein zusätzlicher API-Aufruf wurde mit höchstens 0,03 US-Dollar Modellkosten freigegeben und durchgeführt. Die Ausgabe scheiterte danach an der Statusvalidierung; kein weiterer API-Aufruf erfolgte. Der genaue Verbrauch wurde beim fehlgeschlagenen Lauf nicht gespeichert.

Die drei Beiträge wurden anschließend im Chat anhand der geprüften Originalquellen redaktionell ausgearbeitet und auf der privaten Website als Testausgabe bereitgestellt. Die regelmäßige Pipeline ist nicht um neue KI-Aufrufe erweitert. Die automatische redaktionelle Aufbereitung ist damit weiterhin nicht abgenommen.

Die bisherigen fünf Zusammenfassungen haben nur 8 bis 20 Wörter. Der Sitemap-Collector bevorzugt Metabeschreibungen; der semantischen Bewertung fehlen damit Details aus den Artikeln. Neue Rangfolgen allein können dieses Problem nicht beheben.

## Reviewbarer Testumfang

Ein zusätzlicher KI-Aufruf für drei öffentlich zugängliche Originalartikel, vorbereitet mit prepare_editorial_pilot.py. Das Skript selbst ruft keine KI-API auf. Die Ausgabe umfasst pro Artikel 100 bis 160 Wörter Zusammenfassung sowie Bedeutung, einen als Vorschlag gekennzeichneten Praxisfall, einen nächsten Prüfschritt und offene Grenzen. Belegtes und redaktionelle Ableitung werden getrennt. Bei unzureichendem Eingangstext wird nicht künstlich verlängert.

Artikel: OpenAI/Atlassian-Partnerschaft vom 6. Oktober, Anthropic Frontier Academy vom 2. Oktober, GPM zu KI im Konfliktmanagement vom 30. September. Herstellertexte sind Herstellerangaben, keine unabhängigen Leistungsnachweise. Veröffentlichungsdaten bleiben sichtbar; der ältere GPM-Beitrag wird nicht als neue Nachricht ausgegeben.

Der Request verwendet das bestehende Modell gpt-5.6-luna mit reasoning=low, maximal 6.000 Ausgabetokens, maximal 60.000 UTF-8-Bytes im vorbereiteten Request und ohne kostenpflichtige Recherchetools. Kein automatischer Wiederholungsaufruf. Der einmalig freigegebene Aufruf ist verbraucht; jede weitere Durchführung erfordert eine neue Freigabe. Der einmalige Pilot aktiviert keine zusätzlichen wiederkehrenden API-Aufrufe.

## Themenbreite nach erfolgreichem Pilot

OpenAI News und der Google-AI-Blog besitzen öffentlich erreichbare RSS-Feeds; beide wurden am 7. Oktober technisch geprüft. Anthropic hat einen offiziellen Newsroom; ein eigener Collector ist noch vorzubereiten. Die neuen Herstellerquellen ergänzen Fachverbände, BSI, ENISA und regulatorische Quellen. Sie erhalten eine sichtbare Herstellerkennzeichnung.

Offizielle Quellen:

- https://openai.com/news/rss.xml
- https://blog.google/innovation-and-ai/technology/ai/rss/
- https://www.anthropic.com/news

## Zielbild

Aktuelle KI-Werkzeuge und Anwendungen, KI-/PM-Praxis sowie Regulierung und Sicherheit bilden die Themenbreite. Ausgewählte Beiträge erhalten aussagekräftige Artikelkontexte statt Metabeschreibungen. Auf der Website steht eine lesbare Zusammenfassung mit konkret benanntem Nutzen; Praxisfall und Grenzen sind zusätzlich aufklappbar. Mehr Wörter oder eine feste Meldungszahl sind keine Qualitätsgarantie.

Der Pilot wird zuerst auf faktische Bindung, Kennzeichnung von Herstellerangaben, Trennung von Ableitung und Beleg sowie praktischen Nutzen geprüft. Erst danach wird die automatisierte Aufbereitung erweitert. Die bestehende private Website und reguläre Pipeline werden durch diesen Entwurf nicht verändert.
