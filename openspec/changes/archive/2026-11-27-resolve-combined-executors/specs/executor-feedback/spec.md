# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
