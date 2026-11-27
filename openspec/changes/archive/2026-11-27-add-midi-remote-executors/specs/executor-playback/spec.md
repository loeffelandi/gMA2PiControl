## ADDED Requirements

### Requirement: Transport je Playback-Ziel

Ein Playback-Ziel SHALL optional `transport = "midi"|"web"` angeben. Ohne
Angabe MUST ein Button-Ziel `midi` verwenden, wenn `[midi_remote] enabled = true`
gilt, sonst `web`; ein Fader-Ziel MUST ohne Angabe `web` verwenden.
`transport = "midi"` bei `enabled = false` oder bei einem Fader-Ziel MUST die
Konfigurationsprüfung mit Nennung von Control und Feld ablehnen.

#### Scenario: Button-Ziel ohne Angabe

- **WHEN** `[midi_remote] enabled = true` gilt und ein Button-Ziel keinen
  `transport` angibt
- **THEN** gehen seine Tastenereignisse als MIDI-Nachrichten an die MA

#### Scenario: Fader-Ziel ohne Angabe

- **WHEN** `[midi_remote] enabled = true` gilt und ein Fader-Ziel keinen
  `transport` angibt
- **THEN** gehen seine Werte weiter als `playbacks_userInput` mit `faderValue`

#### Scenario: MIDI ohne Ausgang

- **WHEN** ein Ziel `transport = "midi"` angibt und `[midi_remote]
  enabled = false` gilt
- **THEN** lehnt die Konfigurationsprüfung die Konfiguration ab und nennt das
  Control und `transport`

#### Scenario: Fader über MIDI

- **WHEN** ein Fader-Ziel `transport = "midi"` angibt
- **THEN** lehnt die Konfigurationsprüfung die Konfiguration ab und nennt das
  Control und `transport`

### Requirement: Keine Umleitung breiter Executoren bei MIDI

Ein Button-Ziel mit Transport `midi` SHALL unverändert an seinen konfigurierten
Executor gehen, auch wenn dieser Slot von einem breiten Executor verdeckt ist.
Die MA MUST die Umleitung dann selbst vornehmen, mit der Tastenfunktion der
verdeckten Spalte wie bei einer Konsolentaste. Ziele mit Transport `web` MUST
weiter wie bisher auf den führenden Executor umgeleitet werden.

#### Scenario: Verdeckter Slot über MIDI

- **WHEN** Exec 115 auf Page 2 von dem breiten Exec 114 verdeckt ist und ein
  Button-Ziel `page = 2`, `executor = 115`, Transport `midi` gedrückt wird
- **THEN** sendet `ma2pi` die Note der Adresse von 2.115, und die MIDI-Remote
  zeigt auf Executor 115

## MODIFIED Requirements

### Requirement: Tastenereignisse auf Executor-Buttons

Ein Tastenereignis auf ein Ziel mit Transport `web` SHALL bei gedrückter Taste
einen `playbacks_userInput`-Frame mit `pressed = true` und `released = false`
senden und beim Loslassen einen Frame mit `pressed = false` und
`released = true`. Page, Executor und Button MUST von 1-basiert auf 0-basiert
umgerechnet werden; die Reihenfolge von Press und Release MUST erhalten bleiben.
Ziele mit Transport `midi` MUST stattdessen über den MIDI-Remote-Ausgang gehen.

#### Scenario: Executor-Button drücken

- **WHEN** ein Control mit Button-Ziel und Transport `web` den Wert 1 liefert
- **THEN** sendet `ma2pi` genau einen Frame mit `execIndex = executor - 1`,
  `pageIndex = page - 1`, `buttonId = button - 1`, `pressed = true` und
  `released = false`

#### Scenario: Executor-Button loslassen

- **WHEN** dasselbe Control den Wert 0 liefert
- **THEN** sendet `ma2pi` genau einen Frame mit `pressed = false` und
  `released = true`

#### Scenario: Zweiter oder dritter Executor-Button

- **WHEN** das Ziel `button = 2` oder `button = 3` angibt
- **THEN** enthält der Frame `buttonId = 1` beziehungsweise `buttonId = 2`

#### Scenario: Button-Ziel mit Transport midi

- **WHEN** ein Control mit Button-Ziel und Transport `midi` den Wert 1 liefert
- **THEN** sendet `ma2pi` keinen `playbacks_userInput`-Frame, sondern ein
  Note-On auf der Adresse des Ziels

### Requirement: Vorrang der Playback-Ziele

Ein Control mit Playback-Ziel SHALL dieses Ziel adressieren und nicht zusätzlich
über die bestehende Tasten- oder Encoder-Zuordnung verarbeitet werden. Controls
ohne Playback-Ziel MUST unverändert an die bestehende Zuordnung gehen.

#### Scenario: Control mit Playback-Ziel

- **WHEN** ein Control sowohl ein Playback-Ziel als auch eine Tasten-Zuordnung
  besitzt
- **THEN** sendet `ma2pi` ausschließlich Executor-Eingaben (Executor-Frames oder
  MIDI-Nachrichten je nach Transport) und keine Hardkey- oder Command-Frames

#### Scenario: Control ohne Playback-Ziel

- **WHEN** ein Control keine Playback-Zuordnung besitzt
- **THEN** verhält es sich wie bisher und wird über Hardkey, Command oder
  Encoder verarbeitet
