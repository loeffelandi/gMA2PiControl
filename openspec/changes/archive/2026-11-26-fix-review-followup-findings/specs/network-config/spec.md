# Spec Delta

## ADDED Requirements

### Requirement: Gedeckelte Restfrist nach Neustart und Formular-Resync nach Rollback

Beim Fortsetzen einer offenen Netzwerkänderung nach Dienstneustart (`resume`)
MUST der Daemon die verbleibende Bestätigungsfrist nach oben auf
`confirm_timeout` begrenzen. Endet eine offene Änderung über den WebSocket durch
Rollback oder Bestätigung, MUST `NetworkPage` die Formularfelder mit den wieder
aktiven Schnittstellenwerten synchronisieren.

#### Scenario: Formular zeigt nach automatischem Rollback wieder die aktive IP

- **WHEN** das Bestätigungsfenster abläuft und der WebSocket `pending: null`
  meldet
- **THEN** lädt `NetworkPage` den aktuellen Status neu und setzt die
  Eingabefelder auf die wiederhergestellte Konfiguration zurück
