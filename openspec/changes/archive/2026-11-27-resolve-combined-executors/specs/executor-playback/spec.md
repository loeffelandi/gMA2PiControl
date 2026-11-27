# Spec Delta

## MODIFIED Requirements

### Requirement: Playback auf der aktuellen Master-Page

Ein Playback-Ziel mit `page = "current"` SHALL `pageIndex = -1` senden. Damit
adressiert die MA den Executor auf der aktuell aktiven Master-Page, ohne dass
`ma2pi` für die Eingabe die Page kennen muss. Ein Seitenwechsel auf der MA MUST
ohne Konfigurationsänderung wirksam werden. Das optionale Executor-Feedback MUST
Antworten auf `pageIndex = -1` dem Ziel `"current"` zuordnen und dem
Seitenwechsel folgen; die tatsächliche Master-Page muss dafür nicht bekannt
sein, denn die MA liefert sie in der Antwort nicht mit.

#### Scenario: Button auf der aktuellen Page

- **WHEN** ein Button-Ziel `page = "current"` und `executor = 3` hat und
  gedrückt wird
- **THEN** enthält der Frame `pageIndex = -1` und `execIndex = 2`

#### Scenario: Fader auf der aktuellen Page

- **WHEN** ein Fader-Ziel `page = "current"` und `executor = 5` hat und bewegt
  wird
- **THEN** enthält der Frame `pageIndex = -1` und `execIndex = 4`

#### Scenario: Seitenwechsel auf der MA

- **WHEN** die MA zwischen zwei Eingaben auf eine andere Master-Page wechselt
- **THEN** adressiert die nächste Eingabe weiterhin `pageIndex = -1` und wirkt
  auf den Executor der dann aktiven Page

## ADDED Requirements

### Requirement: Button-Ziele auf überdeckten Floating-Slots

Ein Button-Ziel mit Transport `web` auf einem Executor ab 101, der laut
Topologie von einem führenden Executor überdeckt wird, SHALL an den führenden
Executor gesendet werden: `execIndex` ist der führende Executor minus eins, `buttonId` ist 0, weil
die Floating-Kachel nur eine Taste besitzt. Ein Release MUST an dasselbe
aufgelöste Ziel gehen wie der zugehörige Press.

#### Scenario: Knopf auf überdecktem Slot

- **WHEN** Exec 114 auf Page 2 zwei breit ist und ein Button-Ziel mit Transport
  `web` auf Exec 115, `button = 1` gedrückt wird
- **THEN** enthält der Frame `execIndex = 113` und `buttonId = 0`

#### Scenario: Ziel mit Transport midi

- **WHEN** dasselbe Ziel `transport = "midi"` hat
- **THEN** wird es nicht umgeleitet (Requirement „Keine Umleitung breiter
  Executoren bei MIDI“), und die MA behandelt den Slot wie eine Konsolentaste

#### Scenario: Ziel mit höherer Button-Nummer

- **WHEN** ein Button-Ziel auf dem überdeckten Slot `button = 2` angibt
- **THEN** enthält der Frame `buttonId = 0` des führenden Executors

#### Scenario: Release folgt dem Press

- **WHEN** zwischen Press und Release die Topologie wechselt
- **THEN** geht der Release an den Executor, der beim Press gesendet wurde

#### Scenario: Führender Executor selbst

- **WHEN** ein Button-Ziel auf Exec 114 zeigt
- **THEN** enthält der Frame `execIndex = 113`, unverändert

### Requirement: Überdeckte Slots der Fader-Ansicht bleiben adressierbar

Ein Playback-Ziel auf einem Executor bis 100, der von einem führenden Executor
überdeckt wird, MUST unverändert gesendet werden (eigener `execIndex`, eigene
`buttonId`, eigener Fader), weil die MA den überdeckten Slot dort mit eigenen
Buttons und eigenem Fader bereitstellt.

#### Scenario: Button auf überdecktem Fader-Slot

- **WHEN** Exec 3 auf Page 3 zwei breit ist und ein Button-Ziel auf Exec 4,
  `button = 3` gedrückt wird
- **THEN** enthält der Frame `execIndex = 3` und `buttonId = 2`

#### Scenario: Fader auf überdecktem Slot

- **WHEN** ein Fader-Ziel auf den überdeckten Slot Exec 4 zeigt und bewegt wird
- **THEN** enthält der Frame `execIndex = 3` und den Wert des Ziels
