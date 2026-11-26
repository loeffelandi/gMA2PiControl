# 0019. Absolute MIDI-Werte und Executor-Ziele über den Web Remote

* Datum: 2026-11-26
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Related to [0014. ASL MK2 E4B3 als MIDI-Gerät hinter der Input-Schnittstelle](0014-asl-mk2-e4b3-als-midi-geraet-hinter-der-input-schnittstelle.md)

Related to [0016. Hardkey-Injection über gma.canbus.hardkey im Command-Line-Modus](0016-hardkey-injection-ueber-gma-canbus-hardkey-im-command-line-modus.md)

Related to [0021. Executor-Feedback über Playback-Polling und MIDI-Duplex-Ausgabe](0021-executor-feedback-ueber-playback-polling-und-midi-duplex-ausgabe.md)

Referenced by [22. Geraete-Baenke als MIDI-Kanaele und Bank-Offset](0022-geraete-baenke-als-midi-kanaele-und-bank-offset.md)

## Kontext und Problemstellung

Der MIDICRAFT ENC soll die grandMA2 über `ma2pi` steuern. Die Messung am Gerät
zeigt auf MIDI-Kanal 1 ein vollständig absolutes Layout: Fader senden
Note-On mit Velocity 0–127 (Notes 70–74), Encoder senden ebenfalls absolute
Positionen (Notes 60–64), Tasten senden Flash-Nachrichten (Notes 55–59, 65–69,
75–79, 80–84). Die bestehende MIDI-Eingabe kennt nur Tasten und relative
Encoder; absolute Werte werden verworfen. Executor-Ziele existieren in der
Konfiguration und im Transport bisher nicht.

## Entscheidungstreiber

* Absolute Fader und Encoder ohne Sonderpfad im MIDI-Leser verarbeiten
* Executor-Buttons und -Fader über den bestehenden Web Remote adressieren
* Kein MIDI, kein Telnet und keine MIDI-Remote-Tabelle der MA
* Bestehende ASL-Konfiguration und Relativ-Encoder nicht verändern
* Zweites MIDI-Gerät parallel betreiben, ohne die ASL-LED zu stören
* Feedback und PickUp in einem eigenen Schritt nachrüstbar halten

## Betrachtete Optionen

* Absolute Werte als MIDI-CC behandeln
* Absolute Werte in die bestehende relative Encoder-Semantik pressen
* Executor-Ziele über MIDI-Remotes der MA anlernen
* Executor-Ziele über `playbacks_userInput` des Web Remote senden
* Executor-Ziele über Lua-Hardkeys oder Kommandozeilen emulieren

## Entscheidung

Absolute Werte erhalten eine eigene Profilsektion `midi_values` und werden an
der Gerätegrenze auf 0.0–1.0 normalisiert. Fader und absolute Encoder teilen
sich denselben Wertepfad; Note-Off wird ignoriert.

Executor-Ziele stehen in einer eigenen Mapping-Tabelle `[mapping.playbacks]`
und werden über `playbacks_userInput` des Web Remote gesendet. Page, Executor
und Button bleiben in der Konfiguration 1-basiert und werden erst im
Frame-Builder auf 0-basiert umgerechnet. `page = "current"` wird als
`pageIndex = -1` gesendet und folgt damit der aktuell aktiven Master-Page,
ohne dass `ma2pi` die Page pollt. Buttons bleiben geordnet; Faderwerte werden
pro Ziel zusammengefasst, der letzte Wert gewinnt. Playback-Ziele haben Vorrang
vor Hardkey- und Command-Zuordnungen.

LED-Feedback, Executor-Polling und PickUp sind nicht Teil dieser Entscheidung.

### Konsequenzen

* Gut, weil das Gerät ohne Änderung seiner Firmware oder MIDI-Konfiguration
  nutzbar ist.
* Gut, weil die bestehende Tasten- und Relativ-Encoder-Semantik unverändert
  bleibt.
* Gut, weil der Web Remote bereits der etablierte Transportweg ist und keine
  neue Abhängigkeit nötig ist.
* Gut, weil Fader-Coalescing den Token-Bucket und Button-Releases schützt.
* Gut, weil `page = "current"` bei einem Seitenwechsel auf der MA keine
  Konfigurationsänderung braucht.
* Schlecht, weil ohne PickUp ein Seitenwechsel einen Wertesprung am Executor
  auslösen kann.
* Schlecht, weil die Button-ID-Semantik (`buttonId` 0–2) und `pageIndex = -1`
  erst auf echter Hardware bestätigt werden können.
* Schlecht, weil bei mehreren MIDI-Geräten die LED-Ausgabe explizit über
  `[led].device` gebunden werden muss.

### Bestätigung

Accepted, wenn der ENC am Pi Fader und absolute Encoder sendet, die Frames im
Log die erwarteten `execIndex`, `pageIndex`, `buttonId` und `faderValue`
enthalten, `pageIndex = -1` den Executor der aktiven Master-Page adressiert und
die drei Button-Nummern auf einer echten MA korrekt auslösen.

## Vor- und Nachteile der Optionen

### Absolute Werte als MIDI-CC

* Gut, weil CC ein etablierter Absolutwert-Träger ist.
* Schlecht, weil das gemessene Gerät Note-On sendet und der Parser CC heute
  verwirft; das Gerät müsste umkonfiguriert werden.

### Absolute Werte als relative Encoder

* Gut, weil der bestehende Encoder-Pfad wiederverwendet würde.
* Schlecht, weil Delta und Absolutwert unterschiedliche Semantik haben und die
  Konfiguration sowie die Validierung vermischt würden.

### Executor-Ziele über MA-MIDI-Remotes

* Gut, weil die MA die Zuordnung bereits kennt.
* Schlecht, weil die Tabelle nur per Telnet lesbar ist, keine Release-Semantik
  bietet und die MA-Konfiguration doppelt gepflegt würde.

### Executor-Ziele über `playbacks_userInput`

* Gut, weil der Web Remote bereits verbunden ist und Buttons wie Fader
  unterstützt.
* Schlecht, weil die Indizes und Button-IDs gerätespezifisch verifiziert
  werden müssen.

### Executor-Ziele über Lua oder Kommandozeile

* Gut, weil keine neuen Frames nötig wären.
* Schlecht, weil es keine stabilen Executor-Ziele adressiert und die
  Kommandozeile für Fader ungeeignet ist.

## Weitere Informationen

* Verwandt: ADR-0014 (ASL als MIDI-Gerät), ADR-0016 (Hardkey-Injection)
* Change: `add-midicraft-input`
* Messung: Notes 55–59 (Klicks), 60–64 (absolute Encoder), 65–69/75–79/80–84
  (Tasten), 70–74 (Fader), Kanal 1
