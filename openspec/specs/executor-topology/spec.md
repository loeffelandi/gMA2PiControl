# executor-topology Specification

## Purpose
Liest die tatsächliche Executor-Topologie der grandMA2 (breite Executoren,
überdeckte Slots, nicht vorhandene Executoren) aus den `playbacks`-Antworten und
stellt sie Eingabe und LED-Feedback zur Verfügung, damit Mapping-Ziele nicht
stillschweigend ins Leere zeigen.

## Requirements

### Requirement: Kombinierte Executoren erkennen

`ma2pi` SHALL aus einer beantworteten `playbacks`-Anfrage ableiten, welche
Executoren kombiniert sind. Meldet ein Executor `combinedItems = n` mit `n > 1`,
MUST er als führender Executor gelten und die folgenden `n - 1` Slots MUST als
von ihm überdeckt gelten. Ein überdeckter Slot MUST nicht als fehlend gelten,
auch wenn die Antwort kein Item für ihn enthält.

#### Scenario: Zwei breiter Executor

- **WHEN** die Antwort für Page 2 bei Exec 114 `combinedItems = 2` meldet und
  kein Item für Exec 115 enthält
- **THEN** gilt Exec 114 als führend und Exec 115 als von Exec 114 überdeckt

#### Scenario: Normaler Executor

- **WHEN** ein Executor `combinedItems = 1` meldet
- **THEN** überdeckt er keinen weiteren Slot

#### Scenario: Drei breiter Executor

- **WHEN** ein Executor `combinedItems = 3` meldet
- **THEN** gelten die beiden nächsten Slots als überdeckt

### Requirement: Topologie je Page und Bereich

Die Topologie MUST je Page und je Bereich (Executoren bis 100, Floating-
Executoren ab 101) getrennt geführt werden. Ein Ziel mit `page = "current"` MUST
gegen die zuletzt für `"current"` beantwortete Topologie aufgelöst werden; jede
neue Antwort ersetzt sie. Bei Konfigurationstausch oder Verbindungsverlust MUST
die betroffene Topologie verworfen werden.

#### Scenario: Seitenwechsel wird mit der nächsten Antwort übernommen

- **WHEN** die MA von Page 2 auf Page 3 wechselt und Page 3 keine breiten
  Executoren hat
- **THEN** gelten die überdeckten Slots von Page 2 nach der nächsten Antwort für
  `"current"` nicht mehr; bis dahin kann die alte Topologie noch gelten

#### Scenario: Verbindungsverlust

- **WHEN** die Web-Remote-Verbindung abbricht
- **THEN** ist die Topologie danach unbekannt, bis eine neue Antwort vorliegt

### Requirement: Abfrage unabhängig vom LED-Feedback

Bei `combined_executors = "auto"` SHALL `ma2pi` die Executoren aller
Floating-Button-Ziele (Executor ab 101) abfragen, auch wenn das LED-Feedback
ausgeschaltet ist. Fader-Ziele und Ziele unter 101 MUST NOT für die Topologie
abgefragt werden, weil sie nie umgeleitet werden. Topologie-Abfragen MUST im
Intervall `topology_interval_ms` laufen (500–10000, Default 2000), unabhängig
vom Takt des LED-Feedbacks; es MUST nie mehr als eine Anfrage je Zweck, Page und
Bereich offen sein.

#### Scenario: Feedback aus, Topologie an

- **WHEN** `[feedback] enabled = false` und `combined_executors = "auto"` gilt
  und ein Floating-Button-Ziel existiert
- **THEN** fragt `ma2pi` die Executoren des Ziels im Intervall
  `topology_interval_ms` ab und sendet keine LED-Frames

#### Scenario: Feedback und Topologie gleichzeitig

- **WHEN** das LED-Feedback mit `interval_ms = 250` aktiv ist und
  `topology_interval_ms = 2000` gilt
- **THEN** laufen die LED-Blöcke alle 250 ms und der Topologie-Block nur alle
  2 s; die Topologie-Abfrage vergrößert die LED-Anfragen nicht

#### Scenario: Fader werden nicht abgefragt

- **WHEN** nur Fader-Ziele und Button-Ziele unter Executor 101 existieren
- **THEN** sendet `ma2pi` keine Topologie-Anfrage

#### Scenario: Ungültiges Intervall

- **WHEN** `topology_interval_ms = 100` konfiguriert ist
- **THEN** lehnt die Konfigurationsprüfung die Konfiguration ab und nennt
  `mapping.topology_interval_ms`

### Requirement: Abschaltbare Auflösung

`[mapping] combined_executors` MUST die Werte `"auto"` und `"off"` annehmen
(Default `"auto"`). Bei `"off"` MUST `ma2pi` keine Topologie abfragen und Ziele
unverändert senden, wie vor dieser Funktion. Andere Werte MUST die
Konfigurationsprüfung mit Nennung des Feldes ablehnen.

#### Scenario: Auflösung aus

- **WHEN** `combined_executors = "off"` gilt und ein Button-Ziel auf Exec 115
  zeigt
- **THEN** enthält der Frame `execIndex = 114`, und es erfolgt keine
  Topologie-Abfrage

#### Scenario: Unbekannter Wert

- **WHEN** `combined_executors = "maybe"` konfiguriert ist
- **THEN** lehnt `--check-config` die Konfiguration ab und nennt
  `mapping.combined_executors`

### Requirement: Eingabe blockiert nie auf die Topologie

Ist die Topologie für ein Ziel noch unbekannt oder veraltet, MUST `ma2pi` das
Ziel unverändert senden und darf die Eingabe weder verzögern noch verwerfen.
Der Fall MUST auf Debug-Ebene protokolliert werden.

#### Scenario: Erster Tastendruck vor der ersten Antwort

- **WHEN** ein Button-Ziel gedrückt wird, bevor eine Antwort für dessen Bereich
  eingetroffen ist
- **THEN** wird der Frame sofort mit dem konfigurierten Executor gesendet

### Requirement: Diagnose nicht vorhandener Ziele

Ein Playback-Ziel, dessen Executor in einer beantworteten Anfrage für seinen
Bereich weder als Executor noch als überdeckter Slot vorkommt, MUST einmalig pro
Ziel und Konfigurationsstand als Warnung protokolliert werden. Die Meldung MUST
Control, Page und Executor nennen. Ein leerer, aber vorhandener Executor MUST
keine Warnung auslösen.

#### Scenario: Ziel zeigt ins Leere

- **WHEN** ein Button-Ziel auf Exec 400 der Page 2 zeigt und die Antwort für den
  Bereich Exec 400 nicht enthält
- **THEN** protokolliert `ma2pi` einmalig eine Warnung mit Control, Page 2 und
  Executor 400

#### Scenario: Leerer Executor

- **WHEN** ein Ziel auf einen Executor ohne Zuweisung zeigt, den die Antwort
  als leer meldet
- **THEN** erscheint keine Warnung

#### Scenario: Keine Wiederholung

- **WHEN** weitere Antworten dasselbe Ziel erneut als fehlend zeigen
- **THEN** wird die Warnung nicht wiederholt, bis die Konfiguration getauscht wird
