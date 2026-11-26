# 0002. Wheel- und Encoder-Strategie

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

Verifiziert 2026-11-26: native Attribut-Encoder-Frames (`requestType: "encoder"`) wirken live; die Encoder folgen dem onPC-Fenster (ADR 0015). Ein CMD-Wrapper/Fallback ist nicht nötig; `wheel_protocol.py` bleibt nur dokumentierter, ungenutzter Baustein.

Ergänzt durch [14. ASL MK2 E4B3 als MIDI-Geraet hinter der Input-Schnittstelle](0014-asl-mk2-e4b3-als-midi-geraet-hinter-der-input-schnittstelle.md)

Ergänzt durch [15. Attribut-Encoder folgen der onPC statt fester Wheel-Ziele](0015-attribut-encoder-folgen-der-onpc-statt-fester-wheel-ziele.md)

## Kontext und Problemstellung

Die Web-Remote-API dokumentiert Login, Session, `dataRequest` und
`closeConnection`. Die Frames, die ein virtuelles Wheel im Web-Remote erzeugt,
sind nicht dokumentiert. Für Attribut-Encoder existiert im
Chataigne-Referenzmodul ein nativer `encoder`-Request; für Wheel-Ziele nutzt
dasselbe Modul einen CMD-Wrapper (`Feature $feature.<n> At +<delta>`), der die
Kommandozeile für jeden Schritt belastet. Der Daemon braucht eine belastbare
Strategie, ohne das Protokoll zu raten.

## Entscheidungstreiber

* Korrekte Wheel- und Attribut-Semantik ohne Commandline-Spam
* Kein Raten undokumentierter Frames
* Umschaltbarkeit ohne Änderung der Mapping-Engine
* Testbarkeit ohne Hardware
* Schutz der onPC vor zu hohen Raten

## Betrachtete Optionen

* Ausschließlich CMD-Wrapper
* Ausschließlich natives Protokoll (ohne Capture)
* Hybrid: CMD-Wrapper als Default, natives Protokoll nach Capture
* Chataigne als vorgeschalteter Proxy

## Entscheidung

Es wird ein Hybrid mit Capture-Vorbehalt umgesetzt:

1. Default ist der CMD-Wrapper. Für Attribut-Ziele wird pro Flush ein relativer
   Befehl `Attribute "<Name>" At +<delta> Please` erzeugt; für Wheel-Ziele ein
   äquivalenter relativer Befehl. Der Wrapper ist throttled und delta-akkumuliert.
2. Der native Attribut-Request (`requestType: "encoder"`, `name`, `value`) ist
   aus dem Chataigne-Modul bekannt und kann per Config aktiviert werden.
3. Native Wheel-Frames werden erst nach einem manuellen DevTools-Capture
   implementiert. `wheel_protocol.py` zentralisiert Konstanten und Builder; ohne
   verifiziertes Format bricht der native Wheel-Modus mit einem klaren Hinweis ab.
4. Der Capture-Workflow ist im README dokumentiert und wird manuell ausgeführt;
   es gibt keinen Autodrive.

Der Status bleibt Proposed, bis entweder ein Capture ein stabiles Wheel-Format
belegt oder der CMD-Wrapper als endgültige Lösung dokumentiert wird.

### Konsequenzen

* Gut, weil der Daemon sofort ohne Capture funktioniert.
* Gut, weil native Attribut-Encoder ohne Commandline-Spam möglich sind.
* Gut, weil die Mapping-Engine den Transport nicht kennt.
* Schlecht, weil der CMD-Wrapper die MA2-Kommandozeile sichtbar verändert und bei schnellem Drehen unruhig wirkt.
* Schlecht, weil ein Capture manuellen Aufwand und eine laufende onPC erfordert.
* Schlecht, weil zwei Transportpfade getestet und dokumentiert werden müssen.

### Bestätigung

Accepted, wenn ein Capture vorliegt, das Wheel-Frame-Format als Fixture
reproduzierbar ist und der native Modus dieselbe strukturelle Frame-Form erzeugt.
Falls das Capture kein stabiles Format liefert, wird der CMD-Wrapper als finale
Entscheidung dokumentiert und diese ADR entsprechend aktualisiert.

## Vor- und Nachteile der Optionen

### Ausschließlich CMD-Wrapper

* Gut, weil sofort einsetzbar und ohne Capture verifizierbar.
* Schlecht, weil jeder Schritt die Kommandozeile belastet und die onPC unter Last gerät.
* Schlecht, weil die Semantik relativ und nicht absolut ist; kein Read-back.

### Ausschließlich natives Protokoll

* Gut, weil sauber und performant.
* Schlecht, weil das Wheel-Format unbekannt ist und Raten zu Fehlfunktionen führt.
* Schlecht, weil ohne Capture keine belastbaren Tests möglich sind.

### Hybrid mit Capture

* Gut, weil sofort lauffähig und später optimierbar.
* Gut, weil klare Abbruchkriterien und ein dokumentierter Fallback existieren.
* Schlecht, weil zwei Pfade und ein manueller Capture-Schritt zu pflegen sind.

### Chataigne als Proxy

* Gut, weil erprobte Implementierung.
* Schlecht, weil zusätzliche Software, GUI und Abhängigkeit im Wirkpfad liegen.
* Schlecht, weil der Daemon nicht eigenständig headless betreibbar wäre.

## Weitere Informationen

* Chataigne: `commandSendEncoderByWheel`, `commandSendEncoderByAttribute`
* Capture-Workflow: README-Abschnitt „Wheel-Protokoll-Capture“
* Verwandt: ADR-0001, ADR-0005
