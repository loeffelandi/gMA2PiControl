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

Bei `sync = "auto"` SHALL `ma2pi` die MIDI-Remotes der MA lesen und für jedes
Ziel mit Transport `midi` einen Eintrag mit dessen Adresse und Executor anlegen
oder korrigieren. Einträge auf reservierten Kanälen ohne Ziel MUST entfernt
werden. Der Abgleich MUST nach jeder Konfigurationsaktivierung und einmal je
Aufbau der Web-Remote-Sitzung laufen. Er MUST NOT periodisch wiederholt werden.

#### Scenario: Neues Ziel

- **WHEN** ein Control neu auf `page = 1`, `executor = 102`, `button = 1` mit
  Transport `midi` gelegt und die Konfiguration aktiviert wird
- **THEN** existiert danach in der MA eine MIDI-Remote mit der Adresse dieses
  Ziels auf Executor 1.102, Button 1

#### Scenario: Ziel entfernt

- **WHEN** das letzte Control mit diesem Ziel entfernt und die Konfiguration
  aktiviert wird
- **THEN** entfernt `ma2pi` die zugehörige MIDI-Remote

#### Scenario: Show neu geladen

- **WHEN** die onPC ein anderes Showfile lädt und die MIDI-Remotes der
  reservierten Kanäle fehlen
- **THEN** legt `ma2pi` sie beim nächsten Abgleich (nächster Connect oder
  Knopf) erneut an, ohne dass die Konfiguration geändert werden muss

#### Scenario: Sitzung steht wieder

- **WHEN** die Web-Remote-Sitzung nach einem Abbruch wieder authentifiziert ist
- **THEN** läuft der Abgleich genau einmal

#### Scenario: Kein Abgleich ohne Anlass

- **WHEN** ein Abgleich ohne Fehler beendet ist und weder die Sitzung neu
  aufgebaut, die Konfiguration aktiviert noch der Retrigger ausgelöst wird
- **THEN** greift `ma2pi` nicht erneut auf Telnet zu

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

### Requirement: Telnet-Fehler wiederholen

`ma2pi` MUST den Abgleich mit wachsendem Backoff wiederholen, solange Telnet
fehlschlägt. Fehlen nach dem Schreiben Ziele ohne Verbindungsfehler, MUST
`ma2pi` das melden, aber nicht von sich aus wiederholen.

#### Scenario: Teilweise angenommen

- **WHEN** die MA beim Abgleich nur einen Teil der Einträge annimmt
- **THEN** zeigt der Status die fehlenden Einträge als fehlerhaft und `ma2pi`
  wiederholt den Lauf erst beim nächsten Connect oder per Retrigger

#### Scenario: Telnet noch nicht bereit

- **WHEN** der erste Abgleich nach einem Showwechsel mit Telnet-Fehler endet
- **THEN** versucht `ma2pi` es erneut, ohne dass der Betreiber reconnecten muss

### Requirement: Manueller Retrigger

Die API SHALL `POST /api/midi-remote/sync` anbieten. Der Aufruf MUST denselben
Abgleich anstoßen wie ein automatischer Lauf. Bei deaktivierten MIDI-Remotes
oder `sync = "off"` MUST die API mit 409 antworten und nichts in die MA
schreiben.

#### Scenario: Retrigger bei aktivem Abgleich

- **WHEN** MIDI-Remotes aktiv sind, `sync = "auto"` gilt und
  `POST /api/midi-remote/sync` aufgerufen wird
- **THEN** startet der Abgleich erneut und der Status zeigt ihn als laufend

#### Scenario: Abgleich aus

- **WHEN** `sync = "off"` gilt und `POST /api/midi-remote/sync` aufgerufen wird
- **THEN** antwortet die API mit 409 und schreibt nichts in die MA
