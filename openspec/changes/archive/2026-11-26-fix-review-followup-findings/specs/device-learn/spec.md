# Spec Delta

## ADDED Requirements

### Requirement: Globale Tastenfreigabe beim Tasten-Lernen und Rasten-Entprellung

Startet eine `LearnManager`-Sitzung (auch mit Gerätefilter), MUST der Daemon
gehaltene Tasten und Playback-Buttons **aller** Geräte freigeben, weil während
der Sitzung alle Geräte abgefangen werden. Im `DeviceLearnManager` MUST die
Nachlauf-Entprellung innerhalb des Zeitfensters auch identische Folge-Velocities
von `relative-encoder`-Rasten und Fader-Endanschlägen schlucken und fehlende
Geräteeinträge nach einem Hot-Reload fehlerfrei abfangen.

#### Scenario: Relativer Encoder mit konstanter Velocity beim Bank-Lernen

- **WHEN** beim Anlernen eines `relative-encoder` innerhalb von 350 ms mehrere
  Rasten mit Velocity `127` eintreffen
- **THEN** wird die Note einmalig übernommen, ohne beim Folge-Control einen
  Doppelnoten-Fehler zu melden

#### Scenario: Gehaltene Taste auf Zweitgerät bei gefiltertem Learn-Start

- **WHEN** auf Gerät B eine Taste gehalten wird und für Gerät A der Tasten-Learn
  startet
- **THEN** gibt der Daemon die Taste von Gerät B beim Start sauber frei
