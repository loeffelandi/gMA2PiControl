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
- **THEN** fragt `ma2pi` keine Playbacks ab und sendet keine LED-Frames

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
Feedback ausgegeben wird und mit welchem Protokoll. Derzeit MUST nur
`protocol = "midicraft-v2"` gültig sein. Die optionale Liste `led_notes` MUST
die Noten benennen, die tatsächlich LEDs besitzen; fehlt sie, gelten alle
Profil-Noten, die ein Button-Ziel haben, als LED-fähig. Feedback MUST
ausschließlich an Controls gehen, deren Note im Profil als LED-fähig gilt.

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

### Requirement: Polling der Executor-Zustände

Bei aktivem Feedback SHALL `ma2pi` die Zustände der in `[mapping.playbacks]`
referenzierten Button-Ziele regelmäßig über `requestType = "playbacks"`
abfragen. Pro Page MUST höchstens eine Anfrage gleichzeitig offen sein; eine
neue Anfrage MUST erst nach der Antwort oder einem Timeout folgen. Ohne
LED-fähiges Button-Ziel MUST keine Anfrage gesendet werden.

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

- **WHEN** alle Playback-Ziele auf Fader oder auf Noten ohne LED zeigen
- **THEN** unterbleibt das Polling vollständig

### Requirement: Abfrage der aktuellen Master-Page

Ziele mit `page = "current"` MUST mit `pageIndex = -1` abgefragt werden; die
tatsächliche Page MUST aus der Antwort (`iPage`, 0-basiert; Config-Page =
`iPage + 1`) übernommen werden. Ein Seitenwechsel auf der MA MUST ohne
Konfigurationsänderung wirksam werden.

#### Scenario: Seitenwechsel auf der MA

- **WHEN** die MA während des Betriebs auf eine andere Master-Page wechselt
- **THEN** zeigt die LED im nächsten Poll-Zyklus den Zustand des Executors auf
  der neuen Page

#### Scenario: Feste Page

- **WHEN** ein Ziel `page = 2` angibt
- **THEN** enthält die Anfrage `pageIndex = 1`, unabhängig von der Page auf der MA

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
nächstliegende der 13 MIDICraft-Palettenfarben abgebildet werden; fehlt `bC`
oder ist es nicht auflösbar (auch `#000000`), MUST `bdC` verwendet werden. Ist
auch `bdC` nicht auflösbar, MUST `fallback_color` gelten.

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

### Requirement: LED-Kodierung nach MIDICraft v2

Für `protocol = "midicraft-v2"` SHALL `ma2pi` die LED-Note des Controls mit
einer Velocity senden: `0` für aus, `1–13` für statisch dunkel in
Palettenreihenfolge und `15–27` für statisch hell in Palettenreihenfolge. Die
Palettenreihenfolge MUST weiß, rot, orange, gelb, gelbgrün, grün, seegrün,
cyan, lavendel, blau, violett, magenta, pink sein. Andere Velocity-Werte MUST
NOT gesendet werden.

#### Scenario: Helles Seegrün

- **WHEN** ein laufender Executor die Palettenfarbe seegrün (Index 6) hat
- **THEN** sendet `ma2pi` die Note des Controls mit Velocity 21

#### Scenario: Dunkles Weiß

- **WHEN** ein gestoppter Executor die Palettenfarbe weiß (Index 0) hat und
  `off_state = "dark"` gilt
- **THEN** sendet `ma2pi` die Note des Controls mit Velocity 1

### Requirement: Nur Änderungen senden

`ma2pi` SHALL einen LED-Frame nur senden, wenn sich der LED-Zustand eines
Controls geändert hat. Wiederholte identische Zustände MUST keine Frames
erzeugen. Die Ausgabe MUST den Daemon nicht blockieren, auch wenn das Gerät
nicht schreibbereit ist.

#### Scenario: Unveränderter Zustand

- **WHEN** zwei aufeinanderfolgende Poll-Antworten denselben Zustand liefern
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
