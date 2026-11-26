# Spec Delta

## MODIFIED Requirements

### Requirement: Geräte- und Mapping-Editor

Die Oberfläche SHALL erkannte Geräte und deren logische Controls anzeigen und
das Bearbeiten von Tasten-, Modifier- und Encoder-Mappings ermöglichen. Pro
physischem Encoder MUST zusätzlich das Attribut-Ziel und der Screen-Encoder
als Nummer (5–10 oder „keiner“) wählbar sein. Vor dem Speichern MUST die
Konfiguration mit denselben Regeln wie der Daemon validiert werden; ungültige
Ziele werden mit Feldbezug abgelehnt.

#### Scenario: Erkannte Geräte werden angezeigt

- **WHEN** die Mapping-Seite geöffnet wird
- **THEN** erscheinen beide konfigurierten Geräte mit Name, Vendor-/Product-ID und ihren verfügbaren Controls

#### Scenario: Taste einer Aktion zuweisen

- **WHEN** eine Taste im Learn-Modus erfasst und einer Hardkey- oder CMD-Aktion zugewiesen wird
- **THEN** erscheint die Zuordnung in der Tabelle und die Validierung meldet keinen Fehler

#### Scenario: Ungültiges Encoder-Ziel

- **WHEN** ein Encoder auf Wheel 11 oder auf ein unbekanntes Attribut gesetzt wird
- **THEN** lehnt die API das Speichern mit einer Feldmeldung ab und die aktive Konfiguration bleibt unverändert

#### Scenario: Screen-Encoder-Namen bearbeiten

- **WHEN** im Mapping-Editor pro physischem Encoder ein Screen-Encoder (Nummer 5–10) ausgewählt und gespeichert wird
- **THEN** enthält `mapping.screen_encoders` für den zugeordneten Slot genau diese Nummer und der Screen-Modus adressiert den entsprechenden Hardware-Encoder

#### Scenario: Screen-Encoder-Slot leeren

- **WHEN** für einen physischen Encoder `— keiner —` gewählt und gespeichert wird
- **THEN** fehlt der zugeordnete Slot in `mapping.screen_encoders` und im Screen-Modus sendet dieser Slot keine Frames