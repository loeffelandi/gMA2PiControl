# 0016. Hardkey-Injection über gma.canbus.hardkey im Command-Line-Modus

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Ersetzt [0001. Web-Remote-WebSocket als Transportweg](0001-web-remote-websocket-als-transportweg.md)

Wird auf Accepted gesetzt, wenn die Verifikation unter „Bestätigung“ bestanden ist.

## Kontext und Problemstellung

ADR 0001 hat den Web-Remote-`keyname`-Transport festgelegt. Im Betrieb zeigt sich:
Hardkeys, die als `keyname`-Frame gesendet werden, erscheinen nicht in der
Kommandozeile der onPC. Der Bediener sieht nicht, was er tippt. Das ist für die
Arbeit mit dem Cherry-Keyboard nicht akzeptabel.

Die MIDIMonster-Referenz (`backends/maweb.c`, Community-Projekt) zeigt einen zweiten
Weg. Im Modus `cmdline = console` sendet der Backend für Hardkeys keinen
`keyname`-Frame, sondern einen Command-Frame:

```
{"command":"LUA 'gma.canbus.hardkey(<code>, <true|false>, false)'","requestType":"command","session":<n>}
```

Jede Taste hat dabei einen numerischen Keycode. Ein Druck sendet `true`, das
Loslassen `false`. Der dritte Parameter (`hold`) ist in MIDIMonster immer `false`.
Press und Release sind also zwei eigene Aufrufe. Laut diesem Pfad erscheinen die
Tasten sichtbar in der Kommandozeile, weil die onPC sie wie echte Hardware-Tasten
verarbeitet.

Aus MIDIMonster übernommene Keycodes (Community-Wissen, nicht von MA dokumentiert):
MA=68, Clear=105, Please=106, Store=59, Esc=54, Goto=56, Delete=69, Copy=73, Move=85.
Die Tabelle `cmdline_keys` in `maweb.c` enthält weitere Einträge.

## Entscheidungstreiber

* Die Eingabe muss in der onPC-Kommandozeile sichtbar sein.
* Press und Release müssen getrennt gesendet werden können (Haltefunktionen).
* Modifier-Kombinationen (z. B. MA + Fix) müssen als Sequenz funktionieren.
* Die Keycodes müssen vor dem produktiven Einsatz gegen die echte onPC verifiziert werden.
* Der native `keyname`-Pfad bleibt als Fallback nutzbar.

## Betrachtete Optionen

* MIDI Remotes: nur Note-On-Trigger ohne Release-Semantik, Halten nicht möglich.
* Telnet: kann Kommandozeile, aber keine Hardkeys mit Press/Release.
* OSC: bei MA2 nicht vorhanden.
* Showcockpit: nicht geeignet für Hardkeys.
* Web-Remote `keyname` (bisheriger Stand, ADR 0001): Press/Release möglich, aber nicht in der Kommandozeile sichtbar.
* Web-Remote Command mit `LUA gma.canbus.hardkey(...)` im Command-Line-Modus: Press/Release möglich, sichtbar in der Kommandozeile, Keycodes gemäß Community-Referenz.

## Entscheidung

Der Daemon sendet Hardkeys im Command-Line-Modus über
`LUA 'gma.canbus.hardkey(<code>, <pressed>, false)'` als `command`-Frame über die
bestehende Web-Remote-WebSocket. Press und Release sind getrennte Aufrufe. Halten
wird durch den Abstand zwischen beiden Aufrufen erreicht, nicht durch den dritten
Parameter.

Der native `keyname`-Pfad bleibt über `hardkey_transport = "native"` verfügbar. Er ist
der Fallback, wenn die onPC den LUA-Aufruf ablehnt.

Der Keycode jeder Taste wird in der Konfiguration gespeichert und erst nach
Verifikation produktiv verwendet. Unverifizierte Codes werden nicht gesendet.

## Konsequenzen

* Gut, weil Tasten in der onPC-Kommandozeile sichtbar sind.
* Gut, weil Press und Release getrennt möglich sind und Halten funktioniert.
* Gut, weil MA2-exklusive Tasten erreichbar sind (z. B. Logo/MA).
* Schlecht, weil die Keycodes nicht offiziell dokumentiert sind.
* Schlecht, weil der LUA-Aufruf nach dem Hinweis aus einem früheren Chataigne-Modul-Dokument Admin-Rechte für den Web-Remote-Benutzer erfordert. Das ist vor dem Einsatz zu prüfen.
* Schlecht, weil die Konfiguration um einen Keycode-Eintrag pro Taste erweitert wird.

### Bestätigung

Der ADR wird auf Accepted gesetzt, wenn alle folgenden Punkte bestanden sind:

1. Der Web-Remote-Benutzer der onPC hat die nötigen Rechte für `gma.canbus.hardkey`, und der Aufruf wird nicht abgelehnt.
2. Jede verwendete Taste erscheint einzeln in der onPC-Kommandozeile mit dem erwarteten Keyword.
3. Press/Release einer Haltetaste (z. B. Store) wirkt wie die echte Taste.
4. Eine Modifier-Sequenz (MA + Fix) löst Desk Lock aus.
5. Die verifizierten Keycodes sind in `config.toml` persistiert.

## Vor- und Nachteile der Optionen

### MIDI Remotes

* Gut, weil einfach anzubinden.
* Schlecht, weil keine Release-Semantik, Halten nicht möglich.

### Telnet

* Gut, weil Kommandozeile direkt erreichbar.
* Schlecht, weil keine Hardkeys mit Press/Release.

### OSC

* Schlecht, weil bei MA2 nicht vorhanden.

### Showcockpit

* Schlecht, weil nicht für Hardkeys geeignet.

### Web-Remote keyname (ADR 0001)

* Gut, weil dokumentierte Web-Remote-Schnittstelle, Press/Release möglich.
* Schlecht, weil nicht in der Kommandozeile sichtbar.

### Web-Remote LUA gma.canbus.hardkey

* Gut, weil Kommandozeile sichtbar, Press/Release getrennt, MA2-exklusive Tasten erreichbar.
* Schlecht, weil Keycodes undokumentiert, Admin-Rechte nötig.

## Weitere Informationen

* [MIDIMonster maweb.c](https://github.com/cbdevnet/midimonster/blob/master/backends/maweb.c): Referenz für Frame-Format und Keycode-Tabelle.
* [ADR 0001](0001-web-remote-websocket-als-transportweg.md): ersetzt durch diesen ADR.
* [ADR 0007](0007-hardkey-transport-und-press-release-sicherheit.md): Press/Release-Sicherheit, bleibt gültig.
