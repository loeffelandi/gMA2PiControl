# 0007. Hardkey-Transport und Press-Release-Sicherheit

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

Verifiziert 2026-11-26: Press/Release-Register, Aufräumreihenfolge und Reconnect-ohne-Replay in Tests; live MA+Fix → Desk Lock, Store halten → Store Options und reconnect ohne hängenden Modifier bestätigt (ADR 0016). Der LUA-Pfad ist der Default; `native` bleibt Fallback. Vollständiger Hardware-Smoke (inkl. Clear halten) in Task 7.3.

## Kontext und Problemstellung

Hardkeys müssen als Press **und** Release gesendet werden. Nur so funktionieren
Modifier-Kombinationen (MA halten + Fix = Desk Lock) und Haltefunktionen (Store
halten = Store Options, Clear halten = ClearAll). Die Web-Remote-Semantik
interpretiert einen Press-Wert über `0.9` als gedrückt und darunter als
losgelassen. Gleichzeitig existiert im Chataigne-Referenzmodul ein verifizierter
LUA-Wrapper (`gma.canbus.hardkey(id, pressed, hold)`), der Admin-Rechte
voraussetzt. Fällt ein Release aus, bleibt die onPC in einem hängenden
Modifier-Zustand.

## Entscheidungstreiber

* Zuverlässige Press/Release-Semantik für alle Hardkeys
* Keine hängenden Tasten nach Absturz, Reconnect oder Geräteverlust
* Klare, testbare Frame-Erzeugung an einer Stelle
* Fallback, falls die native Frame-Form von einer onPC-Version abweicht
* Keine unnötigen Admin-Rechte im Normalbetrieb

## Betrachtete Optionen

* Nur LUA-Wrapper
* Nur native Hardkey-Frames
* Konfigurierbarer Transport mit nativem Default und LUA-Fallback
* Pro Tastendruck ein Kommando statt Press/Release

## Entscheidung

Es wird ein konfigurierbarer Transport mit nativem Default und LUA-Fallback
umgesetzt:

* `hardkey_transport = "native"` erzeugt native Hardkey-Frames mit
  `value = 1.0` für Press und `value = 0.0` für Release. Die Schwelle `0.9`
  bleibt die dokumentierte Interpretationsgrenze der onPC.
* `hardkey_transport = "lua"` erzeugt `command`-Frames mit
  `LUA 'gma.canbus.hardkey(<id>, true|false, false)'`. Dieser Pfad ist im
  Chataigne-Modul verifiziert, benötigt aber Admin-Rechte des Web-Remote-Users.
* Beide Builder liegen zentral im MA2-Client; die Mapping-Engine kennt nur
  „press“ und „release“.
* Die Engine führt ein geordnetes Register aller offenen Presses. Releases
  werden nur für tatsächlich gedrückte Keys gesendet. Bei Shutdown,
  Verbindungsverlust oder Geräteverlust werden offene Presses in umgekehrter
  Press-Reihenfolge freigegeben.
* Nach einem Reconnect wird das Register geleert, ohne veraltete Frames
  nachzuspielen. Die onPC startet mit der neuen Session in einem sauberen
  Zustand; der nächste physische Tastendruck erzeugt ein vollständiges Paar.
* `hold` wird standardmäßig `false` gesendet; Modifier werden durch Halten des
  Press-Zustands abgebildet, nicht durch das `hold`-Flag.

### Konsequenzen

* Gut, weil Press/Release und Aufräumreihenfolge deterministisch sind.
* Gut, weil der native Pfad ohne Admin-Rechte auskommt, sofern die onPC ihn akzeptiert.
* Gut, weil der LUA-Fallback bei abweichender Frame-Form sofort verfügbar ist.
* Schlecht, weil zwei Transportpfade getestet werden müssen.
* Schlecht, weil der LUA-Pfad Admin-Rechte benötigt und die Kommandozeile belastet.
* Schlecht, weil ein harter Prozessabbruch ohne Gelegenheit zum Release einen hängenden Modifier hinterlassen kann; das ist nur durch Reconnect/Neustart der Session zu beheben.

### Bestätigung

Accepted, wenn auf der Ziel-onPC folgende Prüfungen bestehen: MA halten + Fix
drücken löst Desk Lock aus; Store eine Sekunde halten öffnet Store Options;
Clear halten löst ClearAll aus; ein Reconnect während gehaltener MA-Taste
hinterlässt keinen hängenden Modifier.

## Vor- und Nachteile der Optionen

### Nur LUA-Wrapper

* Gut, weil im Referenzmodul erprobt.
* Schlecht, weil Admin-Rechte nötig sind.
* Schlecht, weil jeder Hardkey als Kommando die Kommandozeile belastet.

### Nur native Frames

* Gut, weil schlank und ohne Admin-Rechte.
* Schlecht, weil die exakte Frame-Form je nach onPC-Version abweichen kann und dann kein Fallback existiert.

### Konfigurierbarer Transport

* Gut, weil native Effizienz und ein verifizierter Fallback kombiniert werden.
* Gut, weil die Entscheidung pro Installation getroffen werden kann.
* Schlecht, weil beide Pfade dokumentiert und getestet werden müssen.

### Kommando pro Tastendruck

* Gut, weil einfach.
* Schlecht, weil keine Press/Release-Semantik und damit keine Modifier-Kombis oder Haltefunktionen.

## Weitere Informationen

* Chataigne: `commandSendHardKey`
* Hardkey-IDs: Katalog aus dem Chataigne-Modul (`Fix = 41`, `Store = 59`, `MA = 68`, `Clear = 105`, `Please = 106`, …)
* Verwandt: ADR-0001, ADR-0006
