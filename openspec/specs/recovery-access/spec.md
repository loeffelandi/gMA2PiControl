# recovery-access Specification

## Purpose

Stellt über ein eigenes WLAN einen Rettungszugang zur Konfigurationsoberfläche
bereit, wenn das kabelgebundene Verwaltungsnetz fehlt oder eine
Netzwerkänderung fehlgeschlagen ist.

## Requirements

### Requirement: Rettungs-Hotspot

Der Daemon SHALL auf der WLAN-Schnittstelle einen Hotspot mit dem Profil
`ma2pi-recovery` und dem internen DHCP-Dienst von NetworkManager betreiben. Der
Hotspot MUST standardmäßig aus sein, über die Oberfläche ein- und ausgeschaltet
werden können und unter `192.168.50.1` sowie der konfigurierten SSID erreichbar
sein.

#### Scenario: Hotspot manuell einschalten

- **WHEN** der Benutzer den Rettungs-Hotspot in der Oberfläche aktiviert
- **THEN** spannt `wlan0` ein WPA2-geschütztes WLAN mit der konfigurierten SSID auf, vergibt per DHCP Adressen aus `192.168.50.0/24` und die Oberfläche ist unter `http://192.168.50.1:<port>/` erreichbar

#### Scenario: Hotspot ausschalten

- **WHEN** der Benutzer den Rettungs-Hotspot deaktiviert
- **THEN** wird das AP-Profil deaktiviert und die normale WLAN-Verbindung kann wieder aufgebaut werden

#### Scenario: Keine WLAN-Schnittstelle

- **WHEN** der Pi keine WLAN-Schnittstelle besitzt
- **THEN** meldet die API den Rettungs-Hotspot als nicht verfügbar und die Oberfläche bietet keine Aktivierung an

### Requirement: Zugangsdaten des Rettungs-WLANs

SSID und WLAN-Passwort SHALL in der Oberfläche änderbar sein. Die SSID MUST 1–32
Zeichen und das Passwort 8–63 Zeichen lang sein. Das Standardpasswort MUST in
der Oberfläche sichtbar und änderbar sein; der Zugriff auf die Oberfläche bleibt
zusätzlich durch die PIN geschützt.

#### Scenario: Zugangsdaten ändern

- **WHEN** SSID oder Passwort im Rettungsbereich geändert und gespeichert werden
- **THEN** wird das AP-Profil mit den neuen Werten neu aktiviert und die Oberfläche zeigt die neuen Zugangsdaten

#### Scenario: Ungültige Zugangsdaten

- **WHEN** eine leere SSID oder ein Passwort außerhalb von 8–63 Zeichen gespeichert werden soll
- **THEN** lehnt die API die Änderung mit einem Feldbezug ab und der laufende Hotspot bleibt unverändert

### Requirement: Automatischer Rettungszugang

Der Daemon SHALL den Hotspot nach einer anhaltenden fehlenden kabelgebundenen
Verbindung automatisch aktivieren und nach einer anhaltenden stabilen
Rückkehr des LANs wieder deaktivieren. Kurze Verbindungsabbrüche MUST NOT den
Hotspot sofort ein- oder ausschalten. Der Zustand MUST einen Dienstneustart
überleben.

#### Scenario: LAN fehlt länger als die Karenzzeit

- **WHEN** die kabelgebundene Schnittstelle länger als 60 Sekunden keine nutzbare IPv4-Adresse hat und die Automatik aktiv ist
- **THEN** aktiviert der Daemon den Rettungs-Hotspot und markiert ihn als automatisch aktiviert

#### Scenario: LAN kehrt stabil zurück

- **WHEN** die kabelgebundene Verbindung länger als 60 Sekunden stabil ist und der Hotspot automatisch aktiviert wurde
- **THEN** deaktiviert der Daemon den Hotspot wieder

#### Scenario: Kurzer Ausfall

- **WHEN** die LAN-Verbindung nur kurz unterbrochen wird und vor Ablauf der Karenzzeit zurückkehrt
- **THEN** bleibt der Hotspot unverändert

#### Scenario: Neustart mit aktivem Hotspot

- **WHEN** der Dienst neu startet und der Hotspot zuvor aktiviert war
- **THEN** wird der Hotspot beim Start wieder aktiviert

### Requirement: WLAN-Konflikt und Sicherheit

Das Aktivieren des Hotspots MUST die bestehende WLAN-Verbindung auf derselben
Schnittstelle trennen dürfen; die Oberfläche MUST darauf hinweisen. Der Hotspot
MUST WPA2 verwenden, und alle schreibenden Aufrufe MUST denselben PIN-,
JSON- und Header-Schutz wie die übrige API verwenden.

#### Scenario: Bestehende WLAN-Verbindung

- **WHEN** der Hotspot aktiviert wird, während `wlan0` mit einem anderen WLAN verbunden ist
- **THEN** wird die bisherige WLAN-Verbindung getrennt und der Hinweis in der Oberfläche erklärt diesen Effekt

#### Scenario: Schreibzugriff ohne PIN

- **WHEN** die Rettungs-Einstellungen ohne gültige PIN-Session geändert werden sollen
- **THEN** antwortet die API mit `401 pin_required` und der Hotspot bleibt unverändert

### Requirement: Atomare Validierung, Locking und monotone Karenzzeit

`PUT /api/recovery` SHALL strikte JSON-Typen, `1..32` UTF-8-Bytes ohne
Steuerzeichen für die SSID sowie `8..63` druckbare ASCII-Zeichen für das
Passwort verlangen und bei `nmcli`-Fehlern Speicher sowie `recovery.json` auf
den vorherigen Stand zurücksetzen. `auto_cycle` MUST unter demselben Lock und
mit `time.monotonic` laufen.

#### Scenario: Fehlgeschlagenes `nmcli` erhält bisherigen Hotspot-Zustand

- **WHEN** der Hotspot aktiv ist und das Anwenden neuer Werte in `nmcli`
  fehlschlägt
- **THEN** bleiben die bisherigen Einstellungen in Speicher und `recovery.json`
  erhalten

#### Scenario: Mehrbyte-SSID über 32 UTF-8-Bytes wird abgelehnt

- **WHEN** eine SSID mit mehr als 32 UTF-8-Bytes gesendet wird
- **THEN** antwortet die API mit `422 validation_error` und Feldbezug `ssid`

### Requirement: Konsistenter Hotspot-Zustand bei Dateischreibfehlern

Schlägt in `RecoveryService` das Persistieren von `recovery.json` nach einer
bereits in NetworkManager angewendeten Änderung fehl, MUST der Dienst auch den
Live-Zustand in NetworkManager nach bestem Bemühen auf den vorherigen Stand
zurücksetzen, damit Speicher, Datei und Schnittstelle übereinstimmen.

#### Scenario: Schreibfehler auf `recovery.json` lässt keinen Geister-Hotspot aktiv

- **WHEN** das Einschalten des Hotspots in NetworkManager gelingt, das Schreiben
  von `recovery.json` aber mit `OSError` fehlschlägt
- **THEN** deaktiviert der Dienst das AP-Profil wieder und behält den alten
  Zustand bei
