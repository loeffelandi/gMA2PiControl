# 0021. Executor-Feedback über Playback-Polling und MIDI-Duplex-Ausgabe

* Datum: 2026-11-26
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Related to [0019. Absolute MIDI-Werte und Executor-Ziele über den Web Remote](0019-absolute-midi-werte-und-executor-ziele-ueber-den-web-remote.md)

Related to [0014. ASL MK2 E4B3 als MIDI-Gerät hinter der Input-Schnittstelle](0014-asl-mk2-e4b3-als-midi-geraet-hinter-der-input-schnittstelle.md)

## Kontext und Problemstellung

Der MIDICRAFT.ENC zeigt bisher keinen Executor-Zustand an; die 15 RGB-Tasten
bleiben dunkel. ADR-0019 hat Feedback und PickUp ausdrücklich ausgeklammert.
Das Gerät kann Farben und Helligkeit über Note-On mit kodierter Velocity
anzeigen (Manual §8), braucht dafür aber eine Rückmeldung des Executor-Zustands.

Gleichzeitig besitzt `ma2pi` keinen MIDI-Ausgabepfad für dieses Gerät: Der
ALSA-Node wird mit `O_RDONLY` geöffnet, und `led_output.py` ist fest auf das
ASL-Protokoll und ein zweites Gerät verdrahtet.

## Entscheidungstreiber

* Externe Änderungen (Konsole, Command-Fenster) müssen sichtbar werden
* Appearance-Farben der Executoren ohne Showfile-Export übernehmen
* Keine neue Abhängigkeit, kein zweiter ALSA-Open pro Gerät
* Eingabepfad und ASL-LED dürfen sich nicht ändern
* Polling darf die onPC nicht zusätzlich belasten
* Feedback muss abschaltbar sein und ohne Gerät fehlerfrei laufen

## Betrachtete Optionen

* Lokaler Schattenzustand aus selbst gesendeten `playbacks_userInput`-Frames
* Showfile-XML per `getdata` auswerten (wie der offizielle LUA-Script)
* `playbacks`-Polling des Web Remote mit Appearance-Farben aus der Antwort
* MA-MIDI-Remote-Ausgabe über die Konsole selbst (MIDI-Remote-Tabelle)
* Zweiter ALSA-Handle nur zum Schreiben (analog `led_output.py`)

## Entscheidung

`ma2pi` pollt den Executor-Zustand über `requestType = "playbacks"` des Web
Remote, gruppiert nach Page und 5er-Executorblock, mit höchstens einer offenen
Anfrage pro Page. `page = "current"` wird als `pageIndex = -1` angefragt; die
tatsächliche Page kommt als `iPage` zurück. Nur Button-Ziele mit LED-fähiger
Note werden gepollt.

Die LED-Farbe wird aus dem Hex-Feld `bC` (ersatzweise `bdC`) der Antwort auf die
nächstliegende der 13 MIDICraft-Palettenfarben abgebildet. Der LED-Zustand ist
`(an/aus, Farbe)` und wird als Note-On mit Velocity
`0 | 1 + Farbindex | 15 + Farbindex` gesendet — nur bei Änderung.

MIDI-Ausgabe läuft über denselben `RealMidiHandle`, der dafür mit `O_RDWR`
geöffnet wird; ein zweiter Handle pro Gerät entfällt. Die Fähigkeit ist im
Profil deklariert (`[profiles.<id>.led_feedback] protocol = "midicraft-v2"`,
optionale `led_notes`), nicht aus dem Gerätenamen geraten. Die globale
Aktivierung liegt in `[feedback]` und ist standardmäßig aus.

### Konsequenzen

* Gut, weil externe Änderungen an der Konsole ohne Zusatzaufwand sichtbar sind.
* Gut, weil Farben ohne Showfile-Export und ohne doppelte Konfiguration
  funktionieren.
* Gut, weil der bestehende Transportweg und die globale Rate-Limitierung
  wiederverwendet werden.
* Gut, weil ein Handle pro Gerät Hotplug und Fehlerbehandlung einfach hält.
* Schlecht, weil Feldnamen (`isRun`, `bC`, `itemGroups`) nicht dokumentiert sind
  und je MA-Version abweichen können.
* Schlecht, weil Polling Last erzeugt, die bei vielen Pages mit vielen
  Requests skaliert.
* Schlecht, weil `O_RDWR` von einzelnen Adaptern nicht unterstützt werden kann.
* Schlecht, weil Grau/Weiß der MA-Standardfarbe als „weiß" erscheint.

### Bestätigung

Accepted, wenn an einer echten onPC ein Playback-Request mit `pageIndex = -1`
antwortet, `iPage`/`isRun`/`bC` enthalten sind und die LEDs des .ENC beim
Starten, Stoppen und bei einem Seitenwechsel innerhalb von zwei Poll-Intervallen
folgen.

## Vor- und Nachteile der Optionen

### Lokaler Schattenzustand

* Gut, weil kein zusätzlicher Verkehr zur onPC entsteht.
* Schlecht, weil Änderungen außerhalb von `ma2pi` unsichtbar bleiben — genau der
  Fall, für den Feedback gedacht ist.

### Showfile-XML per `getdata`

* Gut, weil die Farbe exakt der Show entspricht.
* Schlecht, weil Export, Pfadkenntnis und Aktualisierung nach jeder Änderung
  nötig sind.

### `playbacks`-Polling mit `bC`

* Gut, weil Zustand und Farbe in einer Antwort kommen.
* Gut, weil zwei unabhängige Implementierungen das Format bestätigen.
* Schlecht, weil das Format undokumentiert ist und live verifiziert werden muss.

### MA-MIDI-Remote-Ausgabe

* Gut, weil die Konsole die Notes selbst senden könnte.
* Schlecht, weil die MIDI-Remote-Tabelle nur per Telnet lesbar ist und die
  Zuordnung doppelt gepflegt würde.

### Zweiter ALSA-Handle zum Schreiben

* Gut, weil `led_output.py` unverändert bliebe.
* Schlecht, weil Rawmidi-Substreams typischerweise nur einen offenen Handle
  erlauben und `EBUSY` das ganze Gerät blockieren kann.

## Weitere Informationen

* Verwandt: ADR-0019 (Executor-Ziele über den Web Remote), ADR-0014 (ASL als
  MIDI-Gerät), ADR-0005 (Rate-Limiting).
* Protokollquellen: MIDICRAFT-Benutzerhandbuch §8 (Velocity-Tabelle),
  midimonster `backends/maweb.c` und locimation „MA2 Remote" (Playback-Antwort).
