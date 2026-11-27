# Proposal

## Why

Executor-Tasten der MIDICRAFT-Controller gehen heute als
`playbacks_userInput` über den Web Remote. Diese Eingabe kennt nur die
Kommandozeile der eigenen Web-Remote-Session (Feld `cmdline`), nicht die
Haupt-Kommandozeile der Konsole, in die die Cherry per LUA-Hardkey schreibt.
Store, Assign, Edit und Co. von der Cherry greifen deshalb nicht auf ENC-Tasten.
Live gemessen am 26.11.2026:

- Store (LUA) + ENC-Taste: Executor wird ausgelöst, nicht gespeichert.
- Store (LUA) + Cherry-X-Taste (LUA): speichert.
- `playbacks_userInput` mit `cmdline: "Store"`: speichert. Den Text der
  Konsolen-Kommandozeile meldet die MA aber nicht, nur den der Session.
- Store (LUA) + MIDI-Note auf eine von Hand angelegte MIDI-Remote: speichert.

Ein Executor über eine MIDI-Remote verhält sich wie eine Konsolentaste. Damit
gehen Cherry und ENC über dieselbe Kommandozeile, und die Cherry bleibt beim
LUA-Transport (sichtbare Kommandozeile, X-, V- und Page-Tasten).

## What Changes

- Neuer Ausgabeweg: `ma2pi` sendet Executor-Eingaben als MIDI-Noten per
  RTP-MIDI an den onPC-Rechner, auf dem die MA sie über MIDI-Remotes einem
  Executor zuordnet.
- `ma2pi` vergibt je Playback-Ziel (Page, Executor, Button bzw. Fader) eine
  feste MIDI-Adresse aus einem reservierten Bereich und legt die passenden
  MIDI-Remotes per Telnet in der MA an, gleicht sie ab und meldet Abweichungen.
- Der Transport je Ziel wird wählbar: `midi` (MIDI-Remote) oder `web`
  (`playbacks_userInput`, heutiges Verhalten). Default für Buttons: `midi`;
  für Fader zunächst `web` (siehe design.md, Entscheidung offen).
- Das LED-Feedback und die Abfrage breiter Executoren bleiben beim Web Remote
  (`playbacks`-Polling); nur die Eingabe wechselt den Weg.
- Fällt der MIDI-Weg aus (keine RTP-MIDI-Sitzung, Remote-Tabelle nicht
  abgeglichen), meldet `ma2pi` das in Status und Log; es fällt nicht still auf
  den Web Remote zurück.

## Capabilities

### New Capabilities

- `midi-remote-output`: RTP-MIDI-Ausgabe zum onPC-Rechner, Adressvergabe je
  Playback-Ziel, Press/Release und Werte als MIDI-Nachrichten, Status der
  MIDI-Sitzung.
- `midi-remote-sync`: Anlegen, Abgleichen und Prüfen der MIDI-Remotes in der MA
  per Telnet für alle Playback-Ziele mit Transport `midi`.

### Modified Capabilities

- `executor-playback`: Playback-Ziele erhalten einen Transport (`midi` oder
  `web`); Tastenereignisse auf Ziele mit `midi` gehen als MIDI-Nachricht statt
  als `playbacks_userInput`.

## Impact

- Code: neuer MIDI-Ausgang zum onPC (`ma2pi/midi_remote*.py` o. ä.), Telnet-Client
  für die MA, Router-Weiche in `ma2pi/playback.py`, Konfiguration
  (`ma2pi/config.py`, `ma2pi/web/serialize.py`), Status in der Web-UI.
- Pi: RTP-MIDI-Dienst (z. B. `rtpmidid`) und ein MIDI-Port, den `ma2pi`
  beschreiben kann; Anpassung von `deploy/install.sh`.
- onPC-Rechner: RTP-MIDI-Treiber (z. B. rtpMIDI unter Windows), MIDI-Eingang
  der MA auf diesen Port, Telnet in der MA aktiviert.
- Show-File: `ma2pi` schreibt MIDI-Remotes in die Show (nur im eigenen
  Adressbereich).
- Doku: neue ADR (ersetzt für Buttons die Transportentscheidung aus ADR 0019),
  README-Abschnitt zur Einrichtung.
- Nicht Teil dieses Changes: Encoder-, Hardkey- und Screen-Pfade; LED-Ausgabe
  zu den Controllern.
