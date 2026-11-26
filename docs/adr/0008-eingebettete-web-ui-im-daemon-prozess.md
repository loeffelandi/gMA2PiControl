# 0008. Eingebettete Web-UI im Daemon-Prozess

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

## Kontext und Problemstellung

Der Core-Daemon ist headless und wird über TOML und CLI konfiguriert. Für
Zugangsdaten, Geräte-Mapping und den Learn-Modus ist das ohne SSH kaum
bedienbar. Es braucht eine Web-Oberfläche, die im LAN erreichbar ist und den
laufenden Zustand (Verbindung, Geräte, Frames) kennt. Gleichzeitig soll der
Pi weiterhin ein einzelner, wartbarer Dienst bleiben.

## Entscheidungstreiber

* Ein Prozess und ein Event-Loop für HID, MA2, Config und UI
* Direkter Zugriff der UI auf Geräte-, Session- und Learn-Zustand
* Kein zweiter Dienst, kein nginx, keine zusätzliche Datenbank
* Statische Auslieferung ohne Internet/CDN
* Klare Trennung zwischen API, Config-Store und Runtime

## Betrachtete Optionen

* Separater Web-Dienst (FastAPI/uvicorn) neben dem Daemon
* Eingebetteter `aiohttp`-Server im Daemon-Prozess
* Nur statische Dateien über einen vorhandenen Webserver, API separat
* Kein UI, nur CLI

## Entscheidung

Die Web-Oberfläche wird in den Daemon-Prozess eingebettet. `aiohttp` läuft im
selben asyncio-Loop und liefert die statische SPA aus `web/dist` sowie die
JSON-API unter `/api`. Live-Daten laufen über einen WebSocket unter
`/api/events`. Es gibt keinen zweiten Dienst und keinen externen Webserver.

### Konsequenzen

* Gut, weil UI, Geräte und MA2-Session denselben Zustand teilen.
* Gut, weil nur ein Lifecycle, ein Log und ein systemd-Dienst existieren.
* Gut, weil keine zusätzliche Infrastruktur auf dem Pi nötig ist.
* Schlecht, weil ein Fehler im Web-Teil den Daemon beeinflussen kann; Handler werden gekapselt und dürfen den Event-Loop nicht blockieren.
* Schlecht, weil `aiohttp` als weitere Laufzeitabhängigkeit hinzukommt.
* Schlecht, weil UI und Daemon gemeinsam deployed und versioniert werden müssen.

### Bestätigung

Accepted, wenn die UI aus dem LAN erreichbar ist, Live-Events über WebSocket
ankommen, ein Fehler in einem API-Handler den Daemon nicht beendet und kein
zweiter Prozess für die UI läuft.

## Vor- und Nachteile der Optionen

### Separater Web-Dienst

* Gut, weil UI und Daemon unabhängig skaliert und neu gestartet werden könnten.
* Schlecht, weil beide Zugriff auf Geräte und Session brauchen und eine IPC-Schicht nötig wäre.
* Schlecht, weil zwei Dienste, zwei Logs und zwei Fehlerdomänen entstehen.

### Eingebetteter aiohttp-Server

* Gut, weil ein Prozess und ein Zustand.
* Gut, weil WebSocket und Static Files ohne Zusatzinfrastruktur verfügbar sind.
* Schlecht, weil der Daemon mehr Verantwortung trägt und die Handler sauber gekapselt werden müssen.

### Statische Dateien plus separate API

* Gut, weil der Webserver getauscht werden könnte.
* Schlecht, weil immer noch eine API im Daemon nötig wäre und die Trennung keinen praktischen Nutzen bringt.

### Kein UI

* Gut, weil kein zusätzlicher Angriffsflächen- und Wartungsaufwand.
* Schlecht, weil Konfiguration und Learn-Modus nur mit SSH und Spezialwissen bedienbar bleiben.

## Weitere Informationen

* Verwandt: ADR-0004, ADR-0009, ADR-0011, ADR-0013
