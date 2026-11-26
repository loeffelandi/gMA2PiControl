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

### Requirement: Absolute MIDI-Werte aus Geräteprofilen

Ein MIDI-Profil SHALL zusätzlich zu Tasten und Encodern absolute Controls über
Note und logischen Namen definieren können. Bei einer konfigurierten
Absolut-Note MUST jede Note-On-Nachricht einen normalisierten Wert zwischen
0.0 (Velocity 0) und 1.0 (Velocity 127) erzeugen; das zugehörige Note-Off MUST
ignoriert werden und darf kein Key-Up auslösen.

#### Scenario: Faderwert empfangen

- **WHEN** eine als absolut konfigurierte Fader-Note mit Velocity `64`
  empfangen wird
- **THEN** liefert `ma2pi` genau ein Wertereignis mit dem normalisierten Wert
  `0.5` für das logische Control

#### Scenario: Absoluter Encoderwert empfangen

- **WHEN** eine als absolut konfigurierte Encoder-Note mit Velocity `127`
  empfangen wird
- **THEN** liefert `ma2pi` ein Wertereignis mit dem Wert `1.0` und kein
  Encoder-Delta

#### Scenario: Note-Off eines absoluten Controls

- **WHEN** auf eine absolute Note ein Note-Off folgt
- **THEN** entsteht kein weiteres Ereignis und kein Key-Up

#### Scenario: Note ist gleichzeitig Taste und Wert

- **WHEN** dieselbe Note im Profil sowohl als Taste oder relativer Encoder als
  auch als absoluter Wert konfiguriert ist
- **THEN** lehnt `ma2pi` die Konfiguration mit einer Meldung ab, die Profil und
  Note nennt

### Requirement: Mehrere MIDI-Geräte parallel

`ma2pi` SHALL jedes konfigurierte MIDI-Gerät über einen eigenen, während der
Laufzeit dauerhaft geöffneten Zugriff lesen. Der Verlust oder das erneute
Öffnen eines Geräts MUST die übrigen MIDI-Geräte unabhängig weiterbetreiben und
darf deren Ereignisse nicht unterbrechen.

#### Scenario: Zweites MIDI-Gerät wird erkannt

- **WHEN** neben dem ASL ein weiteres Gerät mit Backend `midi` konfiguriert und
  angeschlossen ist
- **THEN** öffnet `ma2pi` für beide Geräte je einen eigenen Zugriff und liefert
  die Ereignisse getrennt mit dem jeweiligen Gerätenamen

#### Scenario: Ein Gerät wird im Betrieb getrennt

- **WHEN** das zweite MIDI-Gerät während des Betriebs verschwindet
- **THEN** bleiben die Ereignisse des ersten Geräts erhalten, und `ma2pi`
  protokolliert den Verlust des zweiten Geräts

#### Scenario: Gerät erscheint erneut

- **WHEN** das zweite MIDI-Gerät wieder eingesteckt wird
- **THEN** öffnet `ma2pi` es ohne Neustart erneut und liest es mit demselben
  Profil wie zuvor

### Requirement: Unbekannte absolute Werte

Trifft eine Note ein, die weder als Taste, relativer Encoder noch als absoluter
Wert konfiguriert ist, MUST `ma2pi` sie ignorieren und einmalig pro Gerät und
Note protokollieren. Es dürfen keine Frames an die MA gesendet werden.

#### Scenario: Nicht konfigurierte Note

- **WHEN** das MIDICRAFT ENC eine Note sendet, die im Profil nicht vorkommt
- **THEN** wird kein Ereignis weitergereicht und die Note nur beim ersten
  Auftreten protokolliert

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
