# Spec Delta

## ADDED Requirements

### Requirement: Aktivitäts-LEDs auf der Geräte-Seite

Die Geräte-Seite SHALL je angezeigtem Gerät zwei Aktivitäts-LEDs anzeigen: RX
für empfangene Eingaben und TX für gesendete Ausgaben. Die LEDs MUST aus dem
bestehenden Status-/Aktivitäts-Stream gespeist werden und ohne manuelles
Neuladen pulsieren, sobald der jeweilige Zähler steigt. Die Geräte-Seite MUST
dafür weder zusätzliche Endpunkte noch periodisches Polling einführen.
Zählertexte MUST NOT auf der Geräte-Seite erscheinen.

#### Scenario: Eingabe am Gerät lässt die RX-LED pulsieren

- **WHEN** ein Gerät ein Eingabeereignis liefert, während die Geräte-Seite geöffnet ist
- **THEN** pulsiert die RX-LED dieses Geräts kurz, ohne Seitenwechsel oder Neuladen

#### Scenario: Ausgabe an das Gerät lässt die TX-LED pulsieren

- **WHEN** der Daemon erfolgreich eine Ausgabe an ein Gerät schreibt
- **THEN** pulsiert die TX-LED dieses Geräts kurz

#### Scenario: Gerät ohne Aktivität

- **WHEN** ein Gerät weder sendet noch empfängt
- **THEN** bleiben seine LEDs dunkel

#### Scenario: Status-Verbindung unterbrochen

- **WHEN** die WebSocket-Verbindung des Browsers zum Daemon unterbrochen ist
- **THEN** bleiben die LEDs dunkel und die Seite bleibt bedienbar; nach dem automatischen Reconnect aktualisieren sich die LEDs wieder
