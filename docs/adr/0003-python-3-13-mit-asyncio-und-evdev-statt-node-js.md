# 0003. Python 3.13 mit asyncio und evdev statt Node.js

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Ergänzt durch [14. ASL MK2 E4B3 als MIDI-Geraet hinter der Input-Schnittstelle](0014-asl-mk2-e4b3-als-midi-geraet-hinter-der-input-schnittstelle.md)

## Kontext und Problemstellung

Raspberry Pi OS Trixie liefert Python 3.13 und Debian-Pakete für `python3-evdev`.
Der Referenzcode für die MA2-Anbindung liegt in JavaScript (ma2apcmini,
Chataigne-Modul). Der Daemon muss HID-Ereignisse lesen und gleichzeitig eine
WebSocket-Verbindung mit Keepalive, Reconnect und Rate-Limiting betreiben.

## Entscheidungstreiber

* Zuverlässige evdev-Anbindung inklusive Geräteinfo, Hotplug und Grab
* Ein Event-Loop ohne Threading für HID und WebSocket
* Geringer Portierungsaufwand und gute Testbarkeit
* Keine Node.js-Laufzeit auf dem Pi
* Wartbarkeit durch wenige, klar getrennte Module

## Betrachtete Optionen

* Node.js mit einer Portierung der Referenzimplementierung
* Python 3.13 mit asyncio und evdev
* Python mit Threads und blockierendem evdev
* Rust oder Go mit eigener evdev-/WebSocket-Anbindung

## Entscheidung

Es wird Python 3.13 mit asyncio und `evdev` verwendet. `evdev` liefert
Geräteinformationen, Event-Typen und Hotplug-fähige Reader in hoher Qualität;
asyncio verbindet HID-Reader, WebSocket-Client, Keepalive und Rate-Limiter in
einem Event-Loop. Der Portierungsaufwand aus dem Node-Referenzcode wird
akzeptiert, weil nur Login, Frames und Hardkey-Semantik übernommen werden
müssen, nicht die MIDI-/LED-Logik.

### Konsequenzen

* Gut, weil ein Event-Loop ohne Threading und ohne Locking auskommt.
* Gut, weil `tomllib` in der Standardbibliothek liegt und keine Config-Abhängigkeit nötig ist.
* Gut, weil `python3-evdev` als Debian-Paket verfügbar ist und im venv genutzt werden kann.
* Schlecht, weil die Referenzlogik manuell portiert und neu getestet werden muss.
* Schlecht, weil Python bei sehr hohen Frame-Raten mehr Overhead hat als Node; der Rate-Limiter begrenzt das ohnehin.
* Schlecht, weil die GIL bei CPU-lastiger Beschleunigungsberechnung relevant werden könnte; die Berechnung ist klein und wird pro Flush ausgeführt.

### Bestätigung

Accepted, wenn ein Prototyp beide Geräte in einem Loop liest, Frames mit
messbarer Latenz unter 10 ms sendet und ein Reconnect ohne Blockierung des
Input-Loops gelingt.

## Vor- und Nachteile der Optionen

### Node.js-Portierung

* Gut, weil Referenzcode fast unverändert übernommen werden könnte.
* Schlecht, weil eine zusätzliche Laufzeit und npm-Abhängigkeiten auf dem Pi gepflegt werden müssten.
* Schlecht, weil die MIDI-/LED-Teile der Referenz für dieses Projekt irrelevant sind.

### Python asyncio + evdev

* Gut, weil native Debian-Unterstützung und ein einheitlicher Event-Loop.
* Gut, weil gut lesbar und leicht testbar mit pytest-asyncio.
* Schlecht, weil Portierung und eigene Fehlerbehandlung nötig sind.

### Python mit Threads

* Gut, weil blockierendes evdev direkt nutzbar wäre.
* Schlecht, weil Zustandsübergänge zwischen Input, Mapping und Sender synchronisiert werden müssten.
* Schlecht, weil Shutdown und Reconnect fehleranfälliger werden.

### Rust oder Go

* Gut, weil hohe Performance und robuste Nebenläufigkeit.
* Schlecht, weil höherer Entwicklungsaufwand und weniger direktes evdev-/MA2-Referenzwissen.
* Schlecht, weil die Zielumgebung Python ohnehin bereitstellt.

## Weitere Informationen

* Verwandt: ADR-0004, ADR-0005
