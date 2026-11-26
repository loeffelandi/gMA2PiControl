# Spec Delta

## ADDED Requirements

### Requirement: Beschleunigte Werte auf Executor-Fadern

Der Playback-Router SHALL bei einem Fader-Ziel mit `accelerated = true` den
virtuellen Wert nach der Wert-Beschleunigung senden. Die Beschleunigung MUST
vor der Klemmung und vor dem Vergleich mit dem zuletzt gesendeten Wert
erfolgen. Ein Fader-Ziel ohne `accelerated` MUST den normalisierten Rohwert
unverändert senden. Button-Ziele MUST von der Wert-Beschleunigung unberührt
bleiben. Der Zustand MUST je Control getrennt geführt werden.

#### Scenario: Zwei Encoder mit unterschiedlicher Geschwindigkeit

- **WHEN** zwei beschleunigte Encoder gleichzeitig bewegt werden, einer langsam
  und einer schnell
- **THEN** wird nur der schnell bewegte Encoder verstärkt und beide behalten
  ihren eigenen virtuellen Wert

#### Scenario: Beschleunigter Wert wird geklemmt

- **WHEN** die verstärkte Änderung den Wert 1.0 überschreitet
- **THEN** enthält der gesendete Frame `faderValue = 1.0`

#### Scenario: Kein doppelter Frame

- **WHEN** die Beschleunigung denselben Wert ergibt, der zuletzt für dieses Ziel
  gesendet wurde
- **THEN** sendet `ma2pi` keinen weiteren Frame

#### Scenario: Fader ohne Opt-in

- **WHEN** ein Fader-Ziel kein `accelerated` setzt
- **THEN** entspricht der gesendete Wert dem normalisierten Rohwert

#### Scenario: Button-Ziel

- **WHEN** ein Control ein Button-Ziel hat
- **THEN** wird die Wert-Beschleunigung nicht angewendet und die bestehende
  Press-/Release-Logik bleibt unverändert
