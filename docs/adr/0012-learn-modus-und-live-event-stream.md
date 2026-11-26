# 0012. Learn-Modus und Live-Event-Stream

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

## Kontext und Problemstellung

Das Mapping verweist auf logische Control-Namen, die aus evdev-Rohcodes
entstehen. Ohne Learn-Modus müsste der Benutzer die Codes mit `evtest` oder
`--dump-input` ermitteln und von Hand in TOML eintragen. Außerdem soll die
Oberfläche den Verbindungszustand und die Frame-Aktivität live anzeigen. Beim
Lernen darf kein Event an die onPC gehen, sonst löst das Drücken einer Taste
unbeabsichtigt eine MA2-Aktion aus.

## Entscheidungstreiber

* Einfache Zuordnung ohne externe Tools
* Keine unbeabsichtigten MA2-Frames während des Lernens
* Klare Zeitgrenzen und Abbruchmöglichkeit
* Ein gemeinsamer Live-Kanal für Status, Learn und Log
* Keine zusätzliche Infrastruktur

## Betrachtete Optionen

* Manuelle Code-Eingabe mit `evtest`
* Externer Capture-Prozess neben dem Daemon
* In-Process-Learn-Modus mit WebSocket-Events
* Polling der API für Status und Events

## Entscheidung

Es wird ein In-Process-Learn-Modus mit WebSocket-Event-Stream umgesetzt:

* Der `LearnManager` erlaubt höchstens eine Sitzung gleichzeitig, mit
  konfigurierbarem Timeout (Default 15 s).
* Während des Lernens werden **alle** Mapping-Aktionen unterdrückt. Das
  verhindert halbe Chords und unbeabsichtigte MA2-Frames.
* Taste: Der nächste Key-Down wird mit Rohcode und logischem Namen erfasst; das
  Key-Up wird geschluckt.
* Encoder: Über ein Fenster von 2 s werden Achse, Richtung und Detents gesammelt
  und als Vorschlag angezeigt.
* Status, Learn-Events und Logzeilen laufen über `/api/events` (WebSocket).
  Die UI baut die Verbindung nach Abbruch automatisch neu auf.
* Erfolg, Timeout oder Abbruch stellen den normalen Betrieb ohne dauerhafte
  Änderung wieder her. Gespeichert wird erst durch einen expliziten Apply.

### Konsequenzen

* Gut, weil Tasten und Encoder ohne externe Tools zugeordnet werden können.
* Gut, weil während des Lernens garantiert keine MA2-Frames entstehen.
* Gut, weil ein Kanal Status, Learn und Log bündelt.
* Schlecht, weil während des Lernens alle Eingaben gesperrt sind; das UI muss das deutlich anzeigen.
* Schlecht, weil ein Timeout oder eine hängende UI-Sitzung den Modus beenden muss.
* Schlecht, weil der WebSocket-Client Reconnect-Logik braucht.

### Bestätigung

Accepted, wenn eine Taste und ein Encoder im UI erfasst werden, dabei null
MA2-Frames gesendet werden, ein Timeout den Normalbetrieb wiederherstellt und
die UI nach einer Unterbrechung den Event-Stream selbstständig neu aufbaut.

## Vor- und Nachteile der Optionen

### Manuelle Code-Eingabe

* Gut, weil kein zusätzlicher Code nötig ist.
* Schlecht, weil `evtest` und TOML-Wissen erforderlich sind und Fehler leicht passieren.

### Externer Capture-Prozess

* Gut, weil der Daemon unverändert bliebe.
* Schlecht, weil zwei Prozesse um das Gerät konkurrieren und der Zustand nicht synchron ist.

### In-Process-Learn

* Gut, weil Gerätezugriff, Mapping und UI denselben Zustand teilen.
* Gut, weil Aktionen während des Lernens sicher unterdrückt werden können.
* Schlecht, weil der Mapping-Pfad einen zusätzlichen Modus und Tests benötigt.

### Polling

* Gut, weil einfacher als WebSocket.
* Schlecht, weil Status und Learn-Events verzögert und ineffizient ankommen.

## Weitere Informationen

* Verwandt: ADR-0008, ADR-0010, ADR-0011
