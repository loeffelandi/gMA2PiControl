# executor-feedback Specification

## Purpose
Zeigt den Zustand von grandMA2-Executoren über die LEDs angeschlossener
MIDI-Controller an, indem `ma2pi` den Executor-Status pollt und daraus
LED-Frames erzeugt.

## Requirements

### Requirement: Konfiguration des Executor-Feedbacks

Executor-Feedback SHALL standardmäßig deaktiviert sein und nur bei
`enabled = true` aktiv werden. `[feedback]` MUST `enabled`, `interval_ms`
(100–2000, Default 250), `off_state` (`off` oder `dark`, Default `dark`) und
`fallback_color` (Palettenname, Default `white`) akzeptieren. Unbekannte
Schlüssel, unbekannte Farbnamen oder Werte außerhalb der Bereiche MUST die
Konfigurationsprüfung mit Nennung des Feldes ablehnen.

#### Scenario: Feedback ist ausgeschaltet

- **WHEN** `[feedback]` fehlt oder `enabled = false` gesetzt ist
- **THEN** sendet `ma2pi` keine LED-Frames und fragt keine Playbacks für LEDs ab;
  Abfragen für die Executor-Topologie bleiben davon unberührt und richten sich
  nach `[mapping] combined_executors`

#### Scenario: Ungültiges Intervall

- **WHEN** `interval_ms = 50` konfiguriert ist
- **THEN** lehnt `--check-config` die Konfiguration ab und nennt
  `feedback.interval_ms`

#### Scenario: Gültige Konfiguration

- **WHEN** `enabled = true`, `interval_ms = 300`, `off_state = "off"` und
  `fallback_color = "white"` gesetzt sind
- **THEN** startet der Daemon mit aktivem Feedback und fragt höchstens alle
  300 ms neue Zustände ab

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

### Requirement: Polling der Executor-Zustände

Bei aktivem Feedback SHALL `ma2pi` die Zustände der in `[mapping.playbacks]`
referenzierten Button-Ziele regelmäßig über `requestType = "playbacks"`
abfragen. Pro Page MUST höchstens eine Anfrage gleichzeitig offen sein; eine
neue Anfrage MUST erst nach der Antwort oder einem Timeout folgen. Ohne
LED-fähiges Button-Ziel und bei `combined_executors = "off"` MUST keine Anfrage
gesendet werden. Ein einziger Poller MUST die Antworten für LEDs und Topologie
verarbeiten.

#### Scenario: Regelmäßige Abfrage

- **WHEN** Feedback aktiv ist und ein Button-Ziel auf Executor 3 der Page 1
  zeigt
- **THEN** fragt `ma2pi` wiederholt genau den Executor-Bereich um Executor 3
  der Page 1 ab

#### Scenario: Antwort hängt

- **WHEN** die onPC auf eine Playbacks-Anfrage nicht antwortet
- **THEN** sendet `ma2pi` keine zweite Anfrage für dieselbe Page, bis der
  Timeout erreicht ist

#### Scenario: Kein LED-fähiges Ziel

- **WHEN** alle Playback-Ziele auf Fader oder auf Noten ohne LED zeigen und
  `combined_executors = "off"` gilt
- **THEN** unterbleibt das Polling vollständig

#### Scenario: Ein Poller für beide Zwecke

- **WHEN** LED-Feedback und Topologie aktiv sind
- **THEN** liest genau ein Poller die Antworten und versorgt beide Verbraucher

### Requirement: Abfrage der aktuellen Master-Page

Ziele mit `page = "current"` MUST mit `pageIndex = -1` abgefragt werden. Die MA
antwortet darauf mit den Daten der aktuellen Master-Page und dem Platzhalter
`iPage = 0`; die tatsächliche Master-Page enthält die Antwort nicht. Bei einer
Anfrage mit explizitem `pageIndex = N` antwortet die MA mit `iPage = N + 1`. Die
Zuordnung MUST dieser Messung folgen. Ein Seitenwechsel auf der MA MUST ohne
Konfigurationsänderung wirksam werden.

#### Scenario: Seitenwechsel auf der MA

- **WHEN** die MA während des Betriebs auf eine andere Master-Page wechselt
- **THEN** zeigt die LED im nächsten Poll-Zyklus den Zustand des Executors auf
  der neuen Page

#### Scenario: Feste Page

- **WHEN** ein Ziel `page = 2` angibt
- **THEN** enthält die Anfrage `pageIndex = 1`, unabhängig von der Page auf der MA,
  und eine Antwort mit `iPage = 2` wird diesem Ziel zugeordnet

#### Scenario: Antwort einer anderen Page

- **WHEN** auf eine Anfrage für Page 2 eine Antwort mit `iPage = 1` eintrifft
- **THEN** wird sie dem Block für Page 2 nicht zugeordnet

#### Scenario: Antwort für die aktuelle Page

- **WHEN** auf eine Anfrage mit `pageIndex = -1` eine Antwort mit `iPage = 0`
  eintrifft
- **THEN** wird sie dem Block für `"current"` zugeordnet und nie einem Ziel mit
  fester Page

#### Scenario: Feste Page erhält keine Antwort für current

- **WHEN** eine Antwort mit `iPage = 0` eintrifft und nur Blöcke für feste Pages
  offen sind
- **THEN** wird sie keinem dieser Blöcke zugeordnet

### Requirement: LED-Zustand aus Executor-Zustand

Ein Button-Ziel mit LED-fähiger Note SHALL hell leuchten, solange der Executor
läuft, und im konfigurierten Aus-Zustand leuchten, wenn er nicht läuft:
`dark` MUST die dunkle Variante der Executor-Farbe senden, `off` MUST die LED
ausschalten. Für einen laufenden Executor ohne ermittelbare Farbe MUST
`fallback_color` verwendet werden.

#### Scenario: Executor läuft

- **WHEN** der Executor `isRun = true` meldet und die Farbe Rot ermittelt wurde
- **THEN** sendet `ma2pi` die helle rote Variante an die LED des Controls

#### Scenario: Executor ist gestoppt

- **WHEN** derselbe Executor `isRun = false` meldet und `off_state = "dark"`
  konfiguriert ist
- **THEN** sendet `ma2pi` die dunkle rote Variante an die LED

#### Scenario: Aus-Zustand ist aus

- **WHEN** `off_state = "off"` konfiguriert ist und der Executor nicht läuft
- **THEN** sendet `ma2pi` Velocity 0 an die LED

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

### Requirement: Verbindungsverlust und fehlendes Gerät

Bei fehlender Web-Remote-Verbindung MUST `ma2pi` keine neuen LED-Zustände
senden; der zuletzt gesendete Zustand bleibt bestehen. Nach erfolgreichem
Reconnect MUST der Zustand vollständig neu ermittelt werden. Fehlt das
MIDI-Gerät, MUST der Daemon weiterlaufen und die Ausgabe wieder aufnehmen,
sobald das Gerät erscheint.

#### Scenario: onPC trennt die Verbindung

- **WHEN** die WebSocket-Verbindung während einer laufenden Show abbricht
- **THEN** ändern sich die LEDs nicht weiter und nach dem Reconnect wird der
  aktuelle Zustand erneut gesendet

#### Scenario: Controller wird abgezogen

- **WHEN** das MIDI-Gerät während des Betriebs verschwindet
- **THEN** läuft der Daemon ohne Abbruch weiter und sendet nach dem
  Wiedereinstecken die aktuellen Zustände

### Requirement: Dry-Run ohne Hardwareausgabe

Im Dry-Run MUST `ma2pi` keine MIDI-Frames an das Gerät schreiben. Jeder
beabsichtigte LED-Frame MUST mit Note, Velocity und Control protokolliert
werden.

#### Scenario: Dry-Run mit aktivem Feedback

- **WHEN** der Daemon mit `--dry-run` und aktivem Feedback läuft
- **THEN** erscheinen die LED-Frames nur im Log und das Gerät bleibt unberührt

### Requirement: Gerätebezogener Replug-Abgleich und Fortschritts-Stauprüfung

`ExecutorFeedback` SHALL geöffnete MIDI-Geräte über eine pro Öffnung steigende
Handle-Generation abgleichen und Zustände nur für das geänderte Gerät
zurücksetzen. Die Stau-Erkennung MUST prüfen, ob ausstehende Bytes über das
Stau-Fenster hinweg **ohne Abnahme** stehen bleiben, damit kontinuierliche
LED-Updates keinen Fehlalarm auslösen.

#### Scenario: Controller wird auf denselben `/dev/snd/midiC*D*`-Pfad neu gesteckt

- **WHEN** ein MIDI-Controller zwischen zwei Zyklen abgezogen und unter demselben
  Pfad neu geöffnet wird
- **THEN** erkennt `ExecutorFeedback` die neue Generation, hebt eine Stau-Pause
  auf und sendet alle LEDs dieses Geräts neu

#### Scenario: Kontinuierliche LED-Updates lösen keinen Fehl-Stau aus

- **WHEN** über mehr als zwei Sekunden fortlaufend Frames gesendet und vom Gerät
  abgenommen werden
- **THEN** bleibt die LED-Ausgabe aktiv

### Requirement: Leere Executor-Seiten und Bank-Auflösung im Feedback

Unbelegte Executoren ohne `isRun` in `playbacks`-Antworten MUST als `off`
gelten, und `"current"`-Blöcke MUST späte Antworten fester Seiten verwerfen.
`build_feedback_targets` SHALL den Bank-Kanal (`0x90 | (channel - 1)`),
Bank-Offsets und `mapping.device_banks`-Overrides berücksichtigen.

#### Scenario: Wechsel auf leere Executor-Page schaltet LEDs aus

- **WHEN** alle abgefragten Executoren einer Seite unbelegt sind
- **THEN** entsteht kein Timeout und die zugehörigen LEDs wechseln auf `off`

#### Scenario: Bank auf Kanal 2 erhält LED-Frames auf Kanal 2

- **WHEN** eine Bank auf MIDI-Kanal 2 gebunden ist
- **THEN** adressiert `ExecutorFeedback` deren LED-Noten auf Kanal 2

### Requirement: Aktuelle Master-Page bleibt auf Seiten mit festem Ziel aktiv

Ein Abfrageblock mit `page = "current"` SHALL Antworten der grandMA2 auch dann
akzeptieren, wenn die aktuell gewählte Master-Page mit einer Seite übereinstimmt,
für die zusätzlich ein festes Playback-Ziel konfiguriert ist.

#### Scenario: Master-Page wechselt auf eine ebenfalls fest überwachte Seite

- **WHEN** sowohl `page = "current"` als auch `page = 2` überwacht werden und
  der Bediener in der onPC auf Master-Page 2 wechselt
- **THEN** verarbeitet `ExecutorFeedback` die `"current"`-Antwort für Seite 2
  ohne Timeout und aktualisiert die `"current"`-LEDs weiter

### Requirement: Feedback je Gerät schaltbar

`[profiles.<id>.led_feedback]` SHALL den optionalen Schlüssel `enabled`
(Bool, Default `true`) akzeptieren. Bei `enabled = false` MUST `ma2pi` für
Geräte dieses Profils keine LED-Ziele bilden, keine Playbacks nur für dieses
Gerät abfragen und keine LED-Frames senden. Andere Geräte MUST unbeeinflusst
bleiben.

#### Scenario: ENC aus, ASL an

- **WHEN** `[feedback] enabled = true` gilt, `midicraft-enc` hat
  `led_feedback.enabled = false` und `asl-mk2-e4b3` hat Feedback aktiv
- **THEN** sendet `ma2pi` LED-Frames nur an die ASL und keine an den ENC

#### Scenario: Alle Profile aus

- **WHEN** jedes Profil mit `led_feedback` hat `enabled = false`
- **THEN** unterbleibt das Polling wie bei „kein LED-fähiges Ziel“

#### Scenario: Eingabe bleibt unberührt

- **WHEN** das Feedback eines Geräts abgeschaltet ist
- **THEN** werden Eingaben dieses Geräts unverändert verarbeitet

### Requirement: Getaktete LED-Ausgabe

`ma2pi` SHALL LED-Frames je Gerät mit einem Mindestabstand senden, der über
`frame_interval_ms` in `[profiles.<id>.led_feedback]` festgelegt wird (ganze
Zahl 1–500, Default 20). Pro Gerät MUST höchstens ein Frame je Intervall das
Gerät erreichen. Ein neuer Zustand für eine LED, deren Frame noch aussteht, MUST
den offenen ersetzen. Werte außerhalb des Bereichs MUST die
Konfigurationsprüfung mit Nennung des Feldes ablehnen.

#### Scenario: Startzustand verteilt

- **WHEN** beim Start 15 LEDs gesetzt werden müssen und `frame_interval_ms = 20`
  gilt
- **THEN** liegen zwischen zwei Frames an dasselbe Gerät mindestens 20 ms

#### Scenario: Offener Frame wird ersetzt

- **WHEN** für eine LED ein Frame aussteht und sich ihr Zustand erneut ändert
- **THEN** wird nur der neueste Zustand gesendet

#### Scenario: Gerät beeinflusst anderes Gerät nicht

- **WHEN** der Ausgabestau eines Geräts länger dauert als das Intervall eines
  anderen
- **THEN** sendet das andere Gerät weiter im eigenen Takt

#### Scenario: Ungültiges Intervall

- **WHEN** `frame_interval_ms = 0` konfiguriert ist
- **THEN** lehnt `--check-config` die Konfiguration ab und nennt
  `led_feedback.frame_interval_ms`

### Requirement: Ausgabestau pausiert die LED-Ausgabe

Meldet das Betriebssystem für ein MIDI-Gerät länger als 2 Sekunden
ausstehende Ausgabe, die das Gerät nicht abnimmt, oder lehnt es Schreibversuche
dauerhaft ab, SHALL `ma2pi` die LED-Ausgabe für dieses Gerät pausieren und
genau eine Warnung mit Gerät und Anzahl ausstehender Bytes protokollieren.
Eingaben dieses Geräts MUST weiter verarbeitet werden. Nach dem erneuten
Öffnen des Geräts MUST die Ausgabe wieder aufgenommen und der vollständige
Zustand neu gesendet werden.

#### Scenario: Gerät nimmt nichts mehr ab

- **WHEN** ein Gerät 2 Sekunden lang ausstehende Ausgabe nicht abnimmt
- **THEN** sendet `ma2pi` keine weiteren LED-Frames an dieses Gerät und
  protokolliert eine Warnung

#### Scenario: Eingabe läuft weiter

- **WHEN** die LED-Ausgabe eines Geräts pausiert ist
- **THEN** werden Eingaben dieses Geräts weiter zugestellt

#### Scenario: Gerät wird neu geöffnet

- **WHEN** ein pausiertes Gerät nach Disconnect erneut geöffnet wird
- **THEN** nimmt `ma2pi` die Ausgabe wieder auf und sendet den aktuellen
  Zustand aller LEDs erneut

#### Scenario: Statusabfrage nicht verfügbar

- **WHEN** das Betriebssystem keinen Ausgabestatus liefert
- **THEN** gilt das Gerät als nicht gestaut und `ma2pi` verhält sich wie bisher

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

### Requirement: LED überdeckter Slots

Die LED eines Button-Ziels auf einem überdeckten Slot SHALL Laufzustand und
Farbe des führenden Executors zeigen, weil für den überdeckten Slot keine eigene
Antwort existiert. Hat der führende Executor keinen ermittelbaren Zustand, MUST
die LED unverändert bleiben.

#### Scenario: Führender Executor läuft

- **WHEN** Exec 114 `isRun = true` und `bC = "#ff0000"` meldet und ein
  Button-Ziel auf dem überdeckten Slot Exec 115 liegt
- **THEN** sendet `ma2pi` an die LED dieses Ziels die helle rote Variante

#### Scenario: Führender Executor gestoppt

- **WHEN** Exec 114 nicht läuft und `off_state = "dark"` gilt
- **THEN** zeigt die LED des Ziels auf Exec 115 die dunkle Variante derselben
  Farbe

#### Scenario: Zustand unbekannt

- **WHEN** die Antwort keinen Zustand für den führenden Executor enthält
- **THEN** wird für das Ziel auf dem überdeckten Slot kein LED-Frame gesendet
