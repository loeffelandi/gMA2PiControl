# executor-playback Specification

## Purpose

Bildet Tasten- und Wertereignisse aus `ma2pi` auf Executor-Buttons und -Fader
der grandMA2 ab und sendet dafür `playbacks_userInput`-Frames über den Web
Remote.

## Requirements

### Requirement: Playback-Ziele in der Konfiguration

Die Konfiguration SHALL je logischem Control ein optionales Playback-Ziel mit
`page`, `executor`, `kind = "button"|"fader"` und bei Buttons `button = 1..3`
erlauben. `page` MUST eine Ganzzahl ab 1 oder der Wert `"current"` sein;
`executor` MUST ganzzahlig und mindestens 1 sein; `button` MUST nur bei
`kind = "button"` angegeben werden.

#### Scenario: Gültiges Button-Ziel

- **WHEN** ein Control auf `page = 2`, `executor = 7`, `kind = "button"` und
  `button = 1` abgebildet ist
- **THEN** wird die Konfiguration akzeptiert und das Ziel bleibt bis zum
  nächsten Konfigurationstausch aktiv

#### Scenario: Gültiges Fader-Ziel

- **WHEN** ein Control auf `page = 1`, `executor = 3` und `kind = "fader"`
  abgebildet ist
- **THEN** wird die Konfiguration akzeptiert, ohne dass ein Button angegeben
  werden muss

#### Scenario: Aktuelle Master-Page als Ziel

- **WHEN** ein Control auf `page = "current"`, `executor = 3` und
  `kind = "fader"` abgebildet ist
- **THEN** wird die Konfiguration akzeptiert und das Ziel folgt der jeweils
  aktiven Master-Page

#### Scenario: Ungültiges Playback-Ziel

- **WHEN** `page` weder `"current"` noch eine Ganzzahl ab 1 ist, `executor`
  kleiner als 1 ist, `kind` unbekannt ist oder ein Fader-Ziel einen `button`
  angibt
- **THEN** lehnt `ma2pi` die Konfiguration mit einer Meldung ab, die Control
  und fehlerhaftes Feld nennt, und behält die aktive Konfiguration bei

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

### Requirement: Tastenereignisse auf Executor-Buttons

Ein Tastenereignis SHALL bei gedrückter Taste einen `playbacks_userInput`-Frame
mit `pressed = true` und `released = false` senden und beim Loslassen einen
Frame mit `pressed = false` und `released = true`. Page, Executor und Button
MUST von 1-basiert auf 0-basiert umgerechnet werden; die Reihenfolge von Press
und Release MUST erhalten bleiben.

#### Scenario: Executor-Button drücken

- **WHEN** ein Control mit Button-Ziel den Wert 1 liefert
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

### Requirement: Wertereignisse auf Executor-Fader

Ein Wertereignis SHALL als `playbacks_userInput`-Frame mit `faderValue`
zwischen 0.0 und 1.0 und `type = 1` gesendet werden. Mehrere Werte für dasselbe
Ziel MUST zu einem einzigen, noch nicht gesendeten Frame zusammengefasst
werden, bei dem der zuletzt empfangene Wert gewinnt.

#### Scenario: Fader bewegen

- **WHEN** ein Control mit Fader-Ziel den normalisierten Wert 0.5 liefert
- **THEN** sendet `ma2pi` einen Frame mit `faderValue = 0.5`, `type = 1`,
  `execIndex = executor - 1` und `pageIndex = page - 1`

#### Scenario: Schnelle Faderbewegung

- **WHEN** dasselbe Fader-Ziel innerhalb eines Sendezyklus mehrere Werte
  empfängt
- **THEN** wird höchstens ein Frame mit dem zuletzt empfangenen Wert gesendet
  und kein Zwischenwert nachgereicht

#### Scenario: Unveränderter Wert

- **WHEN** ein Fader-Ziel denselben Wert erneut empfängt, der zuletzt gesendet
  wurde
- **THEN** sendet `ma2pi` keinen weiteren Frame

### Requirement: Vorrang der Playback-Ziele

Ein Control mit Playback-Ziel SHALL dieses Ziel adressieren und nicht zusätzlich
über die bestehende Tasten- oder Encoder-Zuordnung verarbeitet werden. Controls
ohne Playback-Ziel MUST unverändert an die bestehende Zuordnung gehen.

#### Scenario: Control mit Playback-Ziel

- **WHEN** ein Control sowohl ein Playback-Ziel als auch eine Tasten-Zuordnung
  besitzt
- **THEN** sendet `ma2pi` ausschließlich Executor-Frames und keine Hardkey-
  oder Command-Frames

#### Scenario: Control ohne Playback-Ziel

- **WHEN** ein Control keine Playback-Zuordnung besitzt
- **THEN** verhält es sich wie bisher und wird über Hardkey, Command oder
  Encoder verarbeitet

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

### Requirement: Ungepaartes Loslassen erzeugt keinen Executor-Frame

Trifft für ein Playback-Button-Control ein Loslassen (`value < 0.5`) ein, ohne
dass dafür im `PlaybackRouter` ein aktiver Tastendruck vermerkt ist (etwa nach
Verbindungsverlust, Konfigurations-Cleanup oder Ende eines Lernmodus), MUST der
Router das Ereignis verwerfen, ohne einen `playbackButton`-Release-Frame oder
einen `Page`-Befehl zu senden.

#### Scenario: Physisches Loslassen nach Session-Reset

- **WHEN** eine gehaltene Playback-Taste durch Verbindungsverlust zurückgesetzt
  wurde und der Bediener sie nach dem Reconnect loslässt
- **THEN** sendet `ma2pi` keinen verwaisten Release-Frame an die neue Session
