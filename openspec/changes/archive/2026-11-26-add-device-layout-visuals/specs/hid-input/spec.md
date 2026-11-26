# Spec Delta

## MODIFIED Requirements

### Requirement: Geräteprofile für nicht standardisierte Hardware

Für Geräte ohne standardisierte HID-Klasse SHALL das Geräteprofil festlegen,
wie Rohdaten als Tasten oder Encoder gelten. Das Profil MUST zum Backend
passen: evdev nutzt Key-Codes und Achsen, MIDI Noten und Richtungs-Velocities.
Ein MIDI-Profil MAY Controls deklarieren, deren Noten noch nicht gelernt sind;
diese Controls liefern bis zum Lernen keine Ereignisse. Fehlt ein passendes
Profil, MUST das Gerät ignoriert und eine Warnung mit Vendor-/Product-ID
protokolliert werden.

#### Scenario: ASL wird über ein MIDI-Profil eingebunden

- **WHEN** das ASL-Gerät erkannt wird und sein Profil die Tasten-Noten sowie vier Encoder-Noten definiert
- **THEN** werden diese Noten als Tasten und als Encoder 1–4 an die Mapping-Engine weitergegeben

#### Scenario: Profil verweist auf fehlenden Control

- **WHEN** ein evdev-Profil einen Control referenziert, den das erkannte Gerät nicht unterstützt
- **THEN** bricht der Start mit einer Meldung ab, die Profil, Control und Gerät nennt

#### Scenario: MIDI-Profil ohne Noten

- **WHEN** ein Gerät mit Backend `midi` erkannt wird, sein Profil aber weder Controls noch Noten enthält
- **THEN** bleibt das Gerät ungeöffnet und die Meldung nennt Profil, Gerät und Vendor-/Product-ID

#### Scenario: MIDI-Profil mit noch nicht gelernten Noten

- **WHEN** ein Profil Controls deklariert, aber für eine Bank noch keine Noten gelernt sind
- **THEN** wird das Gerät geöffnet und die ungebundenen Controls liefern bis zum Lernen keine Ereignisse

#### Scenario: Kein Profil für erkanntes Gerät

- **WHEN** ein Gerät mit konfigurierter Vendor-ID erkannt wird, aber kein Profil zugeordnet ist
- **THEN** bleibt das Gerät ungeöffnet und die Warnung nennt Vendor-ID und Product-ID zur Profilerstellung

## ADDED Requirements

### Requirement: Control-Inventar unabhängig von Noten

Ein MIDI-Profil SHALL seine physischen Controls als Inventar mit `id` und
`kind` (`button`, `fader`, `poti`, `encoder`, `relative-encoder`) deklarieren
können. Die Notenbelegung MUST auf Controls dieses Inventars verweisen. Fehlt
ein Inventar, MUST das Profil seine Controls aus den bisherigen Noten-,
Encoder- und Werte-Sektionen ableiten.

#### Scenario: Profil mit Inventar ohne Noten

- **WHEN** ein Profil 20 Tasten, fünf Fader und fünf Encoder deklariert, aber keine Noten nennt
- **THEN** ist das Profil gültig, die Controls sind für Layout und Learn verfügbar und es werden keine Eingaben erzeugt

#### Scenario: Note verweist auf unbekannten Control

- **WHEN** eine Bank eine Note einem Control zuordnet, das im Inventar fehlt
- **THEN** schlägt die Validierung mit Profil, Bank, Note und Control fehl

#### Scenario: Altprofil ohne Inventar

- **WHEN** ein bestehendes Profil nur `notes`, `midi_encoders` und `midi_values` enthält
- **THEN** werden die daraus abgeleiteten Controls als Inventar behandelt und die Konfiguration bleibt gültig

### Requirement: Bankabhängige MIDI-Profile

Ein MIDI-Profil SHALL bis zu 16 Bänke mit eigenem MIDI-Kanal und eigener
Notenbelegung definieren können. Die Kanäle MUST je Profil eindeutig sein;
innerhalb einer Bank MUST jede Note genau einem Control zugeordnet sein. Flache
Noten ohne Bank-Angabe MUST Bank 1 auf Kanal 1 zugeordnet werden.

#### Scenario: Zwei Bänke auf verschiedenen Kanälen

- **WHEN** Bank 1 Kanal 1 und Bank 2 Kanal 2 verwenden
- **THEN** erzeugen Ereignisse auf beiden Kanälen getrennte Bank-Ereignisse

#### Scenario: Gleiche Note in zwei Bänken

- **WHEN** Bank 1 und Bank 2 dieselbe Note auf unterschiedlichen Kanälen verwenden
- **THEN** ist die Belegung gültig und die Ereignisse bleiben unterscheidbar

#### Scenario: Note ohne Bank-Angabe

- **WHEN** ein Profil eine Taste ohne Bank-Zuordnung definiert
- **THEN** wird sie als Control der Bank 1 auf Kanal 1 behandelt

### Requirement: Bank im normalisierten Ereignis

Jedes aus einem MIDI-Gerät erzeugte Ereignis MUST die Bank tragen, deren
MIDI-Kanal der Nachricht entspricht. Für Geräte ohne Bank-Definition und für
evdev-Geräte MUST Bank 1 gesetzt sein. Die Bank MUST für Tasten-, Encoder- und
Werte-Ereignisse gleichermaßen gelten.

#### Scenario: Werteereignis aus Bank 2

- **WHEN** ein Fader auf MIDI-Kanal 2 bewegt wird und Bank 2 diesen Kanal verwendet
- **THEN** trägt das Werteereignis den Control, den Wert und Bank 2

#### Scenario: Keyboard ohne Bänke

- **WHEN** eine Cherry-Taste gedrückt wird
- **THEN** trägt das Tastenereignis Bank 1

### Requirement: Profile für die MIDICRAFT-Familie

Für jedes aktuelle MIDICRAFT-Modell SHALL ein Geräteprofil mit Vendor-ID,
Namensfilter, Control-Inventar und bis zu 16 Bänken mitgeliefert werden, deren
Kanal standardmäßig der Banknummer entspricht. Die Notenbelegung MUST durch den
Learn-Modus befüllbar sein, weil sie am Gerät frei einstellbar ist.

#### Scenario: Control-Zahlen der Modelle

- **WHEN** die mitgelieferten MIDICRAFT-Profile geladen werden
- **THEN** deklariert `PUSH²` 30 Tasten, `FADE²` fünf Fader und 20 Tasten, `TURN²` 15 Tasten und 15 Potis, `MIX²` fünf Fader, 15 Tasten und fünf Potis, `ENC` fünf Fader, 15 Tasten und fünf Encoder sowie `SPOT` fünf Fader, zehn Tasten und zehn Potis

#### Scenario: Frisches MIDICRAFT-Profil

- **WHEN** ein MIDICRAFT-Modell mit Inventar, aber ohne gelernte Noten konfiguriert ist und erscheint
- **THEN** wird es geöffnet, die Fläche zeigt alle Controls und es werden noch keine Ereignisse erzeugt

#### Scenario: Gelerntes MIDICRAFT-Profil

- **WHEN** die Noten über den Learn-Modus für eine Bank erfasst und gespeichert wurden
- **THEN** liefern die Controls dieser Bank Ereignisse mit der gelernten Bank

### Requirement: Eindeutige Control-Namen je Gerät

Control-Namen MUST innerhalb der gesamten Konfiguration eindeutig sein, damit
Mappings und Layouts keinem falschen Gerät zugeordnet werden. Die
MIDICRAFT-Modelle MUST dafür getrennte Namenspräfixe verwenden; das bestehende
Präfix `mc_` bleibt dem `ENC` vorbehalten.

#### Scenario: Zwei MIDICRAFT-Modelle parallel

- **WHEN** ein `ENC` und ein `PUSH²` gleichzeitig konfiguriert sind
- **THEN** kollidieren ihre Control-Namen nicht und beide Geräte liefern getrennte Ereignisse

#### Scenario: Doppelter Control-Name

- **WHEN** zwei Profile denselben Control-Namen definieren
- **THEN** schlägt die Konfigurationsvalidierung mit dem Namen und beiden Profilen fehl
