# runtime-config Specification

## Purpose
Wendet validierte Konfigurationsänderungen im laufenden Betrieb atomar an, ohne
den Daemon oder die systemd-Unit neu zu starten, und schützt dabei gehaltene
Tasten, laufende Encoder-Deltas und die MA2-Session vor inkonsistenten
Zwischenzuständen.

## Requirements

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

### Requirement: Atomares Schreiben und Backup

Die Konfiguration SHALL in eine temporäre Datei im Zielverzeichnis geschrieben,
synchronisiert und anschließend atomar ersetzt werden. Vor jedem Ersetzen MUST
die bisherige Datei als Backup erhalten bleiben. Ein Abbruch während des
Schreibens darf weder eine halbe Datei noch einen Verlust der alten
Konfiguration verursachen; Kommentare und Formatierung MUST mit `tomlkit`
erhalten bleiben.

#### Scenario: Abbruch vor dem Ersetzen

- **WHEN** der Prozess zwischen temporärer Datei und atomarem Ersetzen beendet wird
- **THEN** ist die bisherige Konfiguration unverändert und vollständig lesbar

#### Scenario: Kommentare bleiben erhalten

- **WHEN** eine Konfiguration mit Kommentaren über die API geändert wird
- **THEN** enthält die gespeicherte Datei weiterhin die Kommentare an den unveränderten Stellen

#### Scenario: Backup der Vorgängerversion

- **WHEN** eine neue Konfiguration erfolgreich ersetzt wurde
- **THEN** liegt die vorherige Version als Backup vor und ist über die Oberfläche wiederherstellbar

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

### Requirement: Mapping-Tausch ohne Replay

Nach erfolgreichem Apply SHALL jedes neu eintreffende Eingabeereignis das neue
Mapping verwenden. Bereits gesendete Frames MUST NOT rückgängig gemacht oder
nachträglich wiederholt werden; es findet kein Replay alter Presses statt.

#### Scenario: Taste wird neu zugewiesen

- **WHEN** die Fix-Taste von „Fix“ auf „Store“ umgemappt und die Konfiguration angewendet wird
- **THEN** sendet der nächste Tastendruck „Store“ und nicht erneut „Fix“

#### Scenario: Kein Replay nach dem Tausch

- **WHEN** vor dem Apply eine Taste gedrückt war und danach eine andere Taste gedrückt wird
- **THEN** wird nur die neue Taste gesendet und die alte nicht erneut ausgelöst

### Requirement: Zugangsdaten ändern und Reconnect

Änderungen an Host, Port, Pfad, Benutzername oder Passwort SHALL vor dem Apply
durch einen erfolgreichen Verbindungstest bestätigt werden. Bei Erfolg MUST die
alte Session sauber geschlossen und eine neue aufgebaut werden; bei Fehler MUST
das Apply abgelehnt werden und die alte Konfiguration aktiv bleiben. Reine
Mapping-Änderungen dürfen die bestehende Session nicht unterbrechen.

#### Scenario: Neuer Host mit gültigen Daten

- **WHEN** der Host geändert wird und der Verbindungstest erfolgreich ist
- **THEN** wird die alte Session geschlossen, die neue Konfiguration aktiviert und eine Session zum neuen Host aufgebaut

#### Scenario: Falsches Passwort beim Apply

- **WHEN** ein neues Passwort den Verbindungstest nicht besteht
- **THEN** wird das Apply abgelehnt und die bisherige Konfiguration und Session bleiben unverändert

#### Scenario: Nur Mapping geändert

- **WHEN** ausschließlich Tasten- oder Encoder-Mapping geändert wird
- **THEN** bleibt die bestehende MA2-Session verbunden und wird nicht neu aufgebaut

### Requirement: Ein Apply gleichzeitig

Es SHALL höchstens ein Apply gleichzeitig laufen. Ein zweiter Aufruf während
eines laufenden Apply MUST abgelehnt oder bis zum Abschluss zurückgestellt
werden. Nach erfolgreichem Apply MUST die API eine neue Konfigurationsgeneration
melden.

#### Scenario: Zwei gleichzeitige Apply-Aufrufe

- **WHEN** zwei Clients nahezu gleichzeitig eine Änderung anwenden wollen
- **THEN** wird genau eine Änderung übernommen und der zweite Aufruf erhält eine eindeutige Ablehnung oder wartet auf den Abschluss

#### Scenario: Generation steigt

- **WHEN** ein Apply erfolgreich abgeschlossen ist
- **THEN** ist die gemeldete Konfigurationsgeneration um eins höher als vorher

### Requirement: Kein Dienstneustart

Ein Apply SHALL den Daemon-Prozess und die systemd-Unit weiterlaufen lassen. Die
Prozess-ID MUST unverändert bleiben und der Dienst MUST NOT neu gestartet
werden.

#### Scenario: Mapping-Änderung ohne Neustart

- **WHEN** eine Mapping-Änderung angewendet wird
- **THEN** bleibt die Prozess-ID gleich, die Unit läuft weiter und die Änderung ist sofort aktiv

#### Scenario: Kein systemd-Eingriff

- **WHEN** ein Apply über die Oberfläche ausgelöst wird
- **THEN** erscheint im Journal kein neuer Dienststart und die Laufzeit der Unit wird nicht zurückgesetzt

### Requirement: Verbindungsfehler nach erfolgreichem Apply

Scheitert die Verbindung nach einem erfolgreichen Apply, MUST die neue
Konfiguration aktiv bleiben, der Fehler im Status sichtbar sein und der normale
Reconnect mit Backoff greifen. Ein automatisches Zurückrollen auf die alte
Konfiguration darf nicht stattfinden, weil die Zugangsdaten zuvor getestet
wurden.

#### Scenario: onPC nach Apply nicht erreichbar

- **WHEN** die Konfiguration erfolgreich angewendet wurde und die onPC danach ausfällt
- **THEN** bleibt die neue Konfiguration aktiv, die Oberfläche zeigt „getrennt“ und der Daemon versucht den Reconnect mit Backoff

#### Scenario: Wiederherstellung über Backup

- **WHEN** der Benutzer nach einem fehlgeschlagenen Verbindungsaufbau ein älteres Backup wiederherstellt
- **THEN** wird dieses validiert, angewendet und der Verbindungsaufbau mit den alten Daten erneut versucht

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

### Requirement: Sauberer Resolver-Lebenszyklus, Sende-Timeout und Quote-Redaction

`ScreenHelper` SHALL laufende asynchrone Namensauflösungen referenzieren, den
zuletzt angeforderten Screen koaleszieren und offene Auflösungen in `close()`
abbrechen, ohne geschlossene Sockets neu zu öffnen. Der Event-Stream MUST
blockierende WebSocket-Schreibvorgänge zeitlich begrenzen beziehungsweise bei
gesetztem `dropped`-Signal abbrechen, und die Log-Redaction MUST auch maskierte
Anführungszeichen (`\"`, `\'`) innerhalb geheimer Werte vollständig schwärzen.

#### Scenario: ScreenHelper wird während laufender DNS-Auflösung geschlossen

- **WHEN** `ScreenHelper.close()` aufgerufen wird, während `getaddrinfo` noch
  läuft
- **THEN** wird die Auflösung abgebrochen und es bleibt kein offener UDP-Socket
  zurück
