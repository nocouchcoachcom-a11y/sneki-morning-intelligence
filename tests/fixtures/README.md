# Semantischer Referenzdatensatz

`semantic_reference.json` ist der eingefrorene menschliche Referenzdatensatz
für den späteren Vergleich von Baseline B und Hybrid C.

Der Snapshot wurde aus `data/raw-items.json` gebildet. Enthalten sind alle
zum Snapshot-Zeitpunkt zulässigen Kandidaten: Das Item besitzt den Status
`ok`, ist keine Social-Quelle und seine Quelle hat aktuell den Status `ok`
oder `degraded`.

Die Felder `expected_management_relevance`, `expected_actionability`,
`expected_significance`, `expected_assessment_status` und `reference_note`
sind absichtlich `null`. Sie werden erst durch eine menschliche fachliche
Bewertung befüllt. Ein LLM darf diese Referenzwerte nicht erzeugen oder
verändern.

Der Datensatz soll für einen reproduzierbaren B-vs-C-Vergleich unverändert
bleiben. Neue Snapshots werden als neue Fixture angelegt und ersetzen diesen
Referenzstand nicht stillschweigend.
