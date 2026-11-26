# Spec Delta

## MODIFIED Requirements

### Requirement: Playback auf der aktuellen Master-Page

Ein Playback-Ziel mit `page = "current"` SHALL `pageIndex = -1` senden. Damit
adressiert die MA den Executor auf der aktuell aktiven Master-Page, ohne dass
`ma2pi` für die Eingabe die Page kennen muss. Ein Seitenwechsel auf der MA MUST
ohne Konfigurationsänderung wirksam werden. Das optionale Executor-Feedback MUST
die tatsächliche Page aus der Playbacks-Antwort übernehmen und dem Seitenwechsel
folgen.

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

## REMOVED Requirements

### Requirement: Kein Executor-Feedback in diesem Change

**Reason**: Executor-Feedback wird mit der Capability `executor-feedback`
eingeführt; die ursprüngliche Ausklammerung gilt nicht mehr.

**Migration**: Keine. Das Feedback ist standardmäßig über `[feedback].enabled`
abgeschaltet; bestehende Konfigurationen verhalten sich unverändert.
