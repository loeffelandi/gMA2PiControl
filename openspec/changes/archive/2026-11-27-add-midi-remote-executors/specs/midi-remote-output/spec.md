## Purpose

Sendet Executor-Eingaben von `ma2pi` als MIDI-Nachrichten per RTP-MIDI an den
onPC-Rechner, damit die MA sie über MIDI-Remotes wie Konsolentasten auf der
Haupt-Kommandozeile ausführt.

## ADDED Requirements

### Requirement: Konfiguration des MIDI-Remote-Ausgangs

Die Konfiguration SHALL einen Abschnitt `[midi_remote]` mit `enabled`
(Default `false`), `host` (Default: Host der MA-Verbindung), `port` (Default
5004) und `channels` (Liste reservierter MIDI-Kanäle 1–16, Default `[16]`)
erlauben. Ungültige Werte MUST die Konfigurationsprüfung mit Nennung des Feldes
ablehnen.

#### Scenario: Minimale Konfiguration

- **WHEN** `[midi_remote] enabled = true` ohne weitere Felder konfiguriert ist
- **THEN** verwendet `ma2pi` den Host der MA-Verbindung, Port 5004 und Kanal 16

#### Scenario: Ungültiger Kanal

- **WHEN** `channels = [0]` oder `channels = [17]` konfiguriert ist
- **THEN** lehnt die Konfigurationsprüfung die Konfiguration ab und nennt
  `midi_remote.channels`

#### Scenario: Ausgang aus

- **WHEN** `enabled = false` gilt
- **THEN** baut `ma2pi` keine RTP-MIDI-Sitzung auf und sendet keine
  MIDI-Nachrichten an die MA

### Requirement: RTP-MIDI-Sitzung zum onPC-Rechner

Bei `enabled = true` SHALL `ma2pi` eine RTP-MIDI-Sitzung zu `host:port` aufbauen
und halten. Bricht die Sitzung ab oder lehnt die Gegenstelle ab, MUST `ma2pi`
mit wachsender Pause (höchstens 10 s) neu verbinden. Der Zustand der Sitzung
MUST im Status der Web-UI und im Log sichtbar sein.

#### Scenario: Sitzung steht

- **WHEN** der RTP-MIDI-Treiber auf dem onPC-Rechner die Einladung annimmt
- **THEN** zeigt der Status die MIDI-Sitzung als verbunden

#### Scenario: Gegenstelle nicht erreichbar

- **WHEN** auf `host:port` kein RTP-MIDI-Teilnehmer antwortet
- **THEN** zeigt der Status die MIDI-Sitzung als getrennt, `ma2pi` versucht es
  höchstens alle 10 s erneut und die übrigen Funktionen laufen weiter

### Requirement: Feste MIDI-Adresse je Playback-Ziel

`ma2pi` SHALL jedem Playback-Ziel mit Transport `midi` eine MIDI-Adresse
(Kanal, Note) aus den reservierten Kanälen zuweisen. Gleiche Ziele MUST dieselbe
Adresse erhalten; verschiedene Ziele MUST verschiedene Adressen erhalten. Reicht
der Bereich nicht, MUST die Konfigurationsprüfung ablehnen und die Anzahl der
Ziele und freien Adressen nennen.

#### Scenario: Zwei Controls auf dasselbe Ziel

- **WHEN** zwei Controls in verschiedenen Bänken auf `page = 1`,
  `executor = 101`, `button = 1` zeigen
- **THEN** senden beide dieselbe Note auf demselben Kanal

#### Scenario: Bereich erschöpft

- **WHEN** mit `channels = [16]` mehr als 128 verschiedene Ziele Transport
  `midi` haben
- **THEN** lehnt die Konfigurationsprüfung ab und nennt `midi_remote.channels`

### Requirement: Press und Release als Note-On und Note-Off

Ein Tastenereignis auf ein Ziel mit Transport `midi` SHALL beim Drücken ein
Note-On mit Velocity 127 und beim Loslassen ein Note-Off auf der Adresse des
Ziels senden. Die Reihenfolge MUST erhalten bleiben; Release MUST nicht
verworfen werden.

#### Scenario: Taste drücken und loslassen

- **WHEN** ein Control mit Button-Ziel auf Adresse Kanal 16, Note 5 den Wert 1
  und danach 0 liefert
- **THEN** sendet `ma2pi` `9F 05 7F` und danach `8F 05 00`

#### Scenario: Store von der Cherry

- **WHEN** auf der Cherry Store (LUA-Hardkey) und danach eine ENC-Taste mit
  Ziel `page = 1`, `executor = 101`, Transport `midi` gedrückt wird
- **THEN** speichert die MA auf Executor 1.101, statt ihn auszulösen

### Requirement: Kein stilles Ausweichen

Ist die MIDI-Sitzung getrennt oder die Remote-Tabelle für ein Ziel nicht
abgeglichen, SHALL `ma2pi` Eingaben auf dieses Ziel nicht über den Web Remote
senden. Es MUST je Ziel höchstens einmal pro Ausfall eine Warnung loggen und den
Grund im Status zeigen.

#### Scenario: Sitzung getrennt

- **WHEN** die MIDI-Sitzung getrennt ist und eine ENC-Taste mit Transport
  `midi` gedrückt wird
- **THEN** sendet `ma2pi` weder MIDI noch `playbacks_userInput` für diese Taste
  und loggt eine Warnung mit dem Ziel
