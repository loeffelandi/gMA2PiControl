# Proposal

## Why

Der MIDICRAFT ENC ist am Raspberry Pi angeschlossen, aber `ma2pi` kann seine
absoluten Fader- und Encoderwerte weder verarbeiten noch auf Executoren der
grandMA2 abbilden. Der bisherige Ansatz, die MIDI-Remote-Tabelle per Telnet zu
importieren, ist verworfen; die Messung am Gerät hat ein eigenes, vollständig
absolutes Notenlayout ergeben. Ohne diese Erweiterung bleibt der Controller
unbrauchbar.

## What Changes

- Neues MIDI-Geräteprofil `midicraft-enc` für den ENC (USB `04d8:e78c`,
  Kanal 1) mit dem gemessenen Layout: fünf Fader (Notes 70–74), fünf absolute
  Encoder (Notes 60–64) und 20 Flash-Tasten (Notes 55–59, 65–69, 75–79,
  80–84).
- Neue Profilsektion `midi_values` für absolute Note-On-Werte: Velocity 0–127
  wird auf 0.0–1.0 normalisiert und als Wertereignis geliefert; Note-Off wird
  ignoriert und erzeugt kein Tastenereignis.
- Neue Mapping-Sektion `[mapping.playbacks]`: logische Controls werden auf
  Executor-Ziele abgebildet (`page`, `executor`, `kind = "button"|"fader"`,
  optional `button = 1..3`). `page = "current"` folgt der aktuell aktiven
  Master-Page, ohne die Page zu konfigurieren.
- Neue Aktionen und Frames: Tasten senden `playbacks_userInput` mit
  Press/Release, Werte senden denselben Frame-Typ mit `faderValue`. Page,
  Executor und Button werden von 1-basiert auf 0-basiert umgerechnet;
  `"current"` wird als `pageIndex = -1` gesendet.
- Faderwerte werden pro Executor-Ziel zusammengefasst (letzter Wert gewinnt);
  Tasten-Press/Release bleiben geordnet und werden nicht zusammengefasst.
- Der Mapping-Editor im Web-UI zeigt absolute Controls an und erlaubt das
  Bearbeiten der Playback-Ziele mit Validierung vor dem Speichern.
- LED-Feedback und PickUp sind ausdrücklich nicht Teil dieses Changes; sie
  folgen in einem eigenen Change.
- Das nicht implementierte Change `add-midicraft-remote-import` wird entfernt
  (kein Code, keine Spec-Übernahme).

## Capabilities

### New Capabilities

- `executor-playback`: Abbildung von Tasten- und Wertereignissen auf
  MA2-Executoren über `playbacks_userInput`, inklusive Zielvalidierung,
  Indexumrechnung und Fader-Coalescing.

### Modified Capabilities

- `hid-input`: absolute MIDI-Werte aus Geräteprofilen, Koexistenz mehrerer
  MIDI-Geräte und Abgrenzung absoluter Controls von Tasten- und
  Relativ-Encoder-Semantik.
- `config-ui`: absolute Controls und Playback-Ziele im Mapping-Editor.

## Impact

- `ma2pi/config.py`: `MidiValueProfile`, `ProfileConfig.midi_values`,
  `PlaybackMapping`, `MappingSettings.playbacks`, `_reject_unknown` und
  Validierung (inkl. eindeutiger Notes, Page/Executor/Button-Bereiche).
- `ma2pi/midi_input.py`: `_normalise` liefert Wertereignisse, ignoriert
  Note-Off für absolute Controls und protokolliert unbekannte Werte einmal.
- `ma2pi/actions.py`, `ma2pi/frames.py`, `ma2pi/ma2_client.py`: neue Aktionen
  `PlaybackButton`/`PlaybackFader`, Frame-Builder und Dispatch, Coalescing im
  Sendepfad.
- `ma2pi/__main__.py`: Routing der Playback-Ziele vor dem MappingEngine;
  eindeutige LED-Gerätewahl, wenn mehrere MIDI-Geräte konfiguriert sind.
- `ma2pi/web/__init__.py`, `ma2pi/web/devices.py`,
  `web/src/lib/MappingPage.svelte`, `web/src/lib/api.ts`: Controls und
  Playback-Ziele in API und Oberfläche.
- `config.toml`: Beispielprofil `midicraft-enc`, Beispiel-Mapping und
  explizites `[led].device` bei mehreren MIDI-Geräten.
- Tests: `tests/test_midi_input.py`, `tests/test_config.py`,
  `tests/test_ma2_client.py`, `tests/test_config_api.py`,
  `tests/test_web_devices.py`.
- Dokumentation: README-Abschnitt zum ENC; neue ADR (Proposed) für absolute
  MIDI-Werte und Executor-Ziele über den Web Remote.
- Keine neuen Laufzeitabhängigkeiten.
- **BREAKING**: keines. Alle neuen Felder und Sektionen sind optional;
  bestehende Konfigurationen bleiben gültig. Bei aktivierter LED-Ausgabe und
  mehr als einem MIDI-Gerät muss `[led].device` explizit gesetzt sein, sonst
  bricht die Validierung mit einer klaren Meldung ab, statt LEDs am falschen
  Gerät auszugeben.
