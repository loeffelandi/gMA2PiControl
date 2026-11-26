# Spec Delta

## Purpose

Stellt eine im LAN erreichbare Weboberfläche und JSON-API bereit, über die
MA2-Zugangsdaten, Geräte und Mapping ohne SSH bearbeitet, gelernt, getestet und
gesichert werden können – ohne externe Assets oder Cloud-Abhängigkeiten.

## ADDED Requirements

### Requirement: Eingebettete Web-Oberfläche

Der Daemon SHALL die statische Svelte-Oberfläche und die JSON-API im selben
Prozess ausliefern. Bind-Adresse und Port MUST konfigurierbar sein; die
Oberfläche MUST ohne Internetverbindung und ohne externe CDN-Ressourcen laden.
Änderungen an Bind-Adresse oder Port werden erst nach einem Dienstneustart
wirksam.

#### Scenario: Oberfläche lädt ohne Internet

- **WHEN** der Browser nur den Pi im LAN erreicht, aber keinen Internetzugang hat
- **THEN** laden HTML, JavaScript, Styles und Schriften vollständig aus lokalen Assets und die Oberfläche ist bedienbar

#### Scenario: Zugriff aus dem LAN

- **WHEN** ein Browser im selben LAN die konfigurierte Adresse und den Port aufruft
- **THEN** wird die Oberfläche ausgeliefert und die API antwortet

#### Scenario: Bind-Adresse geändert

- **WHEN** die Bind-Adresse in der Konfiguration geändert und angewendet wird
- **THEN** meldet die Oberfläche, dass die Änderung erst nach einem Dienstneustart wirksam wird

### Requirement: MA2-Zugangsdaten verwalten

Die API SHALL Host, Port, Pfad und Benutzername lesbar und das Passwort
ausschließlich schreibbar bereitstellen. Das Passwort MUST NOT in einer
Antwort, einem Log oder einer Fehlermeldung erscheinen. Der Verbindungstest MUST
die laufende Session nicht unterbrechen.

#### Scenario: Passwort wird nie zurückgegeben

- **WHEN** die Konfiguration über die API gelesen wird
- **THEN** enthält die Antwort weder das Passwort noch dessen Hash, sondern nur die übrigen MA2-Felder

#### Scenario: Verbindungstest erfolgreich

- **WHEN** im UI gültige Zugangsdaten eingegeben und „Testen“ gewählt wird
- **THEN** meldet die API innerhalb des Timeouts Erfolg und zeigt Benutzer sowie Session-Ziel an

#### Scenario: Verbindungstest fehlgeschlagen

- **WHEN** der Test mit falschem Passwort oder unerreichbarem Host läuft
- **THEN** meldet die API einen verständlichen Fehler, ohne das Passwort oder den Hash auszugeben

#### Scenario: Laufende Session bleibt bestehen

- **WHEN** ein Verbindungstest läuft, während der Daemon bereits mit derselben onPC verbunden ist
- **THEN** bleibt die bestehende Session bestehen und der Test verwendet keine zweite dauerhafte Session

### Requirement: Geräte- und Mapping-Editor

Die Oberfläche SHALL erkannte Geräte und deren logische Controls anzeigen und
das Bearbeiten von Tasten-, Modifier- und Encoder-Mappings ermöglichen. Pro
physischem Encoder MUST zusätzlich das Attribut-Ziel und der Screen-Encoder
(5–8 oder „keiner“) wählbar sein. Vor dem Speichern MUST die Konfiguration mit
denselben Regeln wie der Daemon validiert werden; ungültige Ziele werden mit
Feldbezug abgelehnt.

#### Scenario: Erkannte Geräte werden angezeigt

- **WHEN** die Mapping-Seite geöffnet wird
- **THEN** erscheinen beide konfigurierten Geräte mit Name, Vendor-/Product-ID und ihren verfügbaren Controls

#### Scenario: Taste einer Aktion zuweisen

- **WHEN** eine Taste im Learn-Modus erfasst und einer Hardkey- oder CMD-Aktion zugewiesen wird
- **THEN** erscheint die Zuordnung in der Tabelle und die Validierung meldet keinen Fehler

#### Scenario: Ungültiges Encoder-Ziel

- **WHEN** ein Encoder auf Wheel 11 oder auf ein unbekanntes Attribut gesetzt wird
- **THEN** lehnt die API das Speichern mit einer Feldmeldung ab und die aktive Konfiguration bleibt unverändert

#### Scenario: Screen-Encoder-Namen bearbeiten

- **WHEN** im Mapping-Editor pro physischem Encoder ein Screen-Encoder ausgewählt und gespeichert wird
- **THEN** enthält `mapping.screen_encoders` für den zugeordneten Slot genau diesen Namen und der Screen-Modus verwendet ihn

#### Scenario: Screen-Encoder-Slot leeren

- **WHEN** für einen physischen Encoder `— keiner —` gewählt und gespeichert wird
- **THEN** fehlt der zugeordnete Slot in `mapping.screen_encoders` und im Screen-Modus sendet dieser Slot keine Frames

### Requirement: Learn-Modus

Der Learn-Modus SHALL das nächste passende Eingabeereignis erfassen und im UI
anzeigen, ohne es an die onPC zu senden. Es MUST höchstens eine Learn-Sitzung
gleichzeitig geben; ein Timeout oder Abbruch MUST den normalen Betrieb ohne
Zustandsänderung wiederherstellen.

#### Scenario: Taste lernen

- **WHEN** der Learn-Modus für Tasten aktiv ist und eine Taste gedrückt wird
- **THEN** zeigt das UI den logischen Control-Namen und den Rohcode an und es wird kein MA2-Frame gesendet

#### Scenario: Encoder lernen

- **WHEN** der Learn-Modus für einen Encoder aktiv ist und der Encoder gedreht wird
- **THEN** zeigt das UI Achse, Richtung und die erkannten Detents an

#### Scenario: Timeout ohne Eingabe

- **WHEN** im Learn-Modus innerhalb der Frist keine passende Eingabe erfolgt
- **THEN** endet der Modus, das UI zeigt eine Meldung und der normale Betrieb läuft unverändert weiter

#### Scenario: Abbruch durch den Benutzer

- **WHEN** der Benutzer den Learn-Modus abbricht
- **THEN** wird kein Event übernommen und die vorherige Konfiguration bleibt aktiv

### Requirement: Live-Status

Die Oberfläche SHALL den aktuellen Zustand über eine dauerhafte
WebSocket-Verbindung anzeigen: Verbindung zur onPC, Session, erkannte Geräte,
Rate-Limiter, die letzten Frame-Typen und den aktiven Encoder-Modus
(Attribut oder Screen). Aus dem Encoder-Modus MUST sich ein LED-Zustand
ableiten lassen: grün im Screen-Modus, rot im Attribut-Modus. Zugangsdaten und
Passwort-Hashes MUST NOT Teil der Statusdaten sein. Die UI-Verbindung MUST sich
nach einer Unterbrechung selbstständig wieder aufbauen.

#### Scenario: Verbindungszustand ändert sich

- **WHEN** die onPC neu startet und der Daemon reconnectet
- **THEN** wechselt die Anzeige ohne manuelles Neuladen von „getrennt“ über „verbinde“ zu „verbunden“

#### Scenario: Frame-Aktivität

- **WHEN** Tasten gedrückt oder Encoder gedreht werden
- **THEN** aktualisieren sich Frame-Zähler und die Liste der letzten Frame-Typen in Echtzeit

#### Scenario: Encoder-Modus sichtbar

- **WHEN** die Screen-Modus-Taste am Gerät gedrückt wird
- **THEN** meldet der Status innerhalb einer Sekunde den neuen Modus und die Oberfläche zeigt den passenden LED-Zustand

#### Scenario: UI-Verbindung bricht ab

- **WHEN** die WebSocket-Verbindung des Browsers zum Daemon unterbrochen wird
- **THEN** baut die Oberfläche die Verbindung automatisch wieder auf und zeigt den aktuellen Zustand

### Requirement: Konfigurations-Backups

Die Oberfläche SHALL Konfigurations-Backups anlegen, auflisten und
wiederherstellen können. Eine Wiederherstellung MUST validiert und als
Bestätigungsschritt ausgeführt werden; bei ungültigem Backup bleibt die aktive
Konfiguration unverändert.

#### Scenario: Backup anlegen und wiederherstellen

- **WHEN** ein Backup erstellt, die Konfiguration geändert und anschließend das Backup wiederhergestellt wird
- **THEN** ist die ursprüngliche Konfiguration aktiv und die Änderung wurde rückgängig gemacht

#### Scenario: Ungültiges Backup

- **WHEN** ein beschädigtes oder schemawidriges Backup wiederhergestellt werden soll
- **THEN** lehnt die API den Vorgang ab und die aktive Konfiguration bleibt unverändert

### Requirement: PIN-Sperre der Oberfläche

Die Oberfläche SHALL im LAN erreichbar sein. Eine einfache PIN-Sperre MUST
optional konfigurierbar sein und ohne explizite Aktivierung aus bleiben. Ist
keine PIN gesetzt, MUST die Oberfläche sichtbar warnen. Ist eine PIN aktiv,
MUST die Oberfläche eine Sperrseite zeigen und die API außer den öffentlichen
Auth-Endpunkten authentifizieren.

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

### Requirement: Schreibzugriffe und Geheimnisse

Schreibende API-Aufrufe MUST als JSON mit einem eigenen Anfrage-Header
erfolgen. Antworten und Logs MUST NOT das MA2-Passwort, dessen Hash oder die
PIN enthalten.

#### Scenario: Einfacher Formular-POST wird abgelehnt

- **WHEN** ein schreibender Aufruf ohne JSON-Inhalt oder ohne den erwarteten Header eintrifft
- **THEN** wird er mit einem Client-Fehler abgelehnt und die Konfiguration bleibt unverändert
