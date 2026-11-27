# Spec Delta

## MODIFIED Requirements

### Requirement: LED-Anzeige des Encoder-Modus

Der aktive Modus MUST im Status sichtbar sein und als LED-Zustand an einer
konfigurierten Taste ausgegeben werden: grün im effektiven Screen-Modus, rot im
Attribut-Modus. Der Status MUST den festen Modus, den gehaltenen momentanen
Modifier und den effektiven Modus getrennt melden. Die LED-Ausgabe MUST das
Gerät nicht blockieren, wenn es fehlt.

#### Scenario: Moduswechsel an der LED

- **WHEN** der Modus zwischen Attribut und Screen wechselt
- **THEN** sendet der Daemon innerhalb einer Sekunde die passende Farbe an die Modus-LED

#### Scenario: Gerät nicht angeschlossen

- **WHEN** die LED-Ausgabe aktiviert ist, das MIDI-Gerät aber fehlt
- **THEN** startet der Daemon normal, protokolliert eine Warnung und versucht es beim nächsten Erscheinen erneut

#### Scenario: Momentaner Modus färbt die LED

- **WHEN** der momentane Screen-Modifier gehalten wird, während der feste Modus ausgeschaltet ist
- **THEN** wird die Modus-LED grün und nach dem Loslassen wieder rot

### Requirement: Temporärer Screen-Modus per MA

Solange der momentane Screen-Modifier gehalten wird, MUST jeder Slot-Encoder
die Screen-Encoder aus `mapping.screen_encoders` adressieren, auch wenn der
globale Screen-Modus ausgeschaltet ist. Standardmäßig ist das die MA-Taste;
`mapping.screen_mode.momentary` benennt den Control, wobei `auto` auf den
Control mit Hardkey `MA` auflöst und `none` das Verhalten abschaltet. Beim
Loslassen MUST der nächste Detent wieder die Hardware-Attribut-Encoder
adressieren; ein Moduswechsel zwischen zwei Detents MUST zwei getrennte Frames
erzeugen.

#### Scenario: MA + Encoder

- **WHEN** MA gehalten und Slot 1 um einen Detent gedreht wird
- **THEN** wird ein canbus-Encoder-Frame mit dem Index für die Slot 1 zugeordnete Screen-Encoder-Nummer (Standard `8`) gesendet

#### Scenario: Loslassen

- **WHEN** MA losgelassen und Slot 1 erneut gedreht wird
- **THEN** adressiert der Frame wieder den Hardware-Attribut-Encoder der onPC

#### Scenario: Wechsel zwischen Detents

- **WHEN** ein Attribut-Detent aussteht und MA vor dem nächsten Detent gedrückt wird
- **THEN** werden Attribut- und Screen-Delta als getrennte Frames gesendet

#### Scenario: Anderer Control als momentaner Modifier

- **WHEN** `mapping.screen_mode.momentary` einen anderen Control benennt und dieser gehalten wird
- **THEN** adressieren die Slot-Encoder die Screen-Encoder, obwohl MA nicht gedrückt ist

#### Scenario: Momentaner Modus abgeschaltet

- **WHEN** `mapping.screen_mode.momentary = "none"` gilt und die MA-Taste gehalten wird
- **THEN** adressieren die Encoder weiterhin die Attribut-Encoder und die Modus-LED wechselt nicht

### Requirement: NIPPLE-LED

Die rechte ASL-Taste (Note 11) SHALL standardmäßig leicht orange leuchten
(Farbindex 121, Helligkeit 25) und solange sie gedrückt wird heller (Farbindex
116, Helligkeit 127). Die Helligkeitsstufe MUST dem in `led.nipple_control`
gebundenen Control folgen; `auto` bindet den Control mit Hardkey `NIPPLE`.
Farbe und Helligkeit MUST in `[led]` konfigurierbar sein. Fehlt das MIDI-Gerät,
MUST der Daemon normal weiterlaufen.

#### Scenario: Ruhezustand

- **WHEN** der Daemon die LED-Ausgabe geöffnet hat
- **THEN** leuchtet die rechte ASL-Taste mit Idle-Farbe und Idle-Helligkeit

#### Scenario: Taste gedrückt

- **WHEN** die rechte ASL-Taste gedrückt wird
- **THEN** wechselt ihre LED auf Farbe und Helligkeit des gedrückten Zustands

#### Scenario: Taste losgelassen

- **WHEN** die rechte ASL-Taste losgelassen wird
- **THEN** kehrt die LED auf den Ruhezustand zurück

#### Scenario: Anderer Control gebunden

- **WHEN** `led.nipple_control` einen anderen Control benennt und dieser gedrückt wird
- **THEN** wechselt die Nipple-LED unabhängig vom Hardkey `NIPPLE` auf die gedrückte Stufe

### Requirement: LED der Fine-Taste

Die mittlere ASL-Taste (Note 10) SHALL im Ruhezustand gedimmt (Farbindex 123,
Helligkeit 25) leuchten und solange sie als Fine-Modifier gehalten wird hell
(Helligkeit 127). Die Helligkeitsstufe MUST dem in `led.fine_control`
gebundenen Control folgen; `auto` bindet den `resolution.cycle_modifier`.
Farbe und Helligkeiten MUST in `[led]` konfigurierbar sein.

#### Scenario: Ruhezustand

- **WHEN** die LED-Ausgabe geöffnet ist
- **THEN** leuchtet die mittlere ASL-Taste mit Ruhefarbe und Ruhehelligkeit

#### Scenario: Taste gehalten

- **WHEN** die mittlere ASL-Taste gedrückt wird
- **THEN** wechselt ihre LED auf die helle Stufe

#### Scenario: Taste losgelassen

- **WHEN** die mittlere ASL-Taste losgelassen wird
- **THEN** kehrt die LED auf die gedimmte Stufe zurück

#### Scenario: Abweichende Fine-Bindung

- **WHEN** `led.fine_control` einen anderen Control benennt und dieser gehalten wird
- **THEN** zeigt die Fine-LED die helle Stufe, obwohl die mittlere ASL-Taste nicht gedrückt ist

## ADDED Requirements

### Requirement: Konfiguration des momentanen Screen-Modifiers

`[mapping.screen_mode]` SHALL den Schlüssel `momentary` akzeptieren: `auto`
(Standard), einen Control-Namen oder `none`. `auto` MUST den ersten Control mit
Hardkey `MA` auflösen; existiert keiner, MUST kein momentaner Modus entstehen.
Ein benannter Control MUST existieren und MAY als Modifier oder als normale
Taste konfiguriert sein. `none` MUST das Verhalten abschalten. Ein unbekannter
Control MUST die Validierung mit Feldbezug fehlschlagen lassen.

#### Scenario: Auto mit MA-Control

- **WHEN** `momentary = "auto"` gilt und ein Control auf den Hardkey `MA` zeigt
- **THEN** löst die Konfiguration diesen Control als momentanen Modifier auf

#### Scenario: Auto ohne MA-Control

- **WHEN** `momentary = "auto"` gilt und kein Control auf den Hardkey `MA` zeigt
- **THEN** bleibt das Verhalten aus und die Konfiguration ist gültig

#### Scenario: Benannter Control

- **WHEN** `momentary = "asl_button_3"` gilt und dieser Control existiert
- **THEN** schaltet dessen Halten den momentanen Screen-Modus

#### Scenario: Abgeschaltet

- **WHEN** `momentary = "none"` gesetzt ist
- **THEN** entsteht kein momentaner Screen-Modus

#### Scenario: Unbekannter Control

- **WHEN** `momentary` einen nicht vorhandenen Control benennt
- **THEN** lehnt die Validierung die Konfiguration mit Nennung des Feldes und des Controls ab

### Requirement: Bindung der Funktions-LEDs

`[led]` SHALL `fine_control` und `nipple_control` akzeptieren: `auto`
(Standard), einen Control-Namen oder `none`. `auto` MUST für `fine_control` den
`resolution.cycle_modifier` und für `nipple_control` den Control mit Hardkey
`NIPPLE` verwenden. Ein benannter Control MUST existieren; `none` MUST die
jeweilige LED-Funktion abschalten. Die aufgelösten Bindungen MUST im Status und
im Konfigurationskatalog sichtbar sein.

#### Scenario: Auto-Bindung

- **WHEN** beide Bindungen auf `auto` stehen
- **THEN** verhält sich die Fine-LED wie der Cycle-Modifier und die Nipple-LED wie der NIPPLE-Hardkey

#### Scenario: Fine-LED abgeschaltet

- **WHEN** `fine_control = "none"` gesetzt ist
- **THEN** bleibt die Fine-LED auf ihrer Ruhestufe, unabhängig von gehaltenen Modifiern

#### Scenario: Unbekannter Control

- **WHEN** eine LED-Bindung einen nicht vorhandenen Control benennt
- **THEN** lehnt die Validierung die Konfiguration mit Nennung des Feldes ab

### Requirement: Effektiver Modus im Status

Der Status SHALL den festen Screen-Modus, den gehaltenen momentanen Modifier
und den effektiven Modus getrennt melden. Der effektive Modus MUST wahr sein,
wenn der feste Modus aktiv ist oder der momentane Modifier gehalten wird. Die
Modus-LED MUST dem effektiven Modus folgen. Bei Verbindungsverlust, Konfig-
Tausch und Freigabe gehaltener Tasten MUST der momentane Modus zurückgesetzt
werden.

#### Scenario: Momentaner Modus im Status

- **WHEN** der momentane Modifier gehalten wird, während der feste Modus ausgeschaltet ist
- **THEN** meldet der Status `screen_mode = false`, den Modifier als gehalten und den effektiven Modus als wahr

#### Scenario: Loslassen setzt zurück

- **WHEN** der momentane Modifier losgelassen wird
- **THEN** ist der effektive Modus wieder gleich dem festen Modus

#### Scenario: Verbindungsverlust

- **WHEN** die onPC-Verbindung während eines gehaltenen momentanen Modus abbricht
- **THEN** gilt der momentane Modus als losgelassen und die LED zeigt die Farbe des festen Modus
