# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
