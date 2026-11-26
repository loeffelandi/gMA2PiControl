# Spec Delta

## ADDED Requirements

### Requirement: Gerätebezogener Replug-Abgleich und Fortschritts-Stauprüfung

`ExecutorFeedback` SHALL geöffnete MIDI-Geräte über eine pro Öffnung steigende
Handle-Generation abgleichen und Zustände nur für das geänderte Gerät
zurücksetzen. Die Stau-Erkennung MUST prüfen, ob ausstehende Bytes über das
Stau-Fenster hinweg **ohne Abnahme** stehen bleiben, damit kontinuierliche
LED-Updates keinen Fehlalarm auslösen.

#### Scenario: Controller wird auf denselben `/dev/snd/midiC*D*`-Pfad neu gesteckt

- **WHEN** ein MIDI-Controller zwischen zwei Zyklen abgezogen und unter demselben
  Pfad neu geöffnet wird
- **THEN** erkennt `ExecutorFeedback` die neue Generation, hebt eine Stau-Pause
  auf und sendet alle LEDs dieses Geräts neu

#### Scenario: Kontinuierliche LED-Updates lösen keinen Fehl-Stau aus

- **WHEN** über mehr als zwei Sekunden fortlaufend Frames gesendet und vom Gerät
  abgenommen werden
- **THEN** bleibt die LED-Ausgabe aktiv

### Requirement: Leere Executor-Seiten und Bank-Auflösung im Feedback

Unbelegte Executoren ohne `isRun` in `playbacks`-Antworten MUST als `off`
gelten, und `"current"`-Blöcke MUST späte Antworten fester Seiten verwerfen.
`build_feedback_targets` SHALL den Bank-Kanal (`0x90 | (channel - 1)`),
Bank-Offsets und `mapping.device_banks`-Overrides berücksichtigen.

#### Scenario: Wechsel auf leere Executor-Page schaltet LEDs aus

- **WHEN** alle abgefragten Executoren einer Seite unbelegt sind
- **THEN** entsteht kein Timeout und die zugehörigen LEDs wechseln auf `off`

#### Scenario: Bank auf Kanal 2 erhält LED-Frames auf Kanal 2

- **WHEN** eine Bank auf MIDI-Kanal 2 gebunden ist
- **THEN** adressiert `ExecutorFeedback` deren LED-Noten auf Kanal 2
