# Spec Delta

## ADDED Requirements

### Requirement: Absolute MIDI-Werte aus Geräteprofilen

Ein MIDI-Profil SHALL zusätzlich zu Tasten und Encodern absolute Controls über
Note und logischen Namen definieren können. Bei einer konfigurierten
Absolut-Note MUST jede Note-On-Nachricht einen normalisierten Wert zwischen
0.0 (Velocity 0) und 1.0 (Velocity 127) erzeugen; das zugehörige Note-Off MUST
ignoriert werden und darf kein Key-Up auslösen.

#### Scenario: Faderwert empfangen

- **WHEN** eine als absolut konfigurierte Fader-Note mit Velocity `64`
  empfangen wird
- **THEN** liefert `ma2pi` genau ein Wertereignis mit dem normalisierten Wert
  `0.5` für das logische Control

#### Scenario: Absoluter Encoderwert empfangen

- **WHEN** eine als absolut konfigurierte Encoder-Note mit Velocity `127`
  empfangen wird
- **THEN** liefert `ma2pi` ein Wertereignis mit dem Wert `1.0` und kein
  Encoder-Delta

#### Scenario: Note-Off eines absoluten Controls

- **WHEN** auf eine absolute Note ein Note-Off folgt
- **THEN** entsteht kein weiteres Ereignis und kein Key-Up

#### Scenario: Note ist gleichzeitig Taste und Wert

- **WHEN** dieselbe Note im Profil sowohl als Taste oder relativer Encoder als
  auch als absoluter Wert konfiguriert ist
- **THEN** lehnt `ma2pi` die Konfiguration mit einer Meldung ab, die Profil und
  Note nennt

### Requirement: Mehrere MIDI-Geräte parallel

`ma2pi` SHALL jedes konfigurierte MIDI-Gerät über einen eigenen, während der
Laufzeit dauerhaft geöffneten Zugriff lesen. Der Verlust oder das erneute
Öffnen eines Geräts MUST die übrigen MIDI-Geräte unabhängig weiterbetreiben und
darf deren Ereignisse nicht unterbrechen.

#### Scenario: Zweites MIDI-Gerät wird erkannt

- **WHEN** neben dem ASL ein weiteres Gerät mit Backend `midi` konfiguriert und
  angeschlossen ist
- **THEN** öffnet `ma2pi` für beide Geräte je einen eigenen Zugriff und liefert
  die Ereignisse getrennt mit dem jeweiligen Gerätenamen

#### Scenario: Ein Gerät wird im Betrieb getrennt

- **WHEN** das zweite MIDI-Gerät während des Betriebs verschwindet
- **THEN** bleiben die Ereignisse des ersten Geräts erhalten, und `ma2pi`
  protokolliert den Verlust des zweiten Geräts

#### Scenario: Gerät erscheint erneut

- **WHEN** das zweite MIDI-Gerät wieder eingesteckt wird
- **THEN** öffnet `ma2pi` es ohne Neustart erneut und liest es mit demselben
  Profil wie zuvor

### Requirement: Unbekannte absolute Werte

Trifft eine Note ein, die weder als Taste, relativer Encoder noch als absoluter
Wert konfiguriert ist, MUST `ma2pi` sie ignorieren und einmalig pro Gerät und
Note protokollieren. Es dürfen keine Frames an die MA gesendet werden.

#### Scenario: Nicht konfigurierte Note

- **WHEN** das MIDICRAFT ENC eine Note sendet, die im Profil nicht vorkommt
- **THEN** wird kein Ereignis weitergereicht und die Note nur beim ersten
  Auftreten protokolliert
