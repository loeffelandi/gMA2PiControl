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

Das von den Slots adressierte Attribut-Fenster SHALL aus der aktuellen Auswahl
der onPC abgeleitet werden, nicht aus einem eigenen Bankzähler. Blättert der
Benutzer in der onPC zum nächsten Attribut-Block, MUST der Daemon das innerhalb
weniger Sekunden übernehmen. Slots ohne zugehöriges Attribut MUST keine Frames
erzeugen.

#### Scenario: onPC blättert weiter

- **WHEN** der Benutzer in der onPC von den Attributen 1–4 auf die Attribute 5–8 wechselt
- **THEN** senden die vier Encoder danach die Attribute 5–8

#### Scenario: Weniger Attribute als Slots

- **WHEN** das aktuelle Feature nur zwei Attribute hat
- **THEN** bleiben die Slots 3 und 4 ohne Wirkung und senden keine Frames

#### Scenario: Feature-Wechsel

- **WHEN** der Benutzer in der onPC ein anderes Feature wählt
- **THEN** übernehmen die Encoder das Fenster des neuen Features

### Requirement: Auflösung per Encoder-Klick

Ein Druck auf einen Encoder SHALL dessen Auflösung zyklisch umschalten:
Normal (0) → Fine (1) → Ultra (2) → Normal (0). Die Auflösung MUST pro Encoder
gespeichert und als eigener `encoder`-Frame mit `resolution` an die onPC
gesendet werden. Sie MUST nur nachfolgende Deltas betreffen.

#### Scenario: Drei Klicks

- **WHEN** ein Encoder dreimal hintereinander gedrückt wird
- **THEN** werden nacheinander `resolution` 1, 2 und 0 gesendet

#### Scenario: Auflösung gilt ab dem nächsten Detent

- **WHEN** die Auflösung geändert wird, während noch Deltas ausstehen
- **THEN** wird der ausstehende Delta verworfen und erst der nächste Detent mit der neuen Auflösung gesendet

### Requirement: Screen-Modus per Taste

Eine konfigurierte Taste SHALL zwischen Attribut- und Screen-Encodern
umschalten. Im Screen-Modus MUST jeder Slot auf den in
`mapping.screen_encoders` hinterlegten Namen zeigen.

#### Scenario: Umschalten mit konfigurierten Screen-Encodern

- **WHEN** `mapping.screen_encoders` die Slots 1–4 belegt und die Taste gedrückt wird
- **THEN** senden die Encoder danach die Screen-Encoder-Namen und der Status meldet `screen_mode: true`

#### Scenario: Umschalten ohne Konfiguration

- **WHEN** `mapping.screen_encoders` fehlt und die Taste gedrückt wird
- **THEN** wechselt der Modus, es werden aber keine Encoder-Frames gesendet und eine Warnung nennt die fehlende Konfiguration

#### Scenario: Zurück in den Attribut-Modus

- **WHEN** die Taste im Screen-Modus erneut gedrückt wird
- **THEN** folgen die Encoder wieder dem Attribut-Fenster der onPC

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

### Requirement: Nativer Encoder-Frame

Der Encoder-Transport SHALL ausschließlich der native Web-Remote-Frame sein. Pro
Flush MUST genau ein Frame `{"requestType": "encoder", "name": <Attribut>,
"value": <Delta>}` entstehen. Auflösungswechsel MUST als eigener Frame ohne
`value` gesendet werden. CMD-Wrapper für Encoder werden nicht verwendet.

#### Scenario: Attribut-Delta

- **WHEN** ein akkumulierter Delta für `DIM` anliegt
- **THEN** wird genau ein Frame mit `name: "DIM"` und dem Delta als `value` gesendet

#### Scenario: Auflösungswechsel

- **WHEN** die Auflösung für `DIM` auf Fine wechselt
- **THEN** wird ein Frame mit `name: "DIM"` und `resolution: 1`, aber ohne `value` gesendet

#### Scenario: Dry-Run

- **WHEN** der Daemon im Dry-Run läuft
- **THEN** werden die nativen Encoder-Frames protokolliert, ohne dass eine Verbindung geöffnet wird

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