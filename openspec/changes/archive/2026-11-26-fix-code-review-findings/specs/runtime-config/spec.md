# Spec Delta

## ADDED Requirements

### Requirement: Hilfsdienste folgen der aktiven Konfiguration

Nach einem erfolgreichen Apply SHALL jeder Hilfsdienst ohne Neustart mit der
neuen Konfiguration arbeiten: Eingabegeräte, Executor-Feedback, beide
Learn-Modi, `[led]`, `logging.level` und `keepalive_interval`. Wird `led.enabled`
umgeschaltet oder ändern sich `[led]`-Werte, MUST die ASL-LED-Ausgabe zur
Laufzeit aktiviert, deaktiviert (`DISABLE` senden) oder aktualisiert werden.

#### Scenario: Learn-Sitzung nach Apply

- **WHEN** eine Konfiguration angewendet wird und danach eine Learn-Sitzung
  eine Eingabe auflöst
- **THEN** verwendet die Auflösung die neue Konfiguration

#### Scenario: LED zur Laufzeit aktiviert

- **WHEN** der Daemon mit `led.enabled = false` gestartet wurde und ein Apply
  `led.enabled = true` setzt und das Gerät vorhanden ist
- **THEN** aktiviert die LED-Ausgabe den Modus innerhalb eines Prüfintervalls
  ohne Neustart

#### Scenario: LED zur Laufzeit deaktiviert

- **WHEN** die LED-Ausgabe aktiv ist und ein Apply `led.enabled = false` setzt
- **THEN** sendet sie die Abschaltsequenz (`DISABLE`) und der Client nutzt keine
  Modus-LED mehr

#### Scenario: Geänderte LED-, Log- und Keepalive-Einstellungen

- **WHEN** ein Apply Farben/Noten in `[led]`, `logging.level` oder
  `keepalive_interval` ändert
- **THEN** werden LED-Anzeige, Root-Logger und Keepalive-Takt ohne Neustart
  aktualisiert

### Requirement: Vollständiger Shutdown

Beim Beenden des Daemons SHALL jeder gestartete Hintergrund-Task einschließlich
des Geräte-Learn-Tasks (vor `engine.cleanup()`) abgebrochen und erwartet sowie
alle offenen Event-Stream-Verbindungen geschlossen werden. Ein Task MUST NOT
nach der Rückkehr von `run_daemon()` weiterlaufen.

#### Scenario: Stop-Signal beendet alle Tasks

- **WHEN** der Daemon `SIGTERM` erhält
- **THEN** sind alle `ma2pi-*`-Tasks beendet, bevor `run_daemon()` mit `0`
  zurückkehrt

### Requirement: Endliche Zahlenwerte, Bank-Hardkeys und konsistente Dateipfade

Die Validierung SHALL `NaN` und `±Infinity` ablehnen und Bank-Hardkeys im
LUA-Modus gegen `[hardkeys]` prüfen. `ConfigStore` MUST beim Start von
`/etc/ma2pi/config.toml` migrieren, abweichende `--config`-Dateinamen stützen,
Passwortänderungen bei Schreibfehlern zurückrollen und gleichsekündige Backups
chronologisch rotieren.

#### Scenario: `NaN` oder `inf` wird abgelehnt

- **WHEN** eine Konfiguration `nan` oder `inf` enthält
- **THEN** lehnt die Validierung sie unter Nennung des Feldes ab

#### Scenario: Mehrere Backups in derselben Sekunde

- **WHEN** in derselben Sekunde mehrere Änderungen gespeichert werden
- **THEN** behält `rotate_backups` die neuesten Stände und löscht die ältesten

## MODIFIED Requirements

### Requirement: Validierung vor dem Anwenden

Jede Konfigurationsänderung SHALL vor dem Schreiben, vor dem Einfrieren der
Eingaben und vor dem Anwenden validiert und bei geänderten MA2-Zugangsdaten
getestet werden. Während des Verbindungstests MUST die aktive
Eingabeverarbeitung weiterlaufen; bei Fehlern bleibt die laufende Session ohne
Unterbrechung unverändert.

#### Scenario: Ungültige Änderung wird abgelehnt

- **WHEN** eine Änderung mit Wheel 11 oder einer unbekannten Hardkey-Referenz angewendet werden soll
- **THEN** antwortet die API mit einem Validierungsfehler und die bisherige Konfiguration bleibt vollständig aktiv

#### Scenario: Gültige Änderung wird angenommen

- **WHEN** eine schemakonforme Änderung angewendet wird
- **THEN** wird sie validiert, gespeichert und als neue aktive Generation gemeldet

#### Scenario: Fehlgeschlagener Verbindungstest blockiert keine Eingaben

- **WHEN** ein Apply mit unerreichbarem MA2-Host geprüft wird, während Tasten
  oder Encoder bedient werden
- **THEN** laufen die Live-Eingaben auf der bestehenden Session ohne Pause weiter

### Requirement: Freigabe gehaltener Tasten vor dem Tausch

Unmittelbar vor dem Aktivieren einer getesteten Konfiguration SHALL der Daemon
`MappingEngine` und `PlaybackRouter` einfrieren, alle gehaltenen Hardkeys,
Encoder-Klicks und Playback-Buttons umgekehrt freigeben, offene Encoder-Deltas
verwerfen und die Release-Frames unter der bisherigen Konfiguration absenden,
bevor `apply_config` oder `reconnect` läuft.

#### Scenario: Apply bei gehaltener MA-Taste

- **WHEN** MA und Store (oder ein Executor-Button) gehalten werden und eine neue
  Konfiguration aktiviert wird
- **THEN** werden die Release-Frames in umgekehrter Reihenfolge noch vor dem
  Konfigurations- beziehungsweise Session-Wechsel abgesetzt

#### Scenario: Offener Encoder-Delta

- **WHEN** beim Apply noch ein akkumulierter Encoder-Delta aussteht
- **THEN** wird dieser Delta verworfen und nicht mit der neuen Auflösung oder dem neuen Ziel gesendet
