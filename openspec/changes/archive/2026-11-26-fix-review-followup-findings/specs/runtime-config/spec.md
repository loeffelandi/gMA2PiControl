# Spec Delta

## ADDED Requirements

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
