# Spec Delta

## ADDED Requirements

### Requirement: Gezielter PIN-Session-Widerruf bei Konfigurationsänderungen

`PUT /api/config` SHALL bestehende PIN-Sessions und `/api/events`-WebSockets nur
dann trennen, wenn sich `web.pin_enabled` oder `web.pin` tatsächlich gegenüber
der vorherigen Konfiguration geändert hat. Ein vorübergehender Auth-Fehler in
der App-Hülle MUST nach erfolgreicher Erholung wieder ausgeblendet werden.

#### Scenario: Ändern des Log-Levels trennt andere PIN-Sessions nicht

- **WHEN** auf `AdvancedPage` nur `logging.level` oder `rate` gespeichert wird,
  während die PIN unverändert aktiv bleibt
- **THEN** bleiben bestehende PIN-Sessions und WebSockets anderer Clients
  verbunden

### Requirement: Dedupliziertes Lernen und vollständige Validierung im Mapping-Tab

Der Mapping-Tab SHALL `learnStore`-Zustände deduplizieren, damit ein früheres
Lernergebnis keine neu gestartete Sitzung beendet, leere `hardkey`-Modifier vor
dem Speichern mit Fehlermeldung abweisen, frei benannte `relative-encoder` über
`encoder_id` auflösen und unbelegte Bank-Controls nicht als Note `0` anzeigen.

#### Scenario: Zweites Lernen wird nicht durch alten Status beendet

- **WHEN** nach einer beendeten Learn-Sitzung eine zweite Learn-Sitzung im
  Mapping-Tab gestartet wird und reguläre Status-Events eintreffen
- **THEN** bleibt die neue Learn-Sitzung aktiv, bis eine neue Eingabe, ein
  Timeout oder ein Abbruch eintrifft

### Requirement: Konsistente Dialog-, LearnPanel- und StatusPage-Zustandsführung

Die Oberfläche SHALL `StatusStore` an `DevicesPage` und `LearnPanel` übergeben,
`startedSession` bei beendeter Sitzung zurücksetzen, beim Gerätewechsel offene
Dialoge/Learn-Panels schließen und `ApiError.detail` anzeigen. `AssignDialog`
MUST bei `Attributname`, `Page` und `Schrittweite` gültige Eingaben prüfen,
Screen-Encoder je Slot aktualisieren und Vererbung sowie `[mapping.modifiers]`
korrekt behandeln; `StatusPage` MUST nach `seq` scrollen und Replugs neu laden.

#### Scenario: Leerer Attributname im Zuweisungsdialog wird abgefangen

- **WHEN** im `AssignDialog` der Modus „Attributname“ mit leerem Eingabefeld
  gespeichert werden soll
- **THEN** zeigt der Dialog einen Validierungsfehler und überschreibt weder
  `Slot 1` noch dessen Screen-Encoder
