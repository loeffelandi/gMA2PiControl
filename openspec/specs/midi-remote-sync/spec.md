# midi-remote-sync Specification

## Purpose

Hält die MIDI-Remotes der MA passend zu den Playback-Zielen von `ma2pi`, indem
`ma2pi` sie per Telnet anlegt, abgleicht und prüft, ohne fremde Einträge der
Show zu verändern.

## Requirements

### Requirement: Telnet-Zugang zur MA

Die Konfiguration SHALL in `[midi_remote]` die Felder `sync` (`"auto"`,
`"check"` oder `"off"`, Default `"auto"`) und `telnet_port` (Default 30000)
erlauben. `ma2pi` MUST sich mit Host und Benutzer der MA-Verbindung anmelden.
Schlägt die Anmeldung fehl, MUST der Status den Grund zeigen.

#### Scenario: Telnet in der MA aus

- **WHEN** die MA auf `telnet_port` keine Verbindung annimmt
- **THEN** zeigt der Status „Telnet nicht erreichbar" und alle Ziele mit
  Transport `midi` gelten als nicht abgeglichen

#### Scenario: Ungültiger Modus

- **WHEN** `sync = "sometimes"` konfiguriert ist
- **THEN** lehnt die Konfigurationsprüfung ab und nennt `midi_remote.sync`

### Requirement: Abgleich der Remote-Tabelle

Bei `sync = "auto"` SHALL `ma2pi` nach jeder Konfigurationsaktivierung und nach
jedem Neuaufbau der Telnet-Verbindung die MIDI-Remotes der MA lesen und für
jedes Ziel mit Transport `midi` einen Eintrag mit dessen Adresse und Executor
anlegen oder korrigieren. Einträge auf reservierten Kanälen ohne Ziel MUST
entfernt werden.

#### Scenario: Neues Ziel

- **WHEN** ein Control neu auf `page = 1`, `executor = 102`, `button = 1` mit
  Transport `midi` gelegt und die Konfiguration aktiviert wird
- **THEN** existiert danach in der MA eine MIDI-Remote mit der Adresse dieses
  Ziels auf Executor 1.102, Button 1

#### Scenario: Ziel entfernt

- **WHEN** das letzte Control mit diesem Ziel entfernt und die Konfiguration
  aktiviert wird
- **THEN** entfernt `ma2pi` die zugehörige MIDI-Remote

### Requirement: Fremde Einträge bleiben unberührt

`ma2pi` SHALL nur MIDI-Remotes auf den reservierten Kanälen anlegen, ändern oder
entfernen. Einträge auf anderen Kanälen MUST unverändert bleiben, auch wenn sie
dieselben Executoren adressieren.

#### Scenario: Von Hand angelegte Remote

- **WHEN** die Show eine MIDI-Remote auf Kanal 1 enthält und
  `channels = [16]` gilt
- **THEN** bleibt dieser Eintrag nach dem Abgleich unverändert

### Requirement: Nur prüfen

Bei `sync = "check"` SHALL `ma2pi` die Tabelle lesen und Abweichungen melden,
ohne sie zu ändern. Bei `sync = "off"` MUST `ma2pi` keine Telnet-Verbindung
aufbauen und alle Ziele als abgeglichen behandeln.

#### Scenario: Abweichung im Prüfmodus

- **WHEN** `sync = "check"` gilt und für ein Ziel die MIDI-Remote fehlt
- **THEN** zeigt der Status das Ziel als nicht abgeglichen, `ma2pi` schreibt
  nichts in die MA und sendet für dieses Ziel nichts

#### Scenario: Abgleich aus

- **WHEN** `sync = "off"` gilt
- **THEN** sendet `ma2pi` MIDI-Nachrichten für alle Ziele mit Transport `midi`,
  ohne die Tabelle zu prüfen

### Requirement: Ergebnis im Status

Nach jedem Abgleich SHALL der Status die Anzahl angelegter, geänderter,
entfernter und fehlerhafter Einträge sowie den Zeitpunkt zeigen. Fehlgeschlagene
Einträge MUST mit Ziel und Antwort der MA geloggt werden.

#### Scenario: Teilweise fehlgeschlagen

- **WHEN** die MA einen von drei Einträgen mit einer Fehlermeldung ablehnt
- **THEN** zeigt der Status 2 angelegt und 1 fehlerhaft, und das abgelehnte Ziel
  gilt als nicht abgeglichen
