# encoder-control Specification

## Purpose

Übersetzt die vier Drehgeber des ASL MK2 E4B3 in die Attribut-Encoder der
laufenden onPC: Sie folgen dem Attribut-Fenster, das die onPC anzeigt, bündeln
Detent-Deltas zu wenigen nativen Encoder-Frames, unterstützen
Normal/Fine/Ultra pro Encoder-Klick und schützen die onPC vor zu hohen
Frame-Raten. Eine Taste schaltet zwischen Attribut- und Screen-Encodern um.

## Requirements

### Requirement: Encoder-Zielmapping

Jeder physische Encoder SHALL in der Konfiguration genau ein Ziel erhalten:
entweder einen Attribut-Slot (`slot`, 1–8) oder einen festen Attributnamen
(`attribute`). Beide gleichzeitig, eine ungültige Slot-Nummer oder eine doppelte
Encoder-ID MUST die Konfigurationsvalidierung fehlschlagen lassen.

#### Scenario: Encoder folgt dem Attribut-Fenster

- **WHEN** Encoder 1 auf Slot 1 gemappt ist
- **THEN** sendet er Deltas für das erste Attribut, das die onPC im aktuellen Fenster zeigt

#### Scenario: Encoder auf festem Attribut

- **WHEN** Encoder 2 auf das Attribut `PAN` gemappt ist
- **THEN** sendet er seine Deltas unabhängig vom angezeigten Fenster an `PAN`

#### Scenario: Ungültiger Slot

- **WHEN** die Konfiguration einen Slot außerhalb von 1–8 zuweist
- **THEN** bricht die Validierung mit einer Meldung ab, die den gültigen Bereich nennt

#### Scenario: Doppelte Encoder-ID

- **WHEN** zwei Einträge dieselbe Encoder-ID definieren
- **THEN** bricht die Validierung mit Verweis auf beide Einträge ab

### Requirement: Attribut-Fenster folgt der onPC

Die Slot-Encoder SHALL die Hardware-Attribut-Encoder der onPC adressieren; die
onPC routet diese selbst auf das aktuell gewählte Feature und Attribut-Fenster.
Der Daemon MUST kein `presetTypes`-Dauer-Polling betreiben; er DARF das
Attribut-Modell nur beim Verbinden und kurz nach einem Auflösungswechsel lesen,
um Attributnamen und Auflösung zu bestimmen.

#### Scenario: onPC blättert weiter

- **WHEN** der Benutzer in der onPC von den Attributen 1–4 auf die Attribute 5–8 wechselt
- **THEN** senden die vier Encoder weiterhin ihre Hardware-Encoder-Indizes und die onPC legt sie auf die Attribute 5–8

#### Scenario: Weniger Attribute als Slots

- **WHEN** das aktuelle Feature nur zwei Attribute hat
- **THEN** bleiben die Hardware-Encoder 3 und 4 an der onPC ohne Wirkung; der Daemon sendet ihre Indizes weiter und die onPC ignoriert sie

#### Scenario: Feature-Wechsel

- **WHEN** der Benutzer in der onPC ein anderes Feature wählt
- **THEN** adressieren die Encoder ohne Zutun des Daemons das Fenster des neuen Features; es findet kein Dauer-Polling statt

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

### Requirement: LED-Anzeige des Encoder-Modus

Der aktive Modus MUST im Status sichtbar sein und als LED-Zustand an einer
konfigurierten Taste ausgegeben werden: grün im Screen-Modus, rot im
Attribut-Modus. Die LED-Ausgabe MUST das Gerät nicht blockieren, wenn es fehlt.

#### Scenario: Moduswechsel an der LED

- **WHEN** der Modus zwischen Attribut und Screen wechselt
- **THEN** sendet der Daemon innerhalb einer Sekunde die passende Farbe an die Modus-LED

#### Scenario: Gerät nicht angeschlossen

- **WHEN** die LED-Ausgabe aktiviert ist, das MIDI-Gerät aber fehlt
- **THEN** startet der Daemon normal, protokolliert eine Warnung und versucht es beim nächsten Erscheinen erneut

### Requirement: Delta-Akkumulation und Flush

Die Engine SHALL signed Detent-Deltas pro Encoder akkumulieren und höchstens
einmal pro konfiguriertem Flush-Intervall (Default 40 ms) senden. Ein Flush mit
Delta 0 MUST unterbleiben; nach einer Idle-Frist MUST der letzte aufgelaufene
Delta gesendet werden, damit keine Detents verloren gehen.

#### Scenario: Schneller Stoß

- **WHEN** innerhalb von 10 ms zehn Detents an einem Encoder anfallen
- **THEN** entsteht daraus ein einziger Frame mit dem akkumulierten Delta statt zehn Einzelframes

#### Scenario: Langsame Drehung

- **WHEN** die Detents langsamer als das Flush-Intervall eintreffen
- **THEN** wird jeder Detent spätestens nach Ablauf des Intervalls gesendet

#### Scenario: Gleiche Drehung in beide Richtungen

- **WHEN** innerhalb eines Intervalls gleich viele Detents vorwärts und rückwärts anfallen
- **THEN** ist das akkumulierte Delta 0 und es wird kein Frame gesendet

#### Scenario: Letzter Detent vor dem Loslassen

- **WHEN** die Drehung endet, kurz nachdem ein Detent akkumuliert wurde
- **THEN** wird dieser letzte Delta nach der Idle-Frist noch gesendet

### Requirement: Beschleunigungskurve

Die Übersetzung von Detents in Delta SHALL eine konfigurierbare Kurve
(`none`, `linear`, `exponentiell`) verwenden. Bei schnellem Drehen MUST der Delta
pro Detent größer sein als bei langsamem; das Vorzeichen MUST erhalten bleiben
und ein von Null verschiedener Input darf nie Delta 0 erzeugen.

#### Scenario: Langsame Drehung ohne Beschleunigung

- **WHEN** die Kurve `none` aktiv ist und ein Detent eintrifft
- **THEN** entspricht der gesendete Delta genau einem Detent

#### Scenario: Schnelle Drehung mit Beschleunigung

- **WHEN** die Kurve `linear` aktiv ist und mehrere Detents innerhalb eines kurzen Fensters eintreffen
- **THEN** ist der Delta pro Detent größer als bei einem einzelnen langsamen Detent

#### Scenario: Vorzeichen bleibt erhalten

- **WHEN** schnell gegen den Uhrzeigersinn gedreht wird
- **THEN** sind alle gesendeten Deltas negativ

### Requirement: Rate-Limiting und Lockup-Schutz

Encoder-Ausgaben SHALL dem globalen Rate-Limiter unterliegen. Bei Sättigung MUST
der Daemon Deltas weiter akkumulieren, statt Frames unbegrenzt zu puffern; der
akkumulierte Delta MUST auf einen konfigurierten Maximalwert begrenzt und jedes
Verwerfen geloggt werden.

#### Scenario: Dauerhaft schnelle Drehung

- **WHEN** ein Encoder 100 Detents pro Sekunde liefert und das Limit 25 Frames pro Sekunde beträgt
- **THEN** werden höchstens 25 Frames pro Sekunde gesendet und die Summe der gesendeten Deltas entspricht bis zur Obergrenze der Eingabe

#### Scenario: Begrenzter Puffer

- **WHEN** die onPC über längere Zeit keine Frames mehr abnimmt
- **THEN** wächst der Encoder-Puffer nicht unbegrenzt, sondern wird bei der konfigurierten Obergrenze gekappt und das Kappen protokolliert

#### Scenario: Nachlauf nach dem Loslassen

- **WHEN** die Drehung endet und noch ein akkumulierter Delta offen ist
- **THEN** wird dieser Delta nach dem nächsten freien Limit-Slot gesendet

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

### Requirement: NIPPLE-Hardkey auf der rechten ASL-Taste

Die mitgelieferte Konfiguration SHALL die rechte ASL-Taste (`asl_button_3`,
Note 11) auf den Hardkey `NIPPLE` legen. Der Daemon MUST dafür keinen eigenen
Modus auswerten, sondern den Hardkey wie jede andere Taste senden.

#### Scenario: Rechte ASL-Taste drücken

- **WHEN** die rechte ASL-Taste gedrückt und wieder losgelassen wird
- **THEN** sendet der Daemon einen `NIPPLE`-Press und einen `NIPPLE`-Release an die onPC

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

Ein Druck auf einen Slot-Encoder SHALL als `LUA 'gma.canbus.encoder(<Index>, 0, true)'`
und beim Loslassen als `(<Index>, 0, false)` an die onPC gehen. Der Release MUST
denselben Index wie der Press verwenden. Die Zuordnung erfolgt per
`encoder_press = <slot>`; `asl_click_1..4` liegen standardmäßig auf Slot 1–4.

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

Solange der lokale Modifier `asl_button_2` gehalten wird, SHALL ein Encoder-Klick
die Auflösung des Attributs des Slots in der onPC zyklisch umschalten (Normal →
Fine → Ultra → Normal) und keinen Encoder-Druck senden. Die Umschaltung MUST per
nativem `encoder`-Frame mit `name` und `resolution` erfolgen; der Daemon skaliert
Deltas nicht selbst. Für Screen-Encoder (Screen-Modus oder MA gehalten) MUST
nichts gesendet und eine Warnung protokolliert werden.

#### Scenario: Auflösung durchschalten

- **WHEN** `asl_button_2` gehalten und Encoder 1 dreimal geklickt wird
- **THEN** werden nacheinander `resolution` 1, 2 und 0 für das Attribut von Slot 1 gesendet, und kein Klick erzeugt einen Encoder-Druck-Frame

#### Scenario: Fine skaliert

- **WHEN** die onPC Fine für das Attribut meldet und der Slot gedreht wird
- **THEN** ändert sich der Wert pro Schritt entsprechend kleiner, ohne dass der Daemon die Schritte skaliert

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
