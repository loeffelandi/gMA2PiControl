# Spec Delta

## ADDED Requirements

### Requirement: Playback-Ziele im Mapping-Editor

Der Mapping-Editor SHALL logische Controls, die als absoluter Wert konfiguriert
sind, gemeinsam mit Tasten und Encodern anzeigen und je Control ein
Playback-Ziel mit Page, Executor, Art (`button` oder `fader`) und optionaler
Button-Nummer (`1..3`) bearbeiten lassen. Als Page MUST eine Zahl ab 1 oder
`current` akzeptiert werden. Vor dem Speichern MUST die Oberfläche die
Wertebereichsprüfung durchführen und Fehler am betroffenen Feld anzeigen.

#### Scenario: Control einem Executor zuweisen

- **WHEN** der Benutzer für einen Fader das Ziel `page = 1`, `executor = 5`,
  `kind = "fader"` einträgt und speichert
- **THEN** wird die Konfiguration über den bestehenden Schreibendpunkt
  übernommen und das Ziel erscheint anschließend in der Mapping-Ansicht

#### Scenario: Aktuelle Master-Page wählen

- **WHEN** der Benutzer als Page `current` einträgt
- **THEN** speichert die Oberfläche `page = "current"` und das Ziel folgt der
  aktiven Master-Page

#### Scenario: Ungültiger Executor

- **WHEN** der Benutzer `executor = 0` oder eine Page eingibt, die weder eine
  Zahl ab 1 noch `current` ist
- **THEN** zeigt die Oberfläche den Fehler am Feld an und sendet keine
  Konfigurationsänderung

#### Scenario: Button-Nummer bei Fader-Ziel

- **WHEN** der Benutzer für `kind = "fader"` eine Button-Nummer einträgt
- **THEN** weist die Oberfläche auf den ungültigen Wert hin und verhindert das
  Speichern

### Requirement: Absolute Controls in der Geräteübersicht

Die Geräteübersicht SHALL je konfiguriertem MIDI-Gerät die absoluten Controls
mit Note und Art (`fader` oder `encoder`) anzeigen. Die Anzeige MUST aus der
Konfiguration stammen und darf nicht davon abhängen, ob das Gerät gerade
angeschlossen ist.

#### Scenario: MIDICRAFT ENC wird angezeigt

- **WHEN** das Gerät `midicraft` mit seinem Profil konfiguriert und
  angeschlossen ist
- **THEN** listet die Geräteübersicht fünf Fader und fünf absolute Encoder mit
  ihren Notes und logischen Namen

#### Scenario: Gerät ist nicht angeschlossen

- **WHEN** das konfigurierte MIDICRAFT ENC nicht erkannt wird
- **THEN** bleiben seine Controls in der Übersicht sichtbar und sind als nicht
  erkannt markiert
