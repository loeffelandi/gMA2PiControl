# Spec Delta

## ADDED Requirements

### Requirement: Event-Stream schließt langsame Clients

Der Event-Stream SHALL je Client eine begrenzte Warteschlange verwenden. Läuft
sie über, MUST der Server den WebSocket dieses Clients schließen und weitere
Events nicht mehr für ihn einreihen; andere Clients MUST unbeeinträchtigt
bleiben. Die Oberfläche verbindet sich neu und erhält den aktuellen Stand als
Anfangsereignis.

#### Scenario: Client liest zu langsam

- **WHEN** die Warteschlange eines Clients voll ist und ein weiteres Event
  veröffentlicht wird
- **THEN** wird dessen WebSocket geschlossen und der Daemon blockiert nicht

#### Scenario: Andere Clients bleiben verbunden

- **WHEN** ein Client wegen Überlaufs getrennt wird
- **THEN** erhalten alle übrigen Clients weiter jedes Event

#### Scenario: Wiederverbinden

- **WHEN** ein getrennter Client erneut `/api/events` öffnet
- **THEN** erhält er zuerst den aktuellen Status und danach neue Events

## MODIFIED Requirements

### Requirement: PIN-Sperre der Oberfläche

Die Oberfläche SHALL im LAN erreichbar sein. Eine einfache PIN-Sperre MUST
optional konfigurierbar sein und ohne explizite Aktivierung aus bleiben. Ist
keine PIN gesetzt, MUST die Oberfläche sichtbar warnen. Ist eine PIN aktiv,
MUST die Oberfläche eine Sperrseite zeigen und die API außer den öffentlichen
Auth-Endpunkten authentifizieren. Eine PIN-Session MUST serverseitig nach
höchstens zwölf Stunden ablaufen, unabhängig vom Cookie. Nach fünf
aufeinanderfolgenden falschen PINs MUST der Login für eine wachsende Zeit
gesperrt werden (15 s, verdoppelt je weiterem Fehlversuch, höchstens 300 s);
eine richtige PIN setzt den Zähler zurück.

#### Scenario: Zugriff ohne PIN

- **WHEN** keine PIN aktiviert ist
- **THEN** ist die API offen und die Oberfläche zeigt oben einen Warnbanner

#### Scenario: Zugriff mit PIN

- **WHEN** ein Client im LAN die Oberfläche oder eine geschützte API aufruft
- **THEN** wird ohne gültige PIN-Session die Sperrseite beziehungsweise `401 pin_required` geliefert

#### Scenario: PIN-Anmeldung

- **WHEN** der Benutzer die korrekte PIN eingibt
- **THEN** wird eine Session gesetzt und die Oberfläche lädt die Live-Daten

#### Scenario: Falsche PIN

- **WHEN** eine falsche PIN eingegeben wird
- **THEN** bleibt der Zugriff gesperrt und die Antwort enthält die PIN nicht

#### Scenario: PIN-Sperre deaktiviert

- **WHEN** `web.pin_enabled` auf `false` gesetzt ist
- **THEN** verhält sich die Oberfläche wie im offenen LAN-Modus, zeigt keinen Login-Schritt und warnt oben, dass keine PIN gesetzt ist

#### Scenario: Session läuft ab

- **WHEN** eine PIN-Session älter als zwölf Stunden ist
- **THEN** antwortet die API mit `401 pin_required`, auch wenn der Browser das
  Cookie noch sendet

#### Scenario: Sperre nach Fehlversuchen

- **WHEN** fünfmal hintereinander eine falsche PIN eingegeben wird
- **THEN** antwortet `/api/auth/login` mit `429 pin_locked` und `Retry-After`,
  auch für eine richtige PIN, bis die Sperre abgelaufen ist

#### Scenario: Sperre endet

- **WHEN** die Sperrzeit abgelaufen ist und die richtige PIN eingegeben wird
- **THEN** wird eine Session gesetzt und der Fehlversuchszähler beginnt bei null

#### Scenario: Weitere Fehlversuche verlängern die Sperre

- **WHEN** nach Ende einer Sperre erneut eine falsche PIN eingegeben wird
- **THEN** ist die nächste Sperre doppelt so lang wie die vorherige, höchstens
  300 Sekunden

### Requirement: Schreibzugriffe und Geheimnisse

Schreibende API-Aufrufe MUST als JSON mit einem eigenen Anfrage-Header
erfolgen. Antworten und Logs MUST NOT das MA2-Passwort, dessen Hash oder die
PIN enthalten. Endpunkte, die einen JSON-Körper erwarten, MUST einen Körper,
der kein JSON-Objekt ist, mit `400 invalid_json` ablehnen und dürfen nicht mit
einem Serverfehler antworten.

#### Scenario: Einfacher Formular-POST wird abgelehnt

- **WHEN** ein schreibender Aufruf ohne JSON-Inhalt oder ohne den erwarteten Header eintrifft
- **THEN** wird er mit einem Client-Fehler abgelehnt und die Konfiguration bleibt unverändert

#### Scenario: Körper ist kein Objekt

- **WHEN** `POST /api/learn/start` einen JSON-Array- oder Zeichenketten-Körper
  erhält
- **THEN** antwortet die API mit `400 invalid_json` und startet keine
  Learn-Sitzung
