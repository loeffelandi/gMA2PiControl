# Spec Delta

## ADDED Requirements

### Requirement: LED der Fine-Taste

Die mittlere ASL-Taste (Note 10) SHALL im Ruhezustand gedimmt (Farbindex 123,
Helligkeit 25) und solange sie als Fine-Modifier gehalten wird hell
(Helligkeit 127) leuchten. Farbe und Helligkeiten MUST in `[led]` konfigurierbar sein.

#### Scenario: Ruhezustand

- **WHEN** die LED-Ausgabe geöffnet ist
- **THEN** leuchtet die mittlere ASL-Taste mit Ruhefarbe und Ruhehelligkeit

#### Scenario: Taste gehalten

- **WHEN** die mittlere ASL-Taste gedrückt wird
- **THEN** wechselt ihre LED auf die helle Stufe

#### Scenario: Taste losgelassen

- **WHEN** die mittlere ASL-Taste losgelassen wird
- **THEN** kehrt die LED auf die gedimmte Stufe zurück
