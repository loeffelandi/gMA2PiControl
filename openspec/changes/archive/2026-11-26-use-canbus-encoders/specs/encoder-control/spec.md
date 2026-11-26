# Spec Delta

## MODIFIED Requirements

### Requirement: Attribut-Fenster folgt der onPC

Die Slot-Encoder SHALL die Hardware-Attribut-Encoder der onPC adressieren; die
onPC routet diese selbst auf das aktuell gewählte Feature und Attribut-Fenster.
Der Daemon MUST dafür kein eigenes Seiten-Modell vorhalten und kein
`presetTypes`-Polling betreiben. Blättert der Benutzer in der onPC weiter,
folgen die Encoder unmittelbar, weil die onPC das Ziel selbst bestimmt.

#### Scenario: onPC blättert weiter

- **WHEN** der Benutzer in der onPC von den Attributen 1–4 auf die Attribute 5–8 wechselt
- **THEN** senden die vier Encoder weiterhin ihre Hardware-Encoder-Indizes und die onPC legt sie auf die Attribute 5–8

#### Scenario: Weniger Attribute als Slots

- **WHEN** das aktuelle Feature nur zwei Attribute hat
- **THEN** bleiben die Hardware-Encoder 3 und 4 an der onPC ohne Wirkung; der Daemon sendet ihre Indizes weiter und die onPC ignoriert sie

#### Scenario: Feature-Wechsel

- **WHEN** der Benutzer in der onPC ein anderes Feature wählt
- **THEN** adressieren die Encoder ohne Zutun des Daemons das Fenster des neuen Features; ein `presetTypes`-Polling findet nicht statt

### Requirement: Screen-Modus per Taste

Eine konfigurierte Taste SHALL zwischen Attribut- und Screen-Encodern
umschalten. Im Screen-Modus MUST jeder Slot auf die in
`mapping.screen_encoders` hinterlegte Screen-Encoder-Nummer (5–10) zeigen und
den entsprechenden Hardware-Encoder-Index (Nummer − 1) adressieren.

#### Scenario: Umschalten mit konfigurierten Screen-Encodern

- **WHEN** `mapping.screen_encoders` die Slots 1–4 belegt und die Taste gedrückt wird
- **THEN** senden die Encoder danach die Screen-Encoder-Indizes und der Status meldet `screen_mode: true`

#### Scenario: Umschalten ohne Konfiguration

- **WHEN** `mapping.screen_encoders` fehlt und die Taste gedrückt wird
- **THEN** wechselt der Modus, es werden aber keine Encoder-Frames gesendet und eine Warnung nennt die fehlende Konfiguration

#### Scenario: Zurück in den Attribut-Modus

- **WHEN** die Taste im Screen-Modus erneut gedrückt wird
- **THEN** adressieren die Encoder wieder die Hardware-Attribut-Encoder der onPC

### Requirement: Standardzuordnung der Screen-Encoder

Die mitgelieferte Konfiguration SHALL die onPC-Screen-Encoder 5–8 in umgekehrter
Reihenfolge auf die physischen Slots 1–4 legen: Slot 1 → `8`, Slot 2 → `7`,
Slot 3 → `6`, Slot 4 → `5`. `mapping.screen_encoders` MUST ausschließlich
Nummern im Bereich 5–10 akzeptieren; andere Werte MUST die Validierung
fehlschlagen lassen.

#### Scenario: Standardbelegung im Screen-Modus

- **WHEN** der Daemon mit der mitgelieferten `config.toml` läuft und der Screen-Modus aktiv ist
- **THEN** sendet Slot 1 den Index für Screen-Encoder 8, Slot 2 für 7, Slot 3 für 6 und Slot 4 für 5

#### Scenario: Ungültige Screen-Encoder-Nummer

- **WHEN** `mapping.screen_encoders` einen Wert außerhalb von 5–10 oder einen nicht-numerischen Wert enthält
- **THEN** bricht die Konfigurationsvalidierung mit einer Meldung ab, die den gültigen Bereich nennt

#### Scenario: Anpassung im UI

- **WHEN** eine Screen-Encoder-Nummer im UI geändert wird
- **THEN** verwendet der Screen-Modus die geänderte Nummer für diesen Slot

### Requirement: Temporärer Screen-Modus per MA

Solange die MA-Taste gehalten wird, MUST jeder Slot-Encoder die Screen-Encoder
aus `mapping.screen_encoders` adressieren, auch wenn der globale Screen-Modus
ausgeschaltet ist. Beim Loslassen MUST der nächste Detent wieder die
Hardware-Attribut-Encoder adressieren; ein Moduswechsel zwischen zwei Detents
MUST zwei getrennte Frames erzeugen.

#### Scenario: MA + Encoder

- **WHEN** MA gehalten und Slot 1 um einen Detent gedreht wird
- **THEN** wird ein canbus-Encoder-Frame mit dem Index für die Slot 1 zugeordnete Screen-Encoder-Nummer (Standard `8`) gesendet

#### Scenario: Loslassen

- **WHEN** MA losgelassen und Slot 1 erneut gedreht wird
- **THEN** adressiert der Frame wieder den Hardware-Attribut-Encoder der onPC

#### Scenario: Wechsel zwischen Detents

- **WHEN** ein Attribut-Detent aussteht und MA vor dem nächsten Detent gedrückt wird
- **THEN** werden Attribut- und Screen-Delta als getrennte Frames gesendet

## REMOVED Requirements

### Requirement: Auflösung per Encoder-Klick

**Reason:** Der Klick schaltet die Auflösung nicht mehr im Daemon, sondern ist
der echte Encoder-Druck der onPC (siehe „Encoder-Klick über canbus“). Es wird
kein eigener `resolution`-Frame mehr gesendet.

**Migration:** `encoder_fine`-Mappings werden durch `encoder_press`-Mappings
ersetzt; die Auflösung wird lokal per Taste 2 + Klick umgeschaltet (siehe
„Auflösung per Taste 2 und Encoder-Klick“).

### Requirement: Auflösung im Screen-Modus

**Reason:** Mit dem canbus-Transport entfällt der namensbasierte
Auflösungs-Frame vollständig; Screen-Encoder werden wie Hardware-Encoder
adressiert und nutzen die onPC-Auflösung.

**Migration:** Keine; Auflösungswechsel laufen über die onPC.

### Requirement: Nativer Encoder-Frame

**Reason:** Slot-Encoder nutzen nicht mehr den nativen
`{"requestType":"encoder"}`-Request, sondern canbus-Command-Frames. Der native
Request bleibt nur für feste Attribut-Encoder (`attribute`) erhalten.

**Migration:** Siehe neue Anforderung „Encoder-Transport über canbus“.

## ADDED Requirements

### Requirement: Encoder-Transport über canbus

Slot-Encoder SHALL ihre Deltas als Command-Frame
`LUA 'gma.canbus.encoder(<Index>, <Schritte>, nil)'` senden. Der Index ist die
Ziel-Nummer − 1: im Attribut-Modus Slot − 1 (0–3), im Screen-Modus die
konfigurierte Screen-Encoder-Nummer − 1 (4–9). Feste Attribut-Encoder
(`attribute`) SHALL weiterhin den nativen `encoder`-Request mit Namen nutzen.
Ist im Screen-Modus für einen Slot keine Nummer konfiguriert, MUST kein Frame
gesendet und eine Warnung protokolliert werden.

#### Scenario: Attribut-Delta

- **WHEN** im Attribut-Modus ein akkumulierter Delta für Slot 1 anliegt
- **THEN** wird genau ein Command-Frame `LUA 'gma.canbus.encoder(0, <Schritte>, nil)'` gesendet

#### Scenario: Screen-Delta

- **WHEN** im Screen-Modus Slot 2 auf Screen-Encoder 7 zeigt und ein Delta anliegt
- **THEN** wird genau ein Command-Frame `LUA 'gma.canbus.encoder(6, <Schritte>, nil)'` gesendet

#### Scenario: Screen-Modus ohne Nummer

- **WHEN** im Screen-Modus für einen Slot keine Screen-Encoder-Nummer konfiguriert ist
- **THEN** wird kein Frame gesendet und eine Warnung nennt den fehlenden Slot

#### Scenario: Festes Attribut bleibt nativ

- **WHEN** ein Encoder auf das feste Attribut `PAN` gemappt ist
- **THEN** wird weiterhin ein nativer `encoder`-Frame mit `name: "PAN"` gesendet

#### Scenario: Dry-Run

- **WHEN** der Daemon im Dry-Run läuft
- **THEN** werden die canbus-Encoder-Frames protokolliert, ohne dass eine Verbindung geöffnet wird

### Requirement: Ganzzahlige Schritte mit Rest-Vortrag

canbus-Encoder-Frames SHALL ganzzahlige Schritte senden. Der akkumulierte
Float-Delta eines Slots MUST ganzzahlig gesendet und der verbleibende Rest für
diesen Slot vorgetragen werden, sodass auch langsame Drehungen unter einem
vollen Schritt langfristig keinen Detent verlieren. Das Vorzeichen MUST
erhalten bleiben; ein Flush ohne ganzen Schritt MUST keinen Frame erzeugen.

#### Scenario: Langsame Drehung unter einem Schritt

- **WHEN** durch Beschleunigungskurve oder Auflösung ein Delta von weniger als einem ganzen Schritt aufläuft
- **THEN** wird zunächst kein Frame gesendet und der Rest bleibt erhalten, bis sich mindestens ein ganzer Schritt ergibt

#### Scenario: Rest wird vorgetragen

- **WHEN** mehrere Flushes jeweils einen Rest hinterlassen
- **THEN** summieren sich die Reste und ergeben schließlich einen ganzzahligen Frame, ohne dass Detents verloren gehen

#### Scenario: Vorzeichen bleibt erhalten

- **WHEN** gegen den Uhrzeigersinn gedreht wird
- **THEN** sind alle gesendeten Schritte negativ

### Requirement: Encoder-Klick über canbus

Ein Druck auf einen Slot-Encoder SHALL als Hardware-Encoder-Druck an die onPC
gesendet werden: `LUA 'gma.canbus.encoder(<Index>, 0, true)'` beim Drücken und
`LUA 'gma.canbus.encoder(<Index>, 0, false)'` beim Loslassen, mit dem Index des
Slots (Attribut-Modus Slot − 1, Screen-Modus bzw. MA gehalten die konfigurierte
Screen-Encoder-Nummer − 1). Der Release MUST denselben Index verwenden wie der
zugehörige Press, auch wenn sich der Modus dazwischen ändert. Die Zuordnung
geschieht per `encoder_press = <slot>` im Key-Mapping; `asl_click_1..4` sind
standardmäßig auf Slot 1–4 gelegt.

#### Scenario: Klick im Attribut-Modus

- **WHEN** Encoder 2 gedrückt und losgelassen wird
- **THEN** werden `gma.canbus.encoder(1, 0, true)` und danach `gma.canbus.encoder(1, 0, false)` gesendet

#### Scenario: Klick mit MA

- **WHEN** MA gehalten und Encoder 2 gedrückt wird
- **THEN** wird `gma.canbus.encoder(6, 0, true)` (Standard: Screen-Encoder 7) gesendet und der Release verwendet ebenfalls Index 6

#### Scenario: Release nach Moduswechsel

- **WHEN** Encoder 1 im Attribut-Modus gedrückt und MA vor dem Loslassen betätigt wird
- **THEN** sendet der Release weiterhin Index 0

### Requirement: Auflösung per Taste 2 und Encoder-Klick

Die mitgelieferte Konfiguration SHALL `asl_button_2` (Note 10) als lokalen
Modifier führen. Solange er gehalten wird, MUST ein Encoder-Klick die
Auflösung des Slots zyklisch umschalten (Normal → Fine → Ultra → Normal) und
keinen Encoder-Druck an die onPC senden. Die Auflösung MUST pro Slot gespeichert
bleiben und die Deltas dieses Slots mit `encoder_resolution.attribute`
(`normal`, `fine`, `ultra`) skalieren; Reste werden wie bei „Ganzzahlige
Schritte mit Rest-Vortrag“ vorgetragen. Eine Konfigurationsübernahme setzt alle
Slots auf Normal zurück.

#### Scenario: Auflösung durchschalten

- **WHEN** `asl_button_2` gehalten und Encoder 1 dreimal geklickt wird
- **THEN** gilt nacheinander Fine, Ultra und wieder Normal, und kein Klick erzeugt einen Encoder-Druck-Frame

#### Scenario: Fine skaliert

- **WHEN** Fine aktiv ist (Faktor 0,1) und der Slot um zehn Detents gedreht wird
- **THEN** ergibt sich ein einzelner Schritt

#### Scenario: Klick ohne Taste 2

- **WHEN** `asl_button_2` nicht gehalten wird und ein Encoder geklickt wird
- **THEN** wird der Encoder-Druck an die onPC gesendet und die Auflösung ändert sich nicht

### Requirement: NIPPLE-LED

Die rechte ASL-Taste (Note 11) SHALL standardmäßig leicht orange leuchten
(Farbindex 121, Helligkeit 25) und solange sie gedrückt wird heller
(Farbindex 116, Helligkeit 127). Farbe und Helligkeit MUST in `[led]`
konfigurierbar sein. Fehlt das MIDI-Gerät, MUST der Daemon normal weiterlaufen.

#### Scenario: Ruhezustand

- **WHEN** der Daemon die LED-Ausgabe geöffnet hat
- **THEN** leuchtet die rechte ASL-Taste mit Idle-Farbe und Idle-Helligkeit

#### Scenario: Taste gedrückt

- **WHEN** die rechte ASL-Taste gedrückt wird
- **THEN** wechselt ihre LED auf Farbe und Helligkeit des gedrückten Zustands

#### Scenario: Taste losgelassen

- **WHEN** die rechte ASL-Taste losgelassen wird
- **THEN** kehrt die LED auf den Ruhezustand zurück
