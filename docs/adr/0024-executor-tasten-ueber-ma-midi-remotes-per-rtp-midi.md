# 0024. Executor-Tasten über MA-MIDI-Remotes per RTP-MIDI

* Datum: 2026-11-27
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

Related to [0019. Absolute MIDI-Werte und Executor-Ziele über den Web Remote](0019-absolute-midi-werte-und-executor-ziele-ueber-den-web-remote.md)

Related to [0016. Hardkey-Injection über gma.canbus.hardkey im Command-Line-Modus](0016-hardkey-injection-ueber-gma-canbus-hardkey-im-command-line-modus.md)

Related to [0021. Executor-Feedback über Playback-Polling und MIDI-Duplex-Ausgabe](0021-executor-feedback-ueber-playback-polling-und-midi-duplex-ausgabe.md)

## Kontext und Problemstellung

Auf der Cherry werden Store, Assign und Edit als LUA-Hardkeys gedrückt
(ADR-0016); die Kommandozeile wartet danach auf ein Ziel. Eine ENC-Taste, die
als `playbacks_userInput` über den Web Remote geht (ADR-0019), löst den
Executor aber immer aus – die Kommandozeile bekommt kein Ziel. Eine echte
Konsolentaste und eine MIDI-Remote der MA verhalten sich dagegen reaktiv: Mit
`Store` davor wird gespeichert statt ausgelöst. Gemessen auf der onPC
(`add-midi-remote-executors`, verification.md): LUA-Store, danach eine Note auf
eine MIDI-Remote, speichert in den leeren Executor.

## Entscheidungstreiber

* Executor-Tasten sollen auf die Kommandozeile reagieren wie Konsolentasten
* Der LUA-Hardkey-Pfad der Cherry bleibt unverändert
* Farben, Zustände und Fader bleiben beim Web Remote (Polling, 14 Bit statt 7)
* Kein Pflegeaufwand in der Show: die Remote-Tabelle folgt der Konfiguration
* Fremde Einträge der Show bleiben unangetastet
* Kein stilles Ausweichen auf einen Transport mit anderem Verhalten

## Betrachtete Optionen

* Weiter `playbacks_userInput` für alle Executor-Ziele
* Tasten per Kommandozeile (`Go Executor …`) emulieren
* Tasten als MIDI-Noten über RTP-MIDI an MA-MIDI-Remotes, Tabelle per Telnet
* Tasten und Fader über MIDI-Remotes

## Entscheidung

Executor-**Tasten** gehen als MIDI-Noten an MIDI-Remotes der MA: Note-On 127
beim Drücken, Note-Off beim Loslassen (gemessen: Note-Off wirkt als Release für
Flash). `ma2pi` ist selbst AppleMIDI-Initiator und lädt die rtpMIDI-Session
auf dem onPC-Rechner ein; RTP-MIDI geht ohne Recovery-Journal, jedes Note-Off
wird nach 20 ms einmal wiederholt. **Fader und Encoder** bleiben beim Web Remote.

Jedes Tastenziel `(page, executor, button)` bekommt aus reservierten Kanälen
(`[midi_remote].channels`, Default 16) eine feste Adresse, sortiert und damit
stabil. `ma2pi` gleicht die Remote-Tabelle der MA per Telnet ab: nach jeder
Konfigurationsaktivierung, nach Verlust der Web-Remote-Sitzung und bis zum
Erfolg mit Backoff bis 10 s. Besitzmarke ist allein der Kanal; Einträge auf
anderen Kanälen werden nie verändert. Weil die MA ungültige `assign`-Befehle
still schluckt und nach `delete` nachnummeriert, liest der Abgleich nach dem
Schreiben zurück und löscht zuletzt und absteigend. Eine Taste geht nur raus,
wenn die Sitzung steht und ihr Eintrag bestätigt ist; sonst wird sie verworfen
und einmal je Ausfall und Ziel gewarnt.

MIDI-Ziele werden nicht über die Executor-Topologie umgeleitet: Eine Remote auf
einem verdeckten Slot eines breiten Executors wirkt wie die Konsolentaste
dieser Spalte (gemessen).

Transport je Ziel: `transport = "midi" | "web"`, ohne Angabe `midi` für Tasten,
wenn `[midi_remote].enabled = true`, sonst `web`.

### Konsequenzen

* Gut, weil Store, Assign, Edit, Copy usw. von der Cherry mit ENC-Tasten
  funktionieren wie an der Konsole.
* Gut, weil die Show nicht von Hand gepflegt wird und fremde Remotes bleiben.
* Gut, weil Feedback, Farben und Fader beim bewährten Web-Remote-Pfad bleiben.
* Schlecht, weil die onPC nur einen MIDI-Eingang hat: Er muss auf die
  rtpMIDI-Session stehen, ein direkt angeschlossenes MIDI-Gerät geht dann nur
  noch über die „Live routings“ von rtpMIDI.
* Schlecht, weil Telnet in der MA aktiviert sein muss (`Login Enabled`) und
  `ma2pi` die Show verändert; Speichern der Show bleibt Sache des Nutzers.
* Schlecht, weil rtpMIDI (Tobias Erichsen) auf dem onPC-Rechner installiert und
  dessen UDP-Ports 5004/5005 frei sein müssen (Screen-Helper deshalb auf 5010).
* Schlecht, weil ein Paketverlust ohne Journal nicht repariert wird; das doppelte
  Note-Off verhindert hängende Flashes, ein verlorenes Note-On bleibt verloren.

### Bestätigung

Accepted nach der Hardware-Abnahme: Store, Assign und Edit von der Cherry plus
ENC-Taste, normales Auslösen, Flash mit Release, LED-Feedback weiter aktiv,
Fader weiter über den Web Remote (Task 6.2 von `add-midi-remote-executors`).

## Vor- und Nachteile der Optionen

### Weiter `playbacks_userInput`

* Gut, weil nichts Neues nötig ist.
* Schlecht, weil der Web Remote Executor-Tasten immer auslöst und die
  Kommandozeile kein Ziel bekommt.

### Kommandozeile emulieren

* Gut, weil der Web Remote Befehle bereits sendet.
* Schlecht, weil jede Tastenfunktion (Go, Flash, Toggle, Swop …) und jeder
  Kommandozeilen-Zustand nachgebaut werden müsste; Flash-Release fehlt.

### Tasten über MIDI-Remotes

* Gut, weil die MA die Note genau wie eine Konsolentaste behandelt.
* Schlecht, weil RTP-MIDI, Telnet und eine Remote-Tabelle dazukommen.

### Tasten und Fader über MIDI-Remotes

* Gut, weil ein einziger Transport für alles.
* Schlecht, weil Fader nur 7 Bit über die Velocity bekommen (gemessen, CC wird
  ignoriert) und die Kommandozeile für Fader keine Rolle spielt.

## Weitere Informationen

* Verwandt: ADR-0016 (LUA-Hardkeys), ADR-0019 (Executor-Ziele über den Web
  Remote, für Fader und Encoder weiter gültig), ADR-0021 (Feedback)
* Change: `add-midi-remote-executors`
* Messung: `openspec/changes/add-midi-remote-executors/verification.md`
