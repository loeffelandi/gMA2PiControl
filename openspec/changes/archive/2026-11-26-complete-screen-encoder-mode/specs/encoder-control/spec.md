# Spec Delta

## ADDED Requirements

### Requirement: Auflösung im Screen-Modus

Im Screen-Modus MUST ein Encoder-Klick den Auflösungsframe auf den in
`mapping.screen_encoders` hinterlegten Namen des Slots beziehen. Ist für den
Slot kein Name konfiguriert, MUST kein Frame gesendet und eine Warnung
protokolliert werden; der Attribut-Name der aktuellen onPC-Page darf dabei
nicht verwendet werden.

#### Scenario: Auflösung mit Screen-Encoder-Namen

- **WHEN** der Screen-Modus aktiv ist, Slot 2 auf `screen2` zeigt und Encoder 2 gedrückt wird
- **THEN** wird ein `encoder`-Frame mit `name: "screen2"` und der nächsten Auflösungsstufe gesendet

#### Scenario: Auflösung ohne Screen-Encoder-Namen

- **WHEN** der Screen-Modus aktiv ist und für den gedrückten Slot kein `screen_encoders`-Name konfiguriert ist
- **THEN** wird kein `encoder`-Frame gesendet und eine Warnung nennt den fehlenden Slot

#### Scenario: Auflösung im Attribut-Modus bleibt unverändert

- **WHEN** der Attribut-Modus aktiv ist und ein Encoder gedrückt wird
- **THEN** bezieht sich der Auflösungsframe weiterhin auf das Attribut der aktuellen Page

### Requirement: Standardzuordnung der Screen-Encoder

Die mitgelieferte Konfiguration SHALL die onPC-Screen-Encoder 5–8 in umgekehrter
Reihenfolge auf die physischen Slots 1–4 legen: Slot 1 → `"8"`, Slot 2 → `"7"`,
Slot 3 → `"6"`, Slot 4 → `"5"`.

#### Scenario: Standardbelegung im Screen-Modus

- **WHEN** der Daemon mit der mitgelieferten `config.toml` läuft und der Screen-Modus aktiv ist
- **THEN** sendet Slot 1 Frames an `"8"`, Slot 2 an `"7"`, Slot 3 an `"6"` und Slot 4 an `"5"`

#### Scenario: Anpassung im UI

- **WHEN** ein Screen-Encoder-Name im UI geändert wird
- **THEN** verwendet der Screen-Modus den geänderten Namen für diesen Slot

### Requirement: Temporärer Screen-Modus per MA

Solange die MA-Taste gehalten wird, MUST jeder Slot-Encoder die Screen-Encoder
aus `mapping.screen_encoders` adressieren, auch wenn der globale Screen-Modus
ausgeschaltet ist. Beim Loslassen MUST der nächste Detent wieder das
Attribut-Fenster adressieren; ein Moduswechsel zwischen zwei Detents MUST zwei
getrennte Frames erzeugen.

#### Scenario: MA + Encoder

- **WHEN** MA gehalten und Slot 1 um einen Detent gedreht wird
- **THEN** wird ein `encoder`-Frame mit dem Screen-Encoder-Namen für Slot 1 (Standard `"8"`) gesendet

#### Scenario: Loslassen

- **WHEN** MA losgelassen und Slot 1 erneut gedreht wird
- **THEN** folgt der Frame wieder dem Attribut der onPC-Page

#### Scenario: Wechsel zwischen Detents

- **WHEN** ein Attribut-Detent aussteht und MA vor dem nächsten Detent gedrückt wird
- **THEN** werden Attribut- und Screen-Delta als getrennte Frames gesendet

### Requirement: NIPPLE-Hardkey auf der rechten ASL-Taste

Die mitgelieferte Konfiguration SHALL die rechte ASL-Taste (`asl_button_3`,
Note 11) auf den Hardkey `NIPPLE` legen. Der Daemon MUST dafür keinen eigenen
Modus auswerten, sondern den Hardkey wie jede andere Taste senden.

#### Scenario: Rechte ASL-Taste drücken

- **WHEN** die rechte ASL-Taste gedrückt und wieder losgelassen wird
- **THEN** sendet der Daemon einen `NIPPLE`-Press und einen `NIPPLE`-Release an die onPC
