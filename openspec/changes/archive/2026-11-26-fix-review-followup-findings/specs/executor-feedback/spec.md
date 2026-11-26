# Spec Delta

## ADDED Requirements

### Requirement: Aktuelle Master-Page bleibt auf Seiten mit festem Ziel aktiv

Ein Abfrageblock mit `page = "current"` SHALL Antworten der grandMA2 auch dann
akzeptieren, wenn die aktuell gewählte Master-Page mit einer Seite übereinstimmt,
für die zusätzlich ein festes Playback-Ziel konfiguriert ist.

#### Scenario: Master-Page wechselt auf eine ebenfalls fest überwachte Seite

- **WHEN** sowohl `page = "current"` als auch `page = 2` überwacht werden und
  der Bediener in der onPC auf Master-Page 2 wechselt
- **THEN** verarbeitet `ExecutorFeedback` die `"current"`-Antwort für Seite 2
  ohne Timeout und aktualisiert die `"current"`-LEDs weiter
