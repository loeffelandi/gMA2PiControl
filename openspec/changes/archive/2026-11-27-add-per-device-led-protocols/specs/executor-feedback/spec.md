# Spec Delta

## MODIFIED Requirements

### Requirement: LED-Fähigkeit im Geräteprofil

Ein Geräteprofil SHALL mit `[profiles.<id>.led_feedback]` deklarieren, ob
Feedback ausgegeben wird und mit welchem Protokoll. Gültig MUST
`protocol = "midicraft-v2"` oder `protocol = "asl-mk2"` sein. Die optionale
Liste `led_notes` MUST die Noten benennen, die tatsächlich LEDs besitzen; fehlt
sie, gelten alle Profil-Noten, die ein Button-Ziel haben, als LED-fähig.
Bei einem Gerät mit Bänken nennt `led_notes` die Noten der ersten Bank; die
Controls dieser Noten gelten in jeder Bank als LED-fähig, und zwar auf der Note,
die das Control in der jeweiligen Bank hat. Feedback MUST ausschließlich an
Controls gehen, die im Profil als LED-fähig gelten.

#### Scenario: Gerät ohne Feedback-Deklaration

- **WHEN** ein Profil kein `led_feedback` besitzt, obwohl `[feedback]` aktiv ist
- **THEN** sendet `ma2pi` an dieses Gerät keine LED-Frames

#### Scenario: Unbekanntes Protokoll

- **WHEN** ein Profil `protocol = "foo"` angibt
- **THEN** lehnt die Konfigurationsprüfung das Profil mit Nennung des Feldes ab

#### Scenario: Nicht-LED-Note bleibt dunkel

- **WHEN** ein Control mit Playback-Ziel eine Note nutzt, die nicht in
  `led_notes` steht
- **THEN** sendet `ma2pi` für dieses Control keinen LED-Frame

#### Scenario: Weitere Bank mit anderer Notenbelegung

- **WHEN** das ENC in Bank 1 `led_notes = [65]` mit dem Control `mc_row1_1`
  hat und Bank 2 dasselbe Control auf Note 10 (Kanal 2) legt
- **THEN** erhält Note 10 auf Kanal 2 die LED des Executors dieser Bank, und
  Controls ohne LED in Bank 1 bleiben in Bank 2 ohne LED-Frame

#### Scenario: Zwei Geräte, zwei Protokolle

- **WHEN** das ENC-Profil `midicraft-v2` und das ASL-Profil `asl-mk2` angibt und
  auf beiden ein laufender Executor rot ist
- **THEN** erhält jedes Gerät die rote LED in seiner eigenen Kodierung, und
  kein Gerät erhält Frames des anderen Protokolls

### Requirement: Farbe aus der Web-Remote-Antwort

Die LED-Farbe MUST aus dem Hex-Feld `bC` des Executors abgeleitet und auf die
nächstliegende der 15 Palettenfarben abgebildet werden; CTO steht dabei für
Warmweiß, CTB für Kaltweiß, reines Weiß `#ffffff` MUST weiß bleiben. Fehlt
`bC` oder ist es nicht auflösbar (auch `#000000`), MUST `bdC` verwendet werden.
Ist auch `bdC` nicht auflösbar, MUST `fallback_color` gelten.

#### Scenario: Appearance-Farbe wird übernommen

- **WHEN** die Antwort für einen Executor `bC = "#ff0000"` enthält
- **THEN** wird die LED in Rot angesteuert

#### Scenario: Ähnliche Farbe

- **WHEN** die Antwort einen Farbwert enthält, der keinem Paletteneintrag exakt
  entspricht
- **THEN** wird die Palettenfarbe mit dem geringsten Farbabstand verwendet

#### Scenario: Keine Farbe vorhanden

- **WHEN** die Antwort weder `bC` noch `bdC` enthält
- **THEN** wird `fallback_color` verwendet

#### Scenario: Schwarz bedeutet keine Farbe

- **WHEN** `bC = "#000000"` ist und `bdC` fehlt oder ebenfalls nicht auflösbar
  ist
- **THEN** wird `fallback_color` verwendet

#### Scenario: Warmweiß wird CTO

- **WHEN** die Antwort `bC = "#ffe0b0"` enthält
- **THEN** wird die LED in CTO angesteuert

#### Scenario: Kaltweiß wird CTB

- **WHEN** die Antwort `bC = "#c0e0ff"` enthält
- **THEN** wird die LED in CTB angesteuert

#### Scenario: Reinweiß bleibt weiß

- **WHEN** die Antwort `bC = "#ffffff"` enthält
- **THEN** wird die LED in Weiß angesteuert

#### Scenario: CTB als Ersatzfarbe

- **WHEN** `fallback_color = "ctb"` gilt und die Antwort keine Farbe enthält
- **THEN** wird die LED in CTB angesteuert

### Requirement: LED-Kodierung nach MIDICraft v2

Für `protocol = "midicraft-v2"` SHALL `ma2pi` die LED-Note des Controls mit
einer Velocity senden: `0` für aus, `1–15` (`1 + Index`) für statisch dunkel
und `17–31` (`17 + Index`) für statisch hell. Die Palettenreihenfolge MUST
weiß, rot, orange, gelb, gelbgrün, grün, seegrün, cyan, lavendel, blau,
violett, magenta, pink, CTO, CTB sein (Index 0–14). Andere Velocity-Werte MUST
NOT gesendet werden.

#### Scenario: Helles Seegrün

- **WHEN** ein laufender Executor die Palettenfarbe seegrün (Index 6) hat
- **THEN** sendet `ma2pi` die Note des Controls mit Velocity 23

#### Scenario: Dunkles Weiß

- **WHEN** ein gestoppter Executor die Palettenfarbe weiß (Index 0) hat und
  `off_state = "dark"` gilt
- **THEN** sendet `ma2pi` die Note des Controls mit Velocity 1

#### Scenario: Helles Weiß

- **WHEN** ein laufender Executor die Palettenfarbe weiß (Index 0) hat
- **THEN** sendet `ma2pi` die Note des Controls mit Velocity 17

#### Scenario: Dunkles CTB

- **WHEN** ein gestoppter Executor die Farbe CTB (Index 14) hat und
  `off_state = "dark"` gilt
- **THEN** sendet `ma2pi` die Note des Controls mit Velocity 15

### Requirement: Nur Änderungen senden

`ma2pi` SHALL einen LED-Frame nur senden, wenn sich der LED-Zustand eines
Controls geändert hat, außer das Profil des Geräts schaltet das Auffrischen
ein. Wiederholte identische Zustände MUST dann keine Frames erzeugen. Die
Ausgabe MUST den Daemon nicht blockieren, auch wenn das Gerät nicht
schreibbereit ist.

#### Scenario: Unveränderter Zustand

- **WHEN** zwei aufeinanderfolgende Poll-Antworten denselben Zustand liefern
  und das Auffrischen aus ist
- **THEN** wird nach dem ersten Frame kein weiterer Frame gesendet

#### Scenario: Gerät nimmt nicht an

- **WHEN** das MIDI-Gerät Schreibversuche nicht annimmt
- **THEN** protokolliert `ma2pi` höchstens eine Warnung und verarbeitet
  weiterhin Eingaben

## ADDED Requirements

### Requirement: LED-Kodierung für ASL MK2

Für `protocol = "asl-mk2"` SHALL `ma2pi` je LED zwei Note-On auf der LED-Note
senden: Kanal 1 mit der Helligkeit, Kanal 2 mit dem Farbindex. Laufend gilt
`bright_level` (Default 127), gestoppt bei `off_state = "dark"` `dark_level`
(Default 25), bei `off_state = "off"` Helligkeit 0. Vor dem ersten LED-Frame
nach dem Öffnen MUST `9F 7F 7F` gesendet werden; `9F 7F 7E` MUST NOT nach
LED-Frames folgen.

#### Scenario: Laufender Executor an der ASL

- **WHEN** ein laufender Executor rot ist und die Farbtabelle Rot auf Index 48
  abbildet
- **THEN** sendet `ma2pi` `90 <Note> 127` und `91 <Note> 48`

#### Scenario: Gestoppter Executor, dunkel

- **WHEN** derselbe Executor stoppt und `off_state = "dark"` gilt
- **THEN** sendet `ma2pi` `90 <Note> 25` und `91 <Note> 48`

#### Scenario: Freigabe beim Öffnen

- **WHEN** das ASL-Gerät geöffnet wurde und der erste LED-Frame ansteht
- **THEN** geht `9F 7F 7F` vor diesem Frame hinaus, und nach dem Frame folgt
  kein `9F 7F 7E`

#### Scenario: Ein ASL-Frame im Takt

- **WHEN** zwei LEDs der ASL sich gleichzeitig ändern und
  `frame_interval_ms = 20` gilt
- **THEN** liegen zwischen dem Paar Note-On der ersten und dem Paar der zweiten
  LED mindestens 20 ms

#### Scenario: Helligkeit außerhalb des Bereichs

- **WHEN** `dark_level = 200` konfiguriert ist
- **THEN** lehnt `--check-config` die Konfiguration ab und nennt
  `led_feedback.dark_level`

### Requirement: Farbtabelle für asl-mk2

Ein Profil mit `asl-mk2` SHALL in `[profiles.<id>.led_feedback.colors]`
Palettennamen auf Farbindizes 0–127 abbilden können. Ohne Eintrag MUST die
gemessene Voreinstellung gelten: weiß 127, rot 48, orange 52, gelb 60,
gelbgrün 44, grün 12, seegrün 14, cyan 15, lavendel 43, blau 3, violett 35,
magenta 51, pink 59, CTO 62, CTB 47. Unbekannte Namen, Werte außerhalb 0–127
und `colors` bei anderen Protokollen MUST die Konfigurationsprüfung ablehnen.

#### Scenario: Eigener Index für Blau

- **WHEN** `colors.blue = 80` gesetzt ist und ein laufender Executor blau ist
- **THEN** sendet `ma2pi` auf Kanal 2 den Index 80

#### Scenario: Voreinstellung für Magenta

- **WHEN** ein laufender Executor magenta ist und `colors` keinen Eintrag für
  magenta enthält
- **THEN** sendet `ma2pi` auf Kanal 2 den Index 51

#### Scenario: Farbtabelle am Midicraft-Profil

- **WHEN** ein Profil mit `midicraft-v2` eine Tabelle `colors` enthält
- **THEN** lehnt `--check-config` die Konfiguration ab und nennt
  `led_feedback.colors`

### Requirement: Eine LED-Note gehört einer Funktion

Eine LED-Note eines Geräts SHALL entweder einer festen Funktion aus `[led]`
(Modus-, Fine- oder Nipple-Taste) oder dem Executor-Feedback gehören. Ist eine
von `[led]` belegte Note am selben Gerät zugleich LED-fähiges Feedback-Ziel,
MUST `--check-config` die Konfiguration ablehnen und beide Felder nennen.

#### Scenario: Nipple-Taste als Playback-Ziel

- **WHEN** `[led] nipple_note = 11` gilt und Note 11 der ASL ein LED-fähiges
  Button-Ziel in `[mapping.playbacks]` ist
- **THEN** lehnt `--check-config` die Konfiguration ab und nennt
  `led.nipple_note` und das Playback-Ziel

#### Scenario: Getrennte Noten

- **WHEN** `[led]` die Noten 9–11 belegt und das Executor-Feedback der ASL nur
  andere Noten nutzt
- **THEN** ist die Konfiguration gültig und beide Funktionen steuern ihre
  eigenen LEDs

### Requirement: LEDs ohne Ziel sind aus

Eine LED-fähige Note (laut `led_notes`) eines Geräts mit aktivem Feedback, die
in ihrer Bank kein Playback-Button-Ziel hat, SHALL ausgeschaltet werden: beim
Start des Feedbacks, nach jedem Wiederöffnen des Geräts, nach einem Reconnect
und nach einer Konfigurationsänderung. Noten, die `[led]` am selben Gerät
belegt, MUST davon ausgenommen sein.

#### Scenario: Unbelegte ENC-Taste

- **WHEN** Note 79 des ENC in `led_notes` steht, aber `mc_row2_5` kein
  Playback-Ziel hat
- **THEN** sendet `ma2pi` für Note 79 den Aus-Zustand des Protokolls
  (`midicraft-v2`: Velocity 0)

#### Scenario: Ziel wird entfernt

- **WHEN** das Playback-Ziel einer leuchtenden Taste per Konfiguration
  entfernt wird
- **THEN** wird ihre LED nach dem Übernehmen der Konfiguration ausgeschaltet

#### Scenario: Feste ASL-Taste bleibt unberührt

- **WHEN** die ASL `asl-mk2`-Feedback mit `led_notes = [9, 10, 11]` hat und
  `[led]` Note 9 als Modus-LED nutzt
- **THEN** sendet das Feedback für Note 9 keinen Aus-Zustand

### Requirement: Unbelegter Executor in der MA ist aus

`ma2pi` SHALL einen Executor als unbelegt erkennen, wenn die Antwort ihn mit
`isEmpty = true` meldet oder wenn sein Titel (`tt`) leer ist und er keine
`bottomButtons` hat; so liefert die onPC unbelegte Executoren (grau,
`bC = #404040`, ohne `isEmpty`). Die LED eines Ziels auf einem unbelegten
Executor MUST den Aus-Zustand des Protokolls erhalten.

#### Scenario: Leerer Executor in der Antwort der onPC

- **WHEN** die Antwort für Executor 103 `isRun = 0`, `tt = ""`,
  `bC = "#404040"` und keine `bottomButtons` enthält
- **THEN** sendet `ma2pi` für das Ziel auf Executor 103 den Aus-Zustand und
  nicht die dunkle Variante einer Farbe

#### Scenario: Belegter Executor ohne Bottom-Buttons

- **WHEN** ein Executor einen Titel hat, aber keine `bottomButtons` (z. B. ein
  breiter Fader-Executor)
- **THEN** gilt er als belegt und seine LED folgt Lauf-Zustand und Farbe

### Requirement: LEDs aller Bänke

Hat ein Gerät mit Feedback mehrere Bänke, SHALL `ma2pi` die LEDs aller Bänke
gleichzeitig führen: jede Bank auf ihrem MIDI-Kanal, mit ihrer Notenbelegung,
ihrem Executor-Offset und ihren `mapping.device_banks`-Overrides. Dies MUST
unabhängig davon gelten, welche Bank das Gerät gerade zeigt; `ma2pi` MUST die
angezeigte Bank nicht kennen.

#### Scenario: Nicht angezeigte Bank

- **WHEN** das ENC Bank 1 zeigt und der Executor von Bank 2, Taste 1, läuft
- **THEN** sendet `ma2pi` die LED für diese Taste auf Kanal 2

#### Scenario: Unbelegte Taste einer weiteren Bank

- **WHEN** eine LED-fähige Taste von Bank 3 kein Playback-Ziel hat
- **THEN** erhält sie auf Kanal 3 den Aus-Zustand

### Requirement: Periodisches Auffrischen

Ein Profil SHALL mit `[profiles.<id>.led_feedback] refresh_interval_ms` (`0` =
aus, sonst 200–60000, Default `0`) festlegen, in welchem Takt `ma2pi` alle
bekannten LED-Zustände des Geräts erneut sendet. `ma2pi` MUST dabei kanalweise
reihum vorgehen und nur einreihen, solange die Ausgabe des Geräts leer ist.
Ein geänderter Zustand MUST Vorrang vor einem Auffrisch-Frame derselben LED
haben, und eine unveränderte Poll-Antwort MUST einen eingereihten
Auffrisch-Frame nicht verwerfen.

#### Scenario: Bankwechsel am Gerät

- **WHEN** der Bediener am ENC auf Bank 2 wechselt und `refresh_interval_ms`
  1500 ist
- **THEN** zeigt das ENC die Farben von Bank 2 spätestens nach rund
  einem Intervall, ohne dass sich ein Executor geändert hat

#### Scenario: Aus

- **WHEN** `refresh_interval_ms = 0` ist
- **THEN** sendet `ma2pi` keine Auffrisch-Frames

### Requirement: Feste LED-Funktionen bleiben erhalten

Sind `[led]` und Executor-Feedback für dasselbe ASL-Gerät aktiv, SHALL `ma2pi`
beide über einen gemeinsamen Ausgabeweg bedienen. Das Starten, Stoppen oder
Umkonfigurieren des Feedbacks MUST die LED-Zustände der festen Funktionen nicht
zurücksetzen, und die festen Funktionen MUST die Feedback-LEDs nicht ändern.

#### Scenario: Moduswechsel bei laufendem Feedback

- **WHEN** das Feedback eine LED der ASL rot zeigt und der Encoder-Modus
  wechselt
- **THEN** wechselt die Modus-LED ihre Farbe, und die Feedback-LED bleibt rot

#### Scenario: Feedback wird abgeschaltet

- **WHEN** `[feedback] enabled` zur Laufzeit auf `false` gesetzt wird
- **THEN** behalten Modus-, Fine- und Nipple-LED ihren Zustand
