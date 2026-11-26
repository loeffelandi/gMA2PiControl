# Spec Delta

## ADDED Requirements

### Requirement: Monotone Zeitmessung und vollständige Gateway-/DNS-Prüfung

Der Daemon SHALL das Bestätigungsfenster für Netzwerkänderungen intern mit
`time.monotonic` in einer Schleife bis zum Fristablauf überwachen. Für statische
IPv4-Werte MUST die Validierung Loopback-, Broadcast-, unbestimmte und
reservierte Adressen sowohl bei `gateway` als auch bei `dns` ablehnen.

#### Scenario: NTP-Zeitsprung nach Aktivierung löst keinen Sofort-Rollback aus

- **WHEN** nach dem Aktivieren einer neuen Netzwerkkonfiguration die Systemuhr
  vorgestellt wird
- **THEN** läuft das 180-Sekunden-Bestätigungsfenster ungestört weiter

#### Scenario: Minimales frühes Aufwachen lässt Rollback nicht ausfallen

- **WHEN** `sleep` kurz vor der monotonen Frist aufwacht und keine Bestätigung
  vorliegt
- **THEN** wartet der Timer die Restzeit ab und rollt zuverlässig zurück
