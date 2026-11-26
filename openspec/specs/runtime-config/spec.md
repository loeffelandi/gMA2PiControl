# runtime-config Specification

## Purpose
Wendet validierte Konfigurationsänderungen im laufenden Betrieb atomar an, ohne
den Daemon oder die systemd-Unit neu zu starten, und schützt dabei gehaltene
Tasten, laufende Encoder-Deltas und die MA2-Session vor inkonsistenten
Zwischenzuständen.

## Requirements

### Requirement: Validierung vor dem Anwenden

Jede Konfigurationsänderung SHALL vor dem Schreiben und Anwenden mit denselben
Regeln wie der Daemon-Start validiert werden. Bei einem Fehler MUST die aktive
Konfiguration unverändert bleiben, die API MUST die betroffenen Felder nennen und
es dürfen keine Frames auf Basis der ungültigen Konfiguration entstehen.

#### Scenario: Ungültige Änderung wird abgelehnt

- **WHEN** eine Änderung mit Wheel 11 oder einer unbekannten Hardkey-Referenz angewendet werden soll
- **THEN** antwortet die API mit einem Validierungsfehler und die bisherige Konfiguration bleibt vollständig aktiv

#### Scenario: Gültige Änderung wird angenommen

- **WHEN** eine schemakonforme Änderung angewendet wird
- **THEN** wird sie validiert, gespeichert und als neue aktive Generation gemeldet

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

Vor dem Aktivieren einer neuen Konfiguration SHALL der Daemon alle gehaltenen
Tasten in umgekehrter Press-Reihenfolge freigeben und offene Encoder-Deltas
verwerfen. Die Releases MUST vor dem ersten Frame aus der neuen Konfiguration
gesendet werden. Nach dem Tausch MUST kein Modifier aus der alten Konfiguration
hängen bleiben.

#### Scenario: Apply bei gehaltener MA-Taste

- **WHEN** MA und Store gehalten werden und eine neue Konfiguration angewendet wird
- **THEN** werden Store und MA in dieser umgekehrten Reihenfolge freigegeben, bevor die neue Konfiguration den ersten Frame sendet

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
