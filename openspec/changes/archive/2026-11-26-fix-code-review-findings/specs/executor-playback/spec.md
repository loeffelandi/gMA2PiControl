# Spec Delta

## ADDED Requirements

### Requirement: Zielbindung gehaltener Playback-Buttons

Der Playback-Router SHALL je gedrücktem Button das Ziel `(page, executor, button)`
unter `(device, control)` speichern und beim Loslassen, `DeviceLost` oder
Cleanup genau dieses Ziel freigeben — auch nach einem Bankwechsel. Gehört das
gehaltene Control stattdessen der `MappingEngine`, MUST das Release an diese
weitergereicht werden.

#### Scenario: Release nach Bankwechsel trifft den ursprünglichen Executor

- **WHEN** ein Button auf Bank 1 (`Executor 1`) gedrückt und erst auf Bank 2
  losgelassen wird
- **THEN** sendet `ma2pi` das Release an `Executor 1`

#### Scenario: Bank-Hardkey-Release wird nicht geschluckt

- **WHEN** ein Control auf Bank 2 als Hardkey gedrückt und nach Wechsel auf
  Bank 1 losgelassen wird
- **THEN** erreicht das Release die `MappingEngine` und gibt den Hardkey frei

#### Scenario: Geräteverlust bei gehaltenem Playback-Button

- **WHEN** ein Controller abgezogen wird, während ein Playback-Button gehalten ist
- **THEN** sendet der Daemon das Release für diesen Executor-Button

### Requirement: Re-Synchronisation von Page und Fadern nach Verbindungsverlust

Bricht die MA2-Session ab, SHALL der Playback-Router gemerkte Bank-Seiten und
Fader-Werte verwerfen, damit nach dem Reconnect `Page <ma_page>` und unveränderte
Fader-Endwerte erneut gesendet werden.

#### Scenario: Erneutes Senden nach Reconnect

- **WHEN** während getrennter Verbindung die Bank gewechselt wurde und die
  Session danach wieder steht
- **THEN** wird bei der nächsten Eingabe die MA-Page erneut gesendet

## MODIFIED Requirements

### Requirement: Beschleunigte Werte auf Executor-Fadern

Der Playback-Router SHALL bei einem Fader-Ziel mit `accelerated = true` den
virtuellen Wert nach der Wert-Beschleunigung vor Klemmung und Deduplizierung
senden; ohne `accelerated` MUST der Rohwert unverändert gehen, und Button-Ziele
MUST unberührt bleiben. Der Zustand MUST je Gerät, Bank und Control getrennt
geführt werden.

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

#### Scenario: Bankwechsel verursacht keinen Fader-Sprung

- **WHEN** `mc_encoder_1` auf Bank 1 bei Rohwert `1.0` steht und danach auf
  Bank 2 mit Rohwert `0.2` bewegt wird
- **THEN** startet Bank 2 ohne Differenzsprung aus Bank 1
