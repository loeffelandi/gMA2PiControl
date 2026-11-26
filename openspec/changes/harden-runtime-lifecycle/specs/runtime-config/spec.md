# Spec Delta

## ADDED Requirements

### Requirement: Hilfsdienste folgen der aktiven Konfiguration

Nach einem erfolgreichen Apply SHALL jeder Hilfsdienst, der Konfiguration liest,
mit der neuen Konfiguration arbeiten, ohne dass der Daemon neu gestartet wird.
Das gilt mindestens für Eingabegeräte, Executor-Feedback, die beiden
Learn-Modi und die ASL-LED-Ausgabe. Wird `led.enabled` umgeschaltet, MUST die
LED-Ausgabe zur Laufzeit geöffnet beziehungsweise geschlossen werden; ändern
sich andere `[led]`-Einstellungen, MUST die Ausgabe mit den neuen Werten neu
geöffnet werden.

#### Scenario: Learn-Sitzung nach Apply

- **WHEN** eine Konfiguration angewendet wird und danach eine Learn-Sitzung
  eine Eingabe auflöst
- **THEN** verwendet die Auflösung die neue Konfiguration

#### Scenario: LED zur Laufzeit aktiviert

- **WHEN** der Daemon mit `led.enabled = false` gestartet wurde und ein Apply
  `led.enabled = true` setzt und das Gerät vorhanden ist
- **THEN** öffnet die LED-Ausgabe innerhalb eines Prüfintervalls, ohne
  Neustart

#### Scenario: LED zur Laufzeit deaktiviert

- **WHEN** die LED-Ausgabe offen ist und ein Apply `led.enabled = false` setzt
- **THEN** sendet sie die Abschaltsequenz, schließt den Handle und der Client
  nutzt keine LED mehr

#### Scenario: Geänderte LED-Einstellungen

- **WHEN** ein Apply die Note oder die Farben des `[led]`-Abschnitts ändert
- **THEN** wird die Ausgabe mit den neuen Werten neu geöffnet und der aktuelle
  Modus erneut angezeigt

### Requirement: Vollständiger Shutdown

Beim Beenden des Daemons SHALL jeder von ihm gestartete Hintergrund-Task
abgebrochen und erwartet werden, einschließlich des Geräte-Learn-Tasks. Ein
Task MUST NOT nach der Rückkehr von `run_daemon()` weiterlaufen.

#### Scenario: Stop-Signal

- **WHEN** der Daemon `SIGTERM` erhält
- **THEN** sind alle `ma2pi-*`-Tasks beendet, bevor die Event-Schleife schließt,
  und der Exit-Code ist `0`
