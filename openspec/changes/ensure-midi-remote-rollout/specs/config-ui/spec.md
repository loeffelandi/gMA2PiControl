# Spec Delta

## ADDED Requirements

### Requirement: Remotes ausrollen auf der Statusseite

Die Statusseite SHALL bei aktiven MIDI-Remotes den letzten Abgleich zeigen und
einen Knopf „Remotes ausrollen“ anbieten, solange `sync` nicht `"off"` ist.
Der Knopf MUST `POST /api/midi-remote/sync` auslösen und während eines
laufenden Abgleichs deaktiviert sein. Fehlen nach einem Lauf Ziele, MUST die
Seite das als Fehlerzustand zeigen.

#### Scenario: Knopf stößt den Abgleich an

- **WHEN** MIDI-Remotes aktiv sind und auf der Statusseite „Remotes ausrollen“
  gewählt wird
- **THEN** stößt die Oberfläche `POST /api/midi-remote/sync` an und der
  Abgleich-Status wechselt auf laufend

#### Scenario: Unvollständig sichtbar

- **WHEN** der letzte Abgleich in `auto` nicht alle Ziele bestätigt hat
- **THEN** zeigt die Statusseite die Anzahl fehlender Einträge und dass der
  Knopf „Remotes ausrollen“ den Abgleich wiederholt

#### Scenario: Kein Knopf bei abgeschaltetem Abgleich

- **WHEN** `sync = "off"` gilt
- **THEN** erscheint der Knopf „Remotes ausrollen“ nicht
