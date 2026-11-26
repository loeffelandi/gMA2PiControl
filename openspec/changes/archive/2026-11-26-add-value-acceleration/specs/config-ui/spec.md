# Spec Delta

## ADDED Requirements

### Requirement: Checkbox je absolutem Encoder

Der Mapping-Editor SHALL für jedes Playback-Ziel mit `kind = "fader"`, dessen
Control im Profil als absoluter Encoder geführt wird, eine Checkbox
„Beschleunigt“ anzeigen. Die Checkbox MUST den gespeicherten Wert
`accelerated` widerspiegeln; ohne gespeicherten Wert MUST sie ausgeschaltet
sein. Für Button-Ziele und für Controls, die im Profil als Fader geführt
werden, MUST keine Checkbox erscheinen.

#### Scenario: Encoder mit Fader-Ziel

- **WHEN** ein absoluter Encoder ein Fader-Ziel auf Executor 3 hat und
  `accelerated = true` gespeichert ist
- **THEN** zeigt die Zeile die Checkbox aktiviert an

#### Scenario: Physischer Fader

- **WHEN** ein Control im Profil als Fader geführt wird
- **THEN** zeigt seine Playback-Zeile keine Beschleunigungs-Checkbox

#### Scenario: Button-Ziel

- **WHEN** ein Playback-Ziel `kind = "button"` hat
- **THEN** zeigt die Zeile keine Beschleunigungs-Checkbox

### Requirement: Speichern der Checkbox

Beim Speichern MUST ein eingeschalteter Wert als `accelerated = true` und ein
ausgeschalteter Wert als `accelerated = false` oder ohne Feld geschrieben
werden. Lehnt das Backend die Kombination ab, MUST der Editor die Fehlermeldung
an der betroffenen Zeile anzeigen und die bisherige Konfiguration behalten.

#### Scenario: Beschleunigung einschalten

- **WHEN** der Benutzer die Checkbox für einen Encoder aktiviert und speichert
- **THEN** enthält das gespeicherte Playback-Ziel `accelerated = true`

#### Scenario: Beschleunigung ausschalten

- **WHEN** der Benutzer die Checkbox für einen Encoder deaktiviert und speichert
- **THEN** enthält das gespeicherte Playback-Ziel kein aktives `accelerated`
  mehr und das Control wird wieder 1:1 übertragen

#### Scenario: Ungültige Kombination

- **WHEN** die Konfiguration die Checkbox für ein Control speichert, das nicht
  als absoluter Encoder geführt wird
- **THEN** zeigt der Editor die Fehlermeldung des Backends an der Zeile an und
  behält die bisherige Konfiguration bei
