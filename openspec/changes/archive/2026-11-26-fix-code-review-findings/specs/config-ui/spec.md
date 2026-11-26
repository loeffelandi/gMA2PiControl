# Spec Delta

## ADDED Requirements

### Requirement: Kanonische TOML-Form in der Konfigurations-API

`GET /api/config` SHALL die aktive Konfiguration in derselben Tabellen- und
Schlüsselstruktur ausgeben, die `PUT /api/config` akzeptiert, abzüglich
redaktierter Geheimnisse (`ma2.password_set`, `web.pin_set`). Inaktive
Variantenfelder (`None`) MUST entfallen, und Bank-Ebenen MUST direkt unter
`mapping.device_banks.<gerät>.<bank>` mit `encoders` als Liste liegen. Vom
Client gesendete Felder `ma2.password_file` und `ma2.password_env` MUST
verworfen werden.

#### Scenario: Zweiten Encoder speichern ohne 422

- **WHEN** `GET /api/config` geladen und einer von mehreren Encodern über
  `PUT /api/config` geändert wird
- **THEN** enthalten unveränderte Encoder kein `attribute: null` oder
  `slot: null` und das Speichern gelingt ohne Fehler

#### Scenario: Bank-Ebene und MA-Page überleben Reload und Speichern

- **WHEN** für Bank 2 `ma_page` und zwei Encoder-Overrides gespeichert und die
  Konfiguration neu geladen wird
- **THEN** bleiben beide Overrides und `ma_page` sichtbar und bei weiteren
  Speichervorgängen erhalten

#### Scenario: Kein Einschleusen von `password_file`

- **WHEN** ein Client `PUT /api/config` ohne `password`, aber mit
  `ma2.password_file = "/var/lib/ma2pi/recovery.json"` sendet
- **THEN** liest der Daemon die angegebene Datei nicht und gibt keinen
  Dateifehler preis

### Requirement: Schutz vor DNS-Rebinding und fremden WebSocket-Ursprüngen

Der Webserver SHALL den `Host`-Header gegen IP-Literale, `localhost`, `.local`
und den lokalen Hostnamen prüfen und fremde Domains mit `403` oder `421`
abweisen. Ist bei Schreibanfragen oder auf `/api/events` ein `Origin`-Header
vorhanden, MUST er zum validierten `Host` passen.

#### Scenario: Zugriff über Pi-IP im Show-LAN

- **WHEN** ein Browser `http://192.168.178.21:8080/` oder `http://ma2pi.local:8080/`
  nutzt
- **THEN** werden Lesen, Schreiben und `/api/events` zugelassen

#### Scenario: DNS-Rebinding über fremde Domain

- **WHEN** eine Anfrage mit `Host: attacker.example:8080` eintrifft
- **THEN** lehnt der Server sie vor der Ausführung ab

#### Scenario: Fremder Origin auf `/api/events`

- **WHEN** eine Anfrage mit `Origin: http://example.com` `/api/events` öffnet
- **THEN** lehnt der Server das WebSocket-Upgrade ab

### Requirement: Event-Stream schließt langsame und abgemeldete Clients

Der Event-Stream SHALL je Client eine begrenzte Warteschlange nutzen. Läuft sie
über oder endet eine PIN-Session durch Abmeldung, PIN-Wechsel oder Backup-Restore,
MUST der Server betroffene `/api/events`-WebSockets aktiv schließen und keine
weiteren Events für sie einreihen; andere Clients MUST unbeeinträchtigt bleiben.

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

#### Scenario: WebSocket endet bei PIN-Wechsel oder Abmeldung

- **WHEN** sich der Benutzer abmeldet oder sich die PIN ändert
- **THEN** werden bestehende `/api/events`-WebSockets geschlossen

### Requirement: Vollständige Merge-Patches und Inventar im Mapping-Editor

Die Oberfläche SHALL beim Ändern einer Zuweisung abgelöste Variantenfelder mit
`null` löschen, nach erfolgreichem Speichern ihre Ausgangsmengen aktualisieren
und im Mapping-Editor auch Controls aus `controls.inventory` und `controls.banks`
einschließlich der `accelerated`-Option anbieten.

#### Scenario: Aktionsart im Mapping-Tab wechseln

- **WHEN** eine bestehende Taste von `hardkey` auf `command` oder ein Playback
  von `button` auf `fader` umgestellt wird
- **THEN** setzt der Patch abgelöste Felder auf `null` und speichert ohne `422`

#### Scenario: MIDICRAFT-Encoder im Mapping-Tab beschleunigen

- **WHEN** ein gebanktes Gerät wie `midicraft-enc` angeschlossen ist
- **THEN** zeigt der Mapping-Tab die `accelerated`-Checkbox für dessen
  Inventar-Encoder und speichert Änderungen korrekt

### Requirement: Konsistente Dialoge, Kontrast und Auth-Synchronisation

Im Zuweisungsdialog SHALL „Kein Screen-Encoder“ speicherbar sein, ein entfernter
Screen-Encoder gelöscht werden (`Slot 1..4`), ein geerbter Bank-Offset nicht
unbeabsichtigt eingefroren werden und das Entfernen einer Zuweisung möglich sein.
Dialoge MUST per `Escape` schließbar sein, dunkle Zellen (`black`) MUST Kontrast
`>= 4,5:1` einhalten, Rettungs-WLAN-Fehler MUST `role="alert"` tragen und
PIN-Änderungen oder `401` MUST den Auth-Status der App aktualisieren.

#### Scenario: Attribut-Encoder ohne Screen-Encoder speichern

- **WHEN** im Zuweisungsdialog ein Encoder auf Slot 1 ohne Screen-Encoder
  gespeichert wird
- **THEN** gelingt das Speichern und ein alter Screen-Encoder für Slot 1 wird
  entfernt

#### Scenario: Fehler beim Rettungs-WLAN und Kontrast auf schwarzen Tasten

- **WHEN** `PUT /api/recovery` fehlschlägt oder eine Zelle die Farbe `black` hat
- **THEN** erscheint der Fehler als `role="alert"` im Fehlerstil und der
  Zellentext ist mit mindestens `4,5:1` lesbar

## MODIFIED Requirements

### Requirement: PIN-Sperre der Oberfläche

Die Oberfläche SHALL im LAN erreichbar sein; die optionale PIN-Sperre MUST ohne
Aktivierung aus bleiben und bei fehlender PIN sichtbar warnen. Eine PIN-Session
MUST serverseitig nach höchstens zwölf Stunden ablaufen. Die PIN-Prüfung MUST
serialisiert und längenunabhängig erfolgen, nach fünf Fehlversuchen wachsend
sperren (15 s, verdoppelt bis 300 s, `429 pin_locked` mit `Retry-After`, ohne
während aktiver Sperre weiterzuzählen) und bei PIN-änderndem Backup-Restore
bestehende Sessions widerrufen.

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

- **WHEN** fünfmal hintereinander (auch parallel) eine falsche PIN eingegeben
  wird
- **THEN** antwortet `/api/auth/login` mit `429 pin_locked` und `Retry-After`,
  auch für eine richtige PIN, bis die Sperre abgelaufen ist, ohne den Zähler
  während der Sperre weiter zu erhöhen

#### Scenario: Sperre endet

- **WHEN** die Sperrzeit abgelaufen ist und die richtige PIN eingegeben wird
- **THEN** wird eine Session gesetzt und der Fehlversuchszähler beginnt bei null

#### Scenario: Weitere Fehlversuche verlängern die Sperre

- **WHEN** nach Ende einer Sperre erneut eine falsche PIN eingegeben wird
- **THEN** ist die nächste Sperre doppelt so lang wie die vorherige, höchstens
  300 Sekunden

#### Scenario: Backup-Restore mit geänderter PIN

- **WHEN** ein Backup mit anderer PIN wiederhergestellt wird
- **THEN** werden bisherige Sessions widerrufen

### Requirement: Schreibzugriffe und Geheimnisse

Schreibende API-Aufrufe MUST als JSON mit eigenem Anfrage-Header erfolgen; ein
Körper, der kein JSON-Objekt ist, MUST mit `400 invalid_json` abgelehnt werden.
Antworten und Logs — inklusive Python-Dicts, JSON und Exception-Tracebacks —
MUST NOT das MA2-Passwort, dessen Hash, Tokens, PSKs oder die PIN enthalten.

#### Scenario: Einfacher Formular-POST wird abgelehnt

- **WHEN** ein schreibender Aufruf ohne JSON-Inhalt oder ohne den erwarteten Header eintrifft
- **THEN** wird er mit einem Client-Fehler abgelehnt und die Konfiguration bleibt unverändert

#### Scenario: Körper ist kein Objekt

- **WHEN** `POST /api/learn/start` einen JSON-Array- oder Zeichenketten-Körper
  erhält
- **THEN** antwortet die API mit `400 invalid_json` und startet keine Sitzung

#### Scenario: Geheimnis in Dict oder Traceback wird im Log geschwärzt

- **WHEN** eine Log-Meldung oder ein Traceback `{"password": "geheim"}` oder
  `'pin': '1234'` enthält
- **THEN** erscheint im Log anstelle des Klartexts `***`

### Requirement: Learn-Modus

Der Learn-Modus SHALL das nächste passende Ereignis samt Rohcode oder Bank-Note
erfassen, beim Encoder-Lernen das erste Control fixieren und ein ausbleibendes
Key-Up nach höchstens zwei Sekunden freigeben. Die Oberfläche MUST einen
Abbrechen-Knopf bieten, bei Timeout oder Abbruch alle Schaltflächen freigeben
und beim Verlassen des Tabs laufende Sitzungen abbrechen.

#### Scenario: Taste lernen

- **WHEN** der Learn-Modus für Tasten aktiv ist und eine Taste (auch auf einem
  gebankten MIDI-Gerät) gedrückt wird
- **THEN** zeigt das UI den logischen Control-Namen und den Rohcode oder die
  Note an und sendet keinen MA2-Frame

#### Scenario: Encoder lernen

- **WHEN** der Learn-Modus für einen Encoder aktiv ist und der Encoder gedreht wird
- **THEN** bleibt das zuerst bewegte Control fixiert und das UI zeigt Achse,
  Richtung und Detents an

#### Scenario: Timeout ohne Eingabe

- **WHEN** im Learn-Modus innerhalb der Frist keine passende Eingabe erfolgt
- **THEN** endet der Modus, alle „Lernen“-Schaltflächen sind wieder aktiv und
  der normale Betrieb läuft weiter

#### Scenario: Abbruch durch den Benutzer

- **WHEN** der Benutzer abbricht oder den Tab verlässt
- **THEN** wird die Sitzung abgebrochen und die bisherige Konfiguration bleibt
  aktiv

#### Scenario: Fehlendes Key-Up blockiert den Betrieb nicht

- **WHEN** eine gelernte Taste kein Key-Up liefert
- **THEN** endet die Nachlaufsperre spätestens nach zwei Sekunden
