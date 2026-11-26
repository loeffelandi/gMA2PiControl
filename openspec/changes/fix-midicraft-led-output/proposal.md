# Proposal

## Why

Mit aktivem LED-Feedback liefert der MIDICRAFT ENC keine Eingaben mehr. Auf dem
Pi (2026-11-26, Journal und Kernel-Log, nur lesend) zeigt sich:

- In den Läufen mit Feedback (19:20:29–19:22:38 und 19:23:36–19:26:35) kam vom
  ENC kein einziges Event an. Mit `enabled = false` (19:29:10–19:31:30) waren
  es 508 Encoder- und 174 Button-Frames.
- Der Kernel meldet beim Schließen `rawmidi drain error` auf `midiC4D0`
  (19:22:48: 21 Bytes, 16:00:34: 477 Bytes im Ausgabepuffer). Unter Linux hat
  der ENC diese Frames also nicht abgenommen.
- Laut Betreiber senden ShowCockpit und die Lua-Plugins der MA2 ohne Probleme
  an den ENC. Das Gerät kann LED-Ausgabe damit grundsätzlich. Die Ursache
  liegt in Inhalt oder Form dessen, was `ma2pi` sendet, oder im Linux-Pfad,
  nicht im Gerät selbst.
- Danach folgt ein USB-Disconnect mit vorausgehender Stall-Welle
  (`urb status -32`), zuletzt 19:26:41 direkt nach dem Stopp des Dienstes.
- Das Stoppen des Dienstes dauert dadurch 28–56 s, weil `close()` auf einem
  `rawmidi`-Knoten bis zum Drain-Timeout wartet.
- Das Protokoll `midicraft-v2` stammt aus dem Handbuch. Task 1.2 von
  `add-midicraft-led-feedback` (LED-Noten am echten ENC messen) ist offen und
  die Ausgabe wurde trotzdem aktiviert.

Die Ausgabe ist zudem nicht geschützt: Feedback ist nur global ein- oder
ausschaltbar, der Startzustand geht als Burst von bis zu 15 Frames hinaus, und
ein Gerät, das nichts mehr abnimmt, wird weiter beschrieben.

## What Changes

- **Feedback je Gerät schaltbar**: `[profiles.<id>.led_feedback]` bekommt
  `enabled` (Default `true`). Die ausgelieferte Konfiguration setzt es für
  `midicraft-enc` auf `false`, bis die Messung am Gerät bestanden ist.
- **Getaktete LED-Ausgabe**: Frames je Gerät werden mit Mindestabstand
  (`frame_interval_ms`, Default 20 ms) gesendet. Offene Frames werden je LED
  zusammengefasst, der Startzustand wird so über mehrere Takte verteilt.
- **Stau erkennen**: Nimmt ein Gerät ausstehende Ausgabe länger als 2 s nicht ab,
  pausiert die LED-Ausgabe für dieses Gerät mit einer Warnung. Die Eingabe läuft
  weiter, die Ausgabe nimmt nach erneutem Öffnen des Geräts wieder auf.
- **Schließen ohne Drain-Wartezeit**: Beim Schließen eines MIDI-Geräts wird
  ausstehende Ausgabe verworfen, damit Stopp und Hotplug nicht auf das Gerät
  warten.
- **Messvorschrift für den ENC**: Task-Gruppe mit konkretem Ablauf und
  Abbruchkriterien. Zuerst wird der Referenzverkehr von ShowCockpit oder dem
  MA2-Lua-Plugin aufgezeichnet (Noten, Kanal, Velocity, Abstände), dann werden
  Einzel-Frames mit Pause gesendet, die Eingabe dazwischen geprüft und das
  Kernel-Log mitgelesen. Das Ergebnis entscheidet, ob und mit welchem Intervall
  der ENC Feedback bekommt und ob `midicraft-v2` angepasst werden muss.
- **Nicht enthalten**: Bank-Kanal und Bank-Offset der LED-Frames (Feedback sendet
  weiter fest auf Kanal 1), Backoff-Obergrenze beim Öffnen (derzeit bis 60 s),
  Änderungen am USB-/Hub-Aufbau. Ebenfalls nicht enthalten: die Korrektur der
  Velocity-Tabelle. Das mitgelieferte Midicraft-Plugin nutzt hell = 17 + Farbe
  und 15 Farben, `midicraft-v2` hell = 15 + Farbe und 13 Farben; welches Layout
  der ENC hat, klärt die Messung, die Korrektur wäre ein Folge-Change an
  `add-midicraft-led-feedback`. Das sind eigene Themen.
- **BREAKING**: keine. Bestehende Konfigurationen bleiben gültig; neue
  Schlüssel haben Defaults, die das bisherige Verhalten ergänzen.

## Capabilities

### New Capabilities

Keine.

### Modified Capabilities

- `executor-feedback`: Neue Requirements für Feedback je Gerät, getaktete
  Ausgabe und Ausgabestau. Die Capability ist erst mit dem Archivieren von
  `add-midicraft-led-feedback` in `openspec/specs/` vorhanden; dieser Change
  setzt voraus, dass er danach archiviert wird.
- `hid-input`: Neues Requirement für das Schließen von MIDI-Geräten.

## Impact

- **Code**: `ma2pi/feedback.py` (Ausgabe-Queue je Gerät, Zeitgeber),
  `ma2pi/midi_input.py` (`RealMidiHandle.close` mit Drop, Statusabfrage der
  Ausgabe, `MidiManager.send`/Pause je Gerät), `ma2pi/config.py` (neue Felder
  `enabled`, `frame_interval_ms`), `README.md` und `config.toml`
  (Dokumentation, ENC mit `enabled = false`).
- **Konfiguration**: `[profiles.<id>.led_feedback]` erhält `enabled` und
  `frame_interval_ms`. Beides optional.
- **Tests**: `tests/test_feedback.py` (Takt, Zusammenfassen, Pause),
  `tests/test_midi_input.py` (Drop beim Schließen, Statusabfrage,
  Fake-FD), `tests/test_config.py` (neue Felder und Grenzen).
- **Abhängigkeit**: baut auf `add-midicraft-led-feedback` auf; Task 1.2 dort
  wird durch Gruppe 1 dieses Changes ausgeführt und danach abgehakt.
- **Betrieb**: Auf dem Pi steht `[feedback] enabled = false` als Sofortmaßnahme.
  Ein Deploy darf diese Datei nicht auf `true` zurücksetzen.
