# hid-input Specification

## Purpose

Erkennt die konfigurierten Eingabegeräte (Cherry POS Keyboard als evdev-Gerät
und ASL MK2 E4B3 als USB-MIDI-Gerät), filtert die richtigen Interfaces heraus
und liefert normalisierte Key-Down-/Key-Up- sowie Encoder-Ereignisse an die
Mapping-Engine – auch über Geräteverlust und Wiederanstecken hinweg.

## Requirements

### Requirement: Geräteerkennung und Interface-Filterung

Der Daemon SHALL beim Start und bei Geräteänderungen alle `/dev/input/event*`
sowie alle rohen MIDI-Knoten `/dev/snd/midiC*` enumerieren und für jeden
Kandidaten Backend, Name, Vendor-ID, Product-ID und die unterstützten
Event-Typen ermitteln. Geöffnet werden nur Geräte, die einem konfigurierten
Geräteprofil mit passendem Backend entsprechen. Meldet sich ein Gerät mit
mehreren HID-Interfaces, MUST nur das Interface mit Tastatur-Events konsumiert
werden.

#### Scenario: Cherry mit mehreren HID-Interfaces

- **WHEN** das Cherry-Keyboard mehrere `/dev/input/event*`-Geräte mit Vendor-ID `0x046a` anmeldet
- **THEN** wird ausschließlich das Interface mit Tastatur-Events geöffnet und jedes physische Tastenereignis genau einmal verarbeitet

#### Scenario: ASL als MIDI-Gerät

- **WHEN** das ASL MK2 E4B3 als USB-MIDI-Gerät mit Vendor-ID `0x04d8` und Product-ID `0xe817` erscheint
- **THEN** wird der zugehörige `/dev/snd/midiC*`-Knoten geöffnet und nicht versucht, ein evdev-Interface zu öffnen

#### Scenario: Unbekanntes Gerät wird ignoriert

- **WHEN** ein nicht konfiguriertes Eingabegerät am System erscheint
- **THEN** wird es nicht geöffnet und auf Debug-Level mit Backend, Name, Vendor-ID und Product-ID protokolliert

#### Scenario: Filterung über Vendor- und Product-ID

- **WHEN** zwei Geräte denselben Namen, aber unterschiedliche Vendor-/Product-IDs haben
- **THEN** wird nur das Gerät geöffnet, dessen IDs zum konfigurierten Profil passen

#### Scenario: Falsches Backend

- **WHEN** ein Gerät konfiguriert ist, aber nur über ein anderes Backend erscheint als im Profil angegeben
- **THEN** bleibt es ungeöffnet und die Warnung nennt Backend, Vendor-ID und Product-ID

### Requirement: Geräteprofile für nicht standardisierte Hardware

Für Geräte ohne standardisierte HID-Klasse SHALL das Geräteprofil festlegen,
wie Rohdaten als Tasten oder Encoder gelten. Das Profil MUST zum Backend
passen: evdev nutzt Key-Codes und Achsen, MIDI Noten und Richtungs-Velocities.
Fehlt ein passendes Profil, MUST das Gerät ignoriert und eine Warnung mit
Vendor-/Product-ID protokolliert werden.

#### Scenario: ASL wird über ein MIDI-Profil eingebunden

- **WHEN** das ASL-Gerät erkannt wird und sein Profil die Tasten-Noten sowie vier Encoder-Noten definiert
- **THEN** werden diese Noten als Tasten und als Encoder 1–4 an die Mapping-Engine weitergegeben

#### Scenario: Profil verweist auf fehlenden Control

- **WHEN** ein evdev-Profil einen Control referenziert, den das erkannte Gerät nicht unterstützt
- **THEN** bricht der Start mit einer Meldung ab, die Profil, Control und Gerät nennt

#### Scenario: MIDI-Profil ohne Noten

- **WHEN** ein Gerät mit Backend `midi` erkannt wird, sein Profil aber weder Tasten-Noten noch Encoder enthält
- **THEN** bleibt das Gerät ungeöffnet und die Meldung nennt Profil, Gerät und Vendor-/Product-ID

#### Scenario: Kein Profil für erkanntes Gerät

- **WHEN** ein Gerät mit konfigurierter Vendor-ID erkannt wird, aber kein Profil zugeordnet ist
- **THEN** bleibt das Gerät ungeöffnet und die Warnung nennt Vendor-ID und Product-ID zur Profilerstellung

### Requirement: Normalisierung auf logische Controls

Rohe Ereignisse SHALL über das Geräteprofil auf logische Control-Namen
abgebildet werden. Jedes physische Drücken MUST genau ein Key-Down und jedes
Loslassen genau ein Key-Up erzeugen; Autorepeat-Ereignisse MUST unterdrückt
werden. Nicht gemappte Codes MUST ignoriert und einmalig pro Code protokolliert
werden.

#### Scenario: Ein Tastendruck erzeugt genau ein Paar

- **WHEN** eine gemappte Taste gedrückt und wieder losgelassen wird
- **THEN** entstehen genau ein Key-Down und genau ein Key-Up mit dem logischen Control-Namen

#### Scenario: Autorepeat wird unterdrückt

- **WHEN** eine Taste länger als die evdev-Autorepeat-Verzögerung gehalten wird
- **THEN** wird während des Haltens kein weiteres Key-Down erzeugt

#### Scenario: Nicht gemappter Scancode

- **WHEN** ein Scancode eintrifft, der im Profil nicht vorkommt
- **THEN** wird kein Ereignis weitergereicht und der Code wird nur beim ersten Auftreten protokolliert

### Requirement: MIDI-Byte-Parser

Für Geräte mit Backend `midi` SHALL der Daemon einen inkrementellen Parser
betreiben, der Note-On- und Note-Off-Nachrichten auch über mehrere
Lesevorgänge hinweg erkennt und andere Nachrichten ignoriert. Eine
fragmentierte Nachricht MUST erst nach dem letzten Byte ausgewertet und genau
einmal verarbeitet werden.

#### Scenario: Fragmentierte MIDI-Nachricht

- **WHEN** eine Note-On-Nachricht in zwei Lesevorgängen ankommt
- **THEN** wird sie erst nach dem letzten Byte vollständig ausgewertet und genau einmal verarbeitet

#### Scenario: Nicht unterstützte Nachricht

- **WHEN** eine Control-Change- oder System-Nachricht empfangen wird
- **THEN** wird sie ignoriert und erzeugt kein Eingabeereignis

### Requirement: MIDI-Tasten

Eine konfigurierte Tasten-Note MUST bei Note-On mit Velocity größer als `1` ein
Key-Down und bei Note-On mit Velocity `1` oder Note-Off ein Key-Up erzeugen.
Unbekannte Noten MUST ignoriert und einmalig pro Gerät und Note protokolliert
werden.

#### Scenario: ASL-Taste wird gedrückt

- **WHEN** eine Tasten-Note mit Velocity `127` und danach mit Velocity `1` empfangen wird
- **THEN** entstehen genau ein Key-Down und genau ein Key-Up für das gemappte Control

#### Scenario: Unbekannte MIDI-Note

- **WHEN** eine Note eintrifft, die weder als Taste noch als Encoder konfiguriert ist
- **THEN** wird kein Ereignis weitergereicht und die Note wird nur beim ersten Auftreten protokolliert

### Requirement: MIDI-Encoder

Eine konfigurierte Encoder-Note MUST bei Note-On genau einen Detent erzeugen.
Die Velocity MUST die Richtung wählen: die im Profil hinterlegte
`cw_velocity` erzeugt ein positives, `ccw_velocity` ein negatives Delta,
jeweils multipliziert mit `direction`. Andere Velocities sowie das zugehörige
Note-Off MUST kein Ereignis erzeugen.

#### Scenario: Encoder-Rastung im Uhrzeigersinn

- **WHEN** die Encoder-Note mit `cw_velocity` empfangen wird
- **THEN** wird genau ein Delta von `+1` an die Mapping-Engine weitergegeben und das Note-Off erzeugt kein weiteres Delta

#### Scenario: Encoder-Rastung gegen den Uhrzeigersinn

- **WHEN** dieselbe Encoder-Note mit `ccw_velocity` empfangen wird
- **THEN** wird genau ein Delta von `-1` an die Mapping-Engine weitergegeben

#### Scenario: Unbekannte Velocity auf einer Encoder-Note

- **WHEN** eine Encoder-Note mit einer Velocity empfangen wird, die weder `cw_velocity` noch `ccw_velocity` entspricht
- **THEN** wird kein Delta erzeugt

#### Scenario: Richtung invertiert

- **WHEN** ein Encoder `direction = -1` konfiguriert hat
- **THEN** erzeugt `cw_velocity` ein Delta von `-1` und `ccw_velocity` ein Delta von `+1`

### Requirement: Hotplug und Geräteverlust

Beim Verlust eines Geräts SHALL der Daemon alle von diesem Gerät gehaltenen
Tasten freigeben, eine Warnung protokollieren und die übrigen Geräte
weiterbetreiben. Erscheint das Gerät erneut, MUST es ohne Neustart des Daemons
wieder geöffnet werden. Das gilt für evdev- und MIDI-Geräte gleichermaßen.

#### Scenario: Keyboard wird im Betrieb getrennt

- **WHEN** das Cherry-Keyboard gezogen wird, während MA gehalten ist
- **THEN** wird ein Release für MA erzeugt und das ASL-Gerät bleibt weiter funktionsfähig

#### Scenario: ASL wird im Betrieb getrennt

- **WHEN** der ASL entfernt wird, während eine seiner Tasten gehalten ist
- **THEN** wird ein Release für diese Taste erzeugt und das Cherry-Keyboard bleibt weiter funktionsfähig

#### Scenario: Gerät wird wieder angesteckt

- **WHEN** ein zuvor entferntes Gerät erneut erscheint
- **THEN** wird es innerhalb weniger Sekunden ohne Daemon-Neustart wieder geöffnet und liefert Ereignisse

#### Scenario: Gerät fehlt beim Start

- **WHEN** beim Start kein konfiguriertes Gerät vorhanden ist
- **THEN** startet der Daemon trotzdem, protokolliert eine Warnung und sucht mit Backoff weiter

### Requirement: Zugriff ohne Root-Rechte

Der Daemon SHALL die Eingabegeräte ohne Root-Rechte öffnen. Fehlende
Berechtigungen MUST als eindeutiger Fehler mit Hinweis auf die mitgelieferte
udev-Regel protokolliert werden; der Daemon darf dadurch nicht in eine
Tight-Loop geraten. Für MIDI-Geräte MUST die Meldung zusätzlich die
`audio`-Gruppe nennen.

#### Scenario: Zugriff über udev-Regel

- **WHEN** der Daemon als Benutzer `ma2pi` läuft und die udev-Regeln für Cherry und ASL installiert sind
- **THEN** werden alle konfigurierten Geräte ohne Root-Rechte geöffnet

#### Scenario: Fehlende Berechtigung auf dem MIDI-Knoten

- **WHEN** der Daemon keine Leserechte auf `/dev/snd/midiC*` hat
- **THEN** erscheint eine Fehlermeldung mit Gerätepfad, Verweis auf die udev-Regel und dem Hinweis auf die `audio`-Gruppe, und der Öffnungsversuch wird mit Backoff wiederholt

### Requirement: Encoder-Rohwerte zu Detent-Deltas

Für als Encoder konfigurierte evdev-Controls SHALL der Daemon absolute oder
relative Werte in vorzeichenbehaftete Detent-Deltas umrechnen, die Richtung
gemäß Profil normalisieren und Werte unterhalb der konfigurierten Schwelle
verwerfen. MIDI-Encoder liefern ihre Deltas bereits pro Rastung über je eine
Note und die richtungsgebende Velocity und benötigen keine Schwellenlogik.

#### Scenario: Drei Raster im Uhrzeigersinn

- **WHEN** der Encoder drei Detents im Uhrzeigersinn meldet
- **THEN** wird ein Delta von `+3` an die Mapping-Engine weitergegeben

#### Scenario: Drehung gegen den Uhrzeigersinn

- **WHEN** der Encoder zwei Detents gegen den Uhrzeigersinn meldet
- **THEN** wird ein Delta von `-2` weitergegeben

#### Scenario: Absolute Achse mit Überlauf

- **WHEN** eine absolute Encoder-Achse über ihren Wertebereich hinausläuft
- **THEN** wird der Überlauf als korrektes signed Delta interpretiert und nicht als Sprung über den gesamten Wertebereich

#### Scenario: Rauschen unterhalb der Schwelle

- **WHEN** ein Achsenwert unterhalb der konfigurierten Detent-Schwelle schwankt
- **THEN** entsteht kein Delta und kein Frame
