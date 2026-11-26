# network-config Specification

## Purpose

Ermöglicht das Lesen, Validieren und kontrollierte Ändern der kabelgebundenen
IPv4-Konfiguration des Pi über die Weboberfläche, einschließlich DHCP/statisch,
Subnetzmaske, Gateway, DNS und automatischem Rollback bei Aussperrung.

## Requirements

### Requirement: Netzwerkstatus anzeigen

Die Oberfläche SHALL die verwaltete kabelgebundene Schnittstelle mit
Verbindungszustand, aktuellem Modus, IPv4-Adresse, Subnetzmaske, Gateway und DNS
anzeigen. Die API MUST den Status auch dann liefern, wenn gerade eine Änderung
auf Bestätigung wartet; Zugangsdaten oder PIN dürfen darin nicht erscheinen.

#### Scenario: Status im DHCP-Modus

- **WHEN** die Schnittstelle per DHCP eine Adresse bezogen hat
- **THEN** zeigt die Oberfläche Modus `dhcp`, die tatsächlich vergebene Adresse, Subnetzmaske, Gateway und DNS sowie den Verbindungszustand an

#### Scenario: Status im statischen Modus

- **WHEN** die Schnittstelle eine statische Adresse verwendet
- **THEN** zeigt die Oberfläche Modus `static` und die konfigurierten Werte getrennt von der aktuell wirksamen Adresse an

#### Scenario: Laufende Änderung sichtbar

- **WHEN** eine Änderung aktiviert wurde, aber noch nicht bestätigt ist
- **THEN** enthält der Status die Kandidatenwerte, die Ziel-URL, den Ablaufzeitpunkt und die Phase der Änderung

#### Scenario: Backend nicht verfügbar

- **WHEN** NetworkManager nicht erreichbar ist
- **THEN** antwortet die API mit einem verständlichen Fehler und die Oberfläche zeigt den zuletzt bekannten Zustand schreibgeschützt an, ohne eine Änderung vorzutäuschen

### Requirement: DHCP und statisch umschalten

Die API SHALL die Modi `dhcp` und `static` anbieten. Im Modus `static` MUST die
Konfiguration IPv4-Adresse, Subnetzmaske sowie optional Gateway und DNS
enthalten; im Modus `dhcp` MUST sie ohne statische Adressfelder auskommen. Ein
Moduswechsel darf erst durch einen erfolgreichen Apply wirksam werden.

#### Scenario: Wechsel zu statisch

- **WHEN** eine gültige statische Konfiguration angewendet und bestätigt wird
- **THEN** verwendet die Schnittstelle die neue Adresse und den neuen Modus, bis eine andere Konfiguration angewendet wird

#### Scenario: Wechsel zu DHCP

- **WHEN** der Modus `dhcp` angewendet und bestätigt wird
- **THEN** bezieht die Schnittstelle ihre Adresse wieder per DHCP und die zuvor statisch gesetzten Adressfelder sind nicht mehr wirksam

#### Scenario: Widersprüchliche Eingabe

- **WHEN** im Modus `dhcp` eine statische Adresse, Maske, Gateway oder DNS mitgesendet wird
- **THEN** lehnt die API die Eingabe mit einem Feldbezug ab und die aktive Konfiguration bleibt unverändert

### Requirement: Statische IPv4-Werte validieren

Die API SHALL IPv4-Adresse, Subnetzmaske als zusammenhängende Punktnotation,
Gateway und DNS vor jedem Apply prüfen und Feldfehler zurückgeben. Loopback-,
Multicast-, Broadcast- und nicht zuordenbare Adressen MUST abgelehnt werden;
eine bereits auf einer anderen Schnittstelle verwendete Adresse ebenfalls.

#### Scenario: Gültige statische Konfiguration

- **WHEN** Adresse `192.168.10.50`, Maske `255.255.255.0`, Gateway `192.168.10.1` und DNS `192.168.10.1` eingegeben werden
- **THEN** meldet die Validierung Erfolg und die Werte werden unverändert als Kandidat übernommen

#### Scenario: Ungültige Subnetzmaske

- **WHEN** eine Maske wie `255.255.0.255` oder ein Wert außerhalb der Punktnotation eingegeben wird
- **THEN** lehnt die API die Konfiguration mit einem Fehler am Feld Subnetzmaske ab

#### Scenario: Gateway außerhalb des Subnetzes

- **WHEN** das Gateway nicht im durch Adresse und Maske bestimmten Subnetz liegt oder der Adresse selbst entspricht
- **THEN** lehnt die API die Konfiguration mit einem Fehler am Feld Gateway ab

#### Scenario: Ungültiger DNS-Eintrag

- **WHEN** ein DNS-Eintrag keine gültige IPv4-Adresse ist oder mehr als drei Einträge gesendet werden
- **THEN** lehnt die API die Konfiguration mit einem Fehler am Feld DNS ab

#### Scenario: Adresse bereits belegt

- **WHEN** die gewünschte Adresse bereits auf einer anderen Schnittstelle des Pi konfiguriert ist
- **THEN** lehnt die API die Konfiguration ab und nennt die betroffene Schnittstelle

#### Scenario: Gateway und DNS bleiben leer

- **WHEN** im statischen Modus Gateway und DNS leer bleiben
- **THEN** wird die Konfiguration ohne Standardroute und ohne expliziten DNS-Server angenommen und die Oberfläche weist vor dem Anwenden darauf hin

### Requirement: Änderung ohne Wirkung prüfen

Die API SHALL eine Vorschau anbieten, die dieselben Regeln wie der Apply
verwendet, aber weder die aktive Konfiguration noch die laufende Verbindung
verändert. Die Antwort MUST bei Erfolg die Ziel-URL und alle Warnungen
enthalten.

#### Scenario: Gültige Vorschau

- **WHEN** eine gültige Kandidatenkonfiguration zur Prüfung gesendet wird
- **THEN** meldet die API `valid: true`, nennt die Ziel-URL und verändert die aktive Netzwerkkonfiguration nicht

#### Scenario: Ungültige Vorschau

- **WHEN** eine ungültige Kandidatenkonfiguration zur Prüfung gesendet wird
- **THEN** meldet die API die betroffenen Felder und die aktive Konfiguration bleibt unverändert

#### Scenario: Vorschau während einer offenen Änderung

- **WHEN** bereits eine Änderung auf Bestätigung wartet und eine weitere Vorschau angefordert wird
- **THEN** lehnt die API den Aufruf mit einem Konflikt ab, damit keine zwei Kandidaten konkurrieren

### Requirement: Zwei-Phasen-Apply mit Bestätigung

Das Anwenden SHALL die neue Konfiguration zunächst nur temporär aktivieren und
eine Bestätigung innerhalb von 180 Sekunden verlangen. Erst die Bestätigung
MUST die Konfiguration dauerhaft speichern; ohne Bestätigung MUST die vorherige
Konfiguration wiederhergestellt werden. Es darf höchstens eine offene Änderung
geben.

#### Scenario: Änderung starten

- **WHEN** eine gültige Änderung angewendet wird
- **THEN** antwortet die API mit `202`, einer offenen Änderung, der Ziel-URL und dem Ablaufzeitpunkt, bevor die Verbindung durch die Aktivierung getrennt werden kann

#### Scenario: Änderung bestätigen

- **WHEN** die Oberfläche die neue Adresse innerhalb des Fensters erreicht und die Änderung bestätigt
- **THEN** wird die Kandidatenkonfiguration dauerhaft gespeichert, die offene Änderung beendet und der Rollback-Timer gestoppt

#### Scenario: Zweite Änderung während der Bestätigung

- **WHEN** eine weitere Änderung angewendet werden soll, während bereits eine offene Änderung existiert
- **THEN** lehnt die API den Aufruf mit einem Konflikt ab und die offene Änderung bleibt unberührt

#### Scenario: Bestätigung ohne offene Änderung

- **WHEN** eine Bestätigung eintrifft, obwohl keine Änderung offen ist
- **THEN** lehnt die API den Aufruf mit einem Konflikt ab

### Requirement: Automatischer Rollback

Läuft das Bestätigungsfenster ab, ohne dass eine Bestätigung eintrifft, MUST der
Daemon die vorherige Netzwerkkonfiguration wiederherstellen und erneut
aktivieren. Dasselbe gilt bei einem Fehler während der Aktivierung. Nach einem
Rollback MUST der Status wieder die vorherige Konfiguration als wirksam melden
und die offene Änderung entfernt sein.

#### Scenario: Zeitablauf ohne Bestätigung

- **WHEN** innerhalb von 180 Sekunden keine Bestätigung über die neue Adresse eintrifft
- **THEN** stellt der Daemon die vorherige Konfiguration wieder her, aktiviert sie und die Oberfläche ist unter der alten Adresse wieder erreichbar

#### Scenario: Aktivierung schlägt fehl

- **WHEN** die neue Konfiguration von NetworkManager nicht aktiviert werden kann
- **THEN** bleibt beziehungsweise wird die vorherige Konfiguration aktiv und die API meldet den Fehler ohne die vorherige Konfiguration zu verlieren

#### Scenario: Manueller Rollback

- **WHEN** der Benutzer während des Bestätigungsfensters „Zurückrollen“ wählt
- **THEN** wird die vorherige Konfiguration sofort wiederhergestellt und die offene Änderung beendet

#### Scenario: Rollback schlägt fehl

- **WHEN** die vorherige Konfiguration nicht wieder aktiviert werden kann
- **THEN** bleibt die offene Änderung mit einem sichtbaren Fehler bestehen und der Daemon protokolliert den Zustand, ohne ihn als erfolgreich zu melden

### Requirement: Notfall-Adresse bei fehlgeschlagenem Rollback

Kann die vorherige Konfiguration nicht wiederhergestellt werden, SHALL der
Daemon die Standard-Notfall-Adresse `192.168.178.254` mit Maske
`255.255.255.0` ohne Gateway und DNS anwenden. Kurze
Verbindungsunterbrechungen MUST NOT einen sofortigen Rollback auslösen; ein
Rollback erfolgt erst nach dem erfolglosen Bestätigungsfenster oder durch einen
Ausfall des Rollbacks.

#### Scenario: Rollback schlägt fehl

- **WHEN** die vorherige Konfiguration nach Ablauf des Bestätigungsfensters nicht wieder aktiviert werden kann
- **THEN** setzt der Daemon die Notfall-Adresse `192.168.178.254/24` ohne Gateway und DNS und meldet dies als letztes Ergebnis

#### Scenario: Kurze Unterbrechung

- **WHEN** die Verbindung nach dem Anwenden kurzzeitig abbricht, aber innerhalb des Bestätigungsfensters wieder bestätigt wird
- **THEN** bleibt die neue Konfiguration aktiv und es findet kein Rollback statt

### Requirement: Neustart während der offenen Änderung

Der Pending-Zustand SHALL atomar unter `/var/lib/ma2pi/` gespeichert werden und
die vorherige Konfiguration sowie den Ablaufzeitpunkt enthalten. Nach einem
Dienstneustart MUST ein noch gültiges Fenster fortgesetzt und ein abgelaufenes
Fenster zurückgerollt werden.

#### Scenario: Neustart im Bestätigungsfenster

- **WHEN** der Dienst während eines noch nicht abgelaufenen Bestätigungsfensters neu startet
- **THEN** bleibt die Kandidatenkonfiguration aktiv, der Rollback-Timer läuft weiter und der Status zeigt die offene Änderung

#### Scenario: Neustart nach Ablauf

- **WHEN** der Dienst nach Ablauf des Bestätigungsfensters neu startet
- **THEN** rollt er die vorherige Konfiguration zurück, bevor er die offene Änderung als beendet meldet

#### Scenario: Beschädigter Pending-Zustand

- **WHEN** die gespeicherte offene Änderung nicht gelesen werden kann
- **THEN** nimmt der Daemon keine automatische Netzwerkänderung vor, meldet den Fehler und lässt die aktive Konfiguration unangetastet

### Requirement: Schutz vor Aussperren und Zugriff

Die Oberfläche SHALL vor dem Anwenden deutlich warnen, wenn die Änderung
voraussichtlich die Verbindung des aktuellen Browsers trennt, und die zu
erwartende Ziel-URL sowie die erneute PIN-Anmeldung nennen. Bestätigen und
Zurückrollen MUST dieselbe PIN-Session, JSON-Pflicht und den
`X-Ma2pi-Request`-Header verlangen wie andere schreibende API-Aufrufe.

#### Scenario: Warnung bei eigener Verbindung

- **WHEN** die zu ändernde Schnittstelle die Adresse trägt, über die der Browser gerade verbunden ist
- **THEN** zeigt die Oberfläche vor dem Anwenden eine Warnung mit Ziel-URL und dem Hinweis, dass die PIN erneut eingegeben werden muss

#### Scenario: Bestätigung nach Adresswechsel

- **WHEN** die Oberfläche die neue Adresse erreicht und dort eine gültige PIN-Session herstellt
- **THEN** kann sie die offene Änderung bestätigen und den neuen Status laden

#### Scenario: Bestätigung ohne PIN

- **WHEN** die Bestätigung ohne gültige PIN-Session eintrifft
- **THEN** antwortet die API mit `401 pin_required` und die offene Änderung bleibt unverändert

#### Scenario: Schreibaufruf ohne JSON-Header

- **WHEN** ein schreibender Netzwerkaufruf ohne JSON-Inhalt oder ohne den erwarteten Header eintrifft
- **THEN** wird er abgelehnt und die Netzwerkkonfiguration bleibt unverändert

### Requirement: Schnittstellenumfang begrenzen

Die Funktion SHALL genau eine kabelgebundene IPv4-Schnittstelle verwalten und
automatisch die Schnittstelle mit der aktuellen Standardroute bevorzugen. WLAN,
IPv6, mehrere gleichzeitig verwaltete Schnittstellen, VLANs und Bonding MUST NOT
angeboten werden; die Netzwerkkonfiguration MUST NOT in `config.toml` wandern.

#### Scenario: Kabel nicht verbunden

- **WHEN** die verwaltete Schnittstelle keinen Link hat und ein Apply angefordert wird
- **THEN** lehnt die API den Apply mit `409 link_down` ab und die aktive Konfiguration bleibt unverändert

#### Scenario: Keine kabelgebundene Schnittstelle

- **WHEN** der Pi keine kabelgebundene Schnittstelle besitzt
- **THEN** meldet die API, dass keine verwaltbare Schnittstelle vorhanden ist, und die Oberfläche bietet keine Änderung an

#### Scenario: Mehrere kabelgebundene Schnittstellen

- **WHEN** mehrere kabelgebundene Schnittstellen vorhanden sind
- **THEN** wählt der Daemon die Schnittstelle mit der Standardroute, sonst die verbundene, sonst die erste kabelgebundene Schnittstelle und zeigt diese Auswahl sichtbar an

#### Scenario: WLAN wird nicht angeboten

- **WHEN** der Pi zusätzlich eine WLAN-Schnittstelle besitzt
- **THEN** erscheint sie nicht als verwaltbare Schnittstelle und ihre IP-Konfiguration wird nicht verändert

#### Scenario: Konfigurationsdatei bleibt unverändert

- **WHEN** eine Netzwerkänderung gespeichert oder zurückgerollt wird
- **THEN** bleibt `config.toml` unverändert und die Netzwerkeinstellungen liegen ausschließlich bei NetworkManager

### Requirement: Backend und Berechtigungen

Die Funktion SHALL NetworkManager als Netzwerk-Backend verwenden und ohne
root-Rechte des Daemons auskommen. Fehlt NetworkManager oder die notwendige
Polkit-Berechtigung, MUST die API einen verständlichen Fehler liefern und jede
teilweise Änderung unterlassen.

#### Scenario: NetworkManager fehlt

- **WHEN** NetworkManager nicht installiert oder nicht aktiv ist
- **THEN** antwortet die API mit einem Backend-Fehler und die Oberfläche erklärt, dass die Netzwerkverwaltung auf diesem System nicht verfügbar ist

#### Scenario: Polkit verweigert die Aktion

- **WHEN** der Benutzer `ma2pi` die NetworkManager-Aktion nicht ausführen darf
- **THEN** schlägt die Änderung vor der Aktivierung fehl, die aktive Konfiguration bleibt unverändert und die Meldung nennt die fehlende Berechtigung

#### Scenario: Dienst bleibt unprivilegiert

- **WHEN** die Netzwerkfunktion genutzt wird
- **THEN** läuft der Daemon weiterhin als Benutzer `ma2pi` ohne root-Rechte und die systemd-Härtung bleibt aktiv

### Requirement: Live-Aktualisierung

Der Daemon SHALL Änderungen am Netzwerkstatus über den bestehenden
WebSocket-Kanal veröffentlichen, damit mehrere geöffnete Oberflächen denselben
Zustand sehen. Nach einer Unterbrechung MUST sich die Oberfläche wie gewohnt
neu verbinden und den Status über die API nachladen.

#### Scenario: Statusänderung im UI

- **WHEN** eine Änderung gestartet, bestätigt oder zurückgerollt wird
- **THEN** erhalten verbundene Oberflächen ein Netzwerk-Ereignis und zeigen den neuen Zustand ohne manuelles Neuladen

#### Scenario: Verbindung nach Adresswechsel

- **WHEN** die WebSocket-Verbindung durch den Adresswechsel abbricht
- **THEN** verbindet sich die Oberfläche nach dem Öffnen der Ziel-URL und der PIN-Anmeldung erneut und lädt den aktuellen Status
