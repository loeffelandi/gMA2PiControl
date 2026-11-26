# Spec Delta

## ADDED Requirements

### Requirement: Kein Log-Aufkommen im Normalbetrieb

Die Beschleunigung SHALL Rohwert und virtuellen Wert nur auf Level `DEBUG`
protokollieren. Bei Level `INFO` MUST ein beschleunigter Wert keine Logzeile
erzeugen.

#### Scenario: Beschleunigter Wert bei Level INFO

- **WHEN** ein beschleunigtes Executor-Ziel Werte empfängt und das Log-Level
  `INFO` ist
- **THEN** entsteht keine Zeile mit Roh- oder virtuellem Wert

#### Scenario: Beschleunigter Wert bei Level DEBUG

- **WHEN** das Log-Level `DEBUG` ist
- **THEN** protokolliert der Router je Wert Rohwert und virtuellen Wert

## MODIFIED Requirements

### Requirement: Virtueller Wert aus Rohwertänderungen

Der Playback-Router SHALL je Gerät, Bank und beschleunigtem Control einen
virtuellen Wert führen. Das erste Wertereignis für dieses Tripel nach Start oder
Konfigurationswechsel MUST ihn auf den Rohwert setzen; jedes weitere Ereignis
desselben Tripels MUST die Differenz zum letzten Rohwert mit dem Multiplikator
verstärken und addieren.

#### Scenario: Langsame Drehung bleibt 1:1

- **WHEN** aufeinanderfolgende Werte 0.0, 1/127 und 2/127 mit mehr als
  `window` Abstand eintreffen
- **THEN** sendet `ma2pi` 0.0, 1/127 und 2/127 ohne Verstärkung

#### Scenario: Schnelle Drehung wird verstärkt

- **WHEN** mehrere Wertänderungen innerhalb von `window` eintreffen
- **THEN** ist die Änderung des gesendeten Werts größer als die Rohwertänderung

#### Scenario: Erster Wert nach dem Start

- **WHEN** das erste Wertereignis den Rohwert 0.4 liefert
- **THEN** sendet `ma2pi` 0.4 und verwendet ihn als Ausgangspunkt

#### Scenario: Kurze schnelle Bewegung

- **WHEN** der Rohwert nur um wenige Schritte steigt und die Drehung dann stoppt
- **THEN** bleibt der virtuelle Wert auf dem verstärkten Zwischenwert stehen und
  wird nicht zurückgesetzt

#### Scenario: Getrennter Zustand je Gerät und Bank

- **WHEN** dasselbe logische Control auf einer anderen Bank oder einem zweiten
  Gerät bewegt wird
- **THEN** beeinflusst der letzte Rohwert der ersten Bank den neuen Wert nicht

### Requirement: Vollständiger Weg bei kräftiger Drehung

Der Multiplikator MUST mindestens 1.0 betragen, sodass eine Drehung über den
vollen Rohbereich `0..127` den vollen virtuellen Bereich `0.0..1.0` abdeckt. Bei
langsamer Rückdrehung auf den Anschlag `0` oder `127` aus einem inneren
virtuellen Wert MUST der Wert stetig mit der Differenz weiterlaufen statt
sprunghaft auf `0.0` oder `1.0` einzurasten.

#### Scenario: Kräftige Drehung nach oben

- **WHEN** der Rohwert in kleinen Schritten schnell von 0 bis 127 steigt
- **THEN** erreicht der gesendete Wert spätestens beim Rohwert 127 den Wert 1.0

#### Scenario: Kräftige Drehung nach unten

- **WHEN** der Rohwert in kleinen Schritten schnell von 127 bis 0 fällt
- **THEN** erreicht der gesendete Wert spätestens beim Rohwert 0 den Wert 0.0

#### Scenario: Kein Sprung bei langsamer Rückdrehung auf Rohwert 0

- **WHEN** der virtuelle Wert durch schnelles Hochdrehen früh `1.0` erreicht hat
  und anschließend langsam bis Rohwert `0` zurückgedreht wird
- **THEN** nähert sich der virtuelle Wert dem Anschlag `0.0` gleichmäßig ohne
  großen Endsprung im letzten Schritt
