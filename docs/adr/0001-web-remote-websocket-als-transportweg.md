# 0001. Web-Remote-WebSocket als Transportweg

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Superseded by [0016. Hardkey-Injection über gma.canbus.hardkey im Command-Line-Modus](0016-hardkey-injection-ueber-gma-canbus-hardkey-im-command-line-modus.md)

## Kontext und Problemstellung

Der Daemon muss Tasten der grandMA2 onPC mit echter Press-/Release-Semantik
auslösen. Modifier-Kombinationen wie MA+Fix (Desk Lock) und Haltefunktionen wie
Store (Store Options) oder Clear (ClearAll) funktionieren nur, wenn die onPC ein
Key-Down und ein separates Key-Up erhält. Gleichzeitig soll kein zusätzlicher
Parameter-Unlock und keine zusätzliche Software im Wirkpfad entstehen.

## Entscheidungstreiber

* Press/Release-Semantik für Hardkeys und Modifier
* Zugriff auf die vollständige Hardkey-Tabelle, nicht nur auf Executor-Buttons
* Dokumentierter, lokal nutzbarer Transport ohne Cloud-Abhängigkeit
* Geringe Latenz und stabiles Verhalten bei Verbindungsabbrüchen
* Wartbarkeit und vorhandene Referenzimplementierungen

## Betrachtete Optionen

* MIDI Remotes
* OSC
* Telnet
* Showcockpit
* grandMA2 Web-Remote-WebSocket-API (`ws://<ip>:80/?ma=1`)

## Entscheidung

Es wird die Web-Remote-WebSocket-API verwendet. Sie liefert JSON-Frames über eine
authentifizierte Session, kennt Hardkey-Press und -Release und ist durch die
AsyncAPI-Dokumentation von deltaeight sowie die Referenzimplementierungen
ma2apcmini und grandMA2-Chataigne-Modul belegt. MIDI Remotes, OSC, Telnet und
Showcockpit entfallen als primärer Pfad.

### Konsequenzen

* Gut, weil Hardkeys und Modifier-Kombinationen native Press/Release-Semantik erhalten.
* Gut, weil keine zusätzliche Software und keine Cloud im Wirkpfad liegt.
* Schlecht, weil Login, Session, Keepalive und Reconnect selbst implementiert werden müssen.
* Schlecht, weil Teile des Protokolls (Wheel-Frames) nicht dokumentiert sind.
* Schlecht, weil zu hohe Frame-Raten die onPC blockieren können; Gegenmaßnahme ist ADR-0005.

### Bestätigung

Die Entscheidung gilt als verifiziert, wenn auf der Ziel-onPC ein Login
erfolgreich ist, ein Hardkey-Press/Release-Paar nachweislich ankommt und
MA halten + Fix drücken Desk Lock auslöst. Erst dann wird der Status auf Accepted gesetzt.

## Vor- und Nachteile der Optionen

### MIDI Remotes

* Gut, weil stabil und einfach zu implementieren.
* Schlecht, weil MIDI keinen Release für Hardkeys kennt; Modifier-Kombis und Haltefunktionen sind nicht abbildbar.
* Schlecht, weil nur ein kleiner Teil der Hardkeys adressierbar ist.

### OSC

* Gut, weil flexibel und netzwerkfähig.
* Schlecht, weil die onPC-OSC-Schnittstelle keine Hardkey-Press/Release-Semantik bereitstellt.
* Schlecht, weil zusätzliche Mapping-Schicht und Fehlerquellen entstehen.

### Telnet

* Gut, weil die Kommandozeile direkt erreichbar ist.
* Schlecht, weil keine Hardkeys, keine Modifier und keine Press/Release-Semantik möglich sind.
* Schlecht, weil die Verbindung fragil ist und keine Session-/Reconnect-Logik bietet.

### Showcockpit

* Gut, weil fertige Oberfläche und Geräteunterstützung.
* Schlecht, weil eine weitere Abhängigkeit im Wirkpfad liegt und die Hardkey-Semantik nicht garantiert ist.
* Schlecht, weil der Daemon dann nicht eigenständig und headless betreibbar wäre.

### Web-Remote-WebSocket

* Gut, weil Press/Release, Hardkeys, Session und Keepalive vorhanden sind.
* Gut, weil Referenzcode für Login und Frames existiert.
* Schlecht, weil Wheel-Frames undokumentiert sind (siehe ADR-0002).
* Schlecht, weil die onPC bei Frame-Fluten empfindlich reagiert (siehe ADR-0005).

## Weitere Informationen

* https://github.com/deltaeight/ma2-websocket-api
* https://github.com/ArtGateOne/ma2apcmini
* https://github.com/joelengelhardt/grandMA2-dot2-Chataigne-Module
* Verwandt: ADR-0002, ADR-0005, ADR-0007
