# Spec Delta

## ADDED Requirements

### Requirement: Kein Log-Aufkommen im Normalbetrieb

Die Beschleunigung SHALL Rohwert und virtuellen Wert nur auf Level `DEBUG`
protokollieren. Bei Level `INFO` MUST ein beschleunigter Wert keine
Logzeile erzeugen.

#### Scenario: Beschleunigter Wert bei Level INFO

- **WHEN** ein beschleunigtes Executor-Ziel Werte empfängt und das Log-Level
  `INFO` ist
- **THEN** entsteht keine Zeile mit Roh- oder virtuellem Wert

#### Scenario: Beschleunigter Wert bei Level DEBUG

- **WHEN** das Log-Level `DEBUG` ist
- **THEN** protokolliert der Router je Wert Rohwert und virtuellen Wert
