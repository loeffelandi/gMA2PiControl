# Spec Delta

## MODIFIED Requirements

### Requirement: Auflösung per Taste 2 und Encoder-Klick

Solange `asl_button_2` gehalten wird, SHALL ein Encoder-Klick die Auflösung des
aktuellen Attributs des Slots in der onPC per nativem `encoder`-Frame zyklisch
umschalten (Normal → Fine → Ultra → Normal), ohne selbst Deltas zu skalieren.
Vor der Umschaltung MUST der Client bedarfsweise `presetTypes` aktualisieren,
bei Disconnect den Seitenstand leeren und bei `"update"`-Frames alte `"s"`-Flags
auf Geschwistern zurücksetzen; für Screen-Encoder MUST nichts gesendet werden.

#### Scenario: Auflösung durchschalten

- **WHEN** `asl_button_2` gehalten und Encoder 1 dreimal geklickt wird
- **THEN** werden nacheinander `resolution` 1, 2 und 0 für das Attribut von Slot 1 gesendet, und kein Klick erzeugt einen Encoder-Druck-Frame

#### Scenario: Fine skaliert

- **WHEN** die onPC Fine für das Attribut meldet und der Slot gedreht wird
- **THEN** ändert sich der Wert pro Schritt entsprechend kleiner, ohne dass der Daemon die Schritte skaliert

#### Scenario: Klick ohne Taste 2

- **WHEN** `asl_button_2` nicht gehalten wird und ein Encoder geklickt wird
- **THEN** wird der Encoder-Druck an die onPC gesendet und die Auflösung ändert sich nicht

#### Scenario: Feature-Wechsel in onPC vor Auflösungs-Umschaltung

- **WHEN** der Bediener in der onPC von Dimmer auf Position wechselt und danach
  `asl_button_2` hält und Encoder 1 klickt
- **THEN** aktualisiert der Client einmalig `presetTypes` und schaltet `PAN`
  statt des veralteten `DIM` um

## ADDED Requirements

### Requirement: Konsistente Tasten-LEDs bei Moduswechsel und Aufräumen

`ToggleScreenMode` SHALL nur die Modus-LED aktualisieren und MUST gehaltene
`NIPPLE`- oder `Fine`-LEDs nicht zurücksetzen. Beim Aufräumen gehaltener Tasten
durch Geräteverlust, Verbindungsverlust oder Apply MUST auch die LED-Anzeigen
gehaltener lokaler Modifier und der `NIPPLE`-Taste in den Ruhezustand wechseln.

#### Scenario: Modus-Toggle während gehaltener Fine-Taste

- **WHEN** `asl_button_2` gehalten wird und der Screen-Modus umgeschaltet wird
- **THEN** wechselt die Modus-LED die Farbe und die `Fine`-LED bleibt hell
