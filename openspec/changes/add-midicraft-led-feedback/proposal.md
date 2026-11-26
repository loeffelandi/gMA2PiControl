# Proposal

## Why

Der MIDICRAFT.ENC ist bisher reine Eingabe: Die 15 RGB-Tasten bleiben dunkel,
obwohl das Gerät den Executor-Zustand über Noten mit kodierter Velocity anzeigen
kann. Wer die Hardware bedient, sieht dadurch nicht, welcher Executor läuft, und
muss auf den Bildschirm der onPC schauen. Genau dieses Feedback war in allen
bisherigen Changes bewusst ausgeklammert.

## What Changes

- Neue Funktion **Executor-Feedback**: `ma2pi` pollt periodisch den Zustand der
  in `[mapping.playbacks]` adressierten Executoren über den Web Remote
  (`requestType: "playbacks"`) und leitet daraus LED-Zustände für
  MIDI-Controller ab, deren Profil Feedback unterstützt.
- Neuer **MIDI-Ausgabepfad**: Die ALSA-Nodes der MIDI-Geräte werden duplex
  (`O_RDWR`) geöffnet und um eine Schreibfunktion mit
  Änderungs-Erkennung und Koaleszierung erweitert. Der bestehende ASL-LED-Pfad
  (`led_output.py`) bleibt unverändert.
- Neue Konfiguration:
  - `[feedback]` global: `enabled`, `interval_ms`, Fallback-Farbe,
    Aus-Zustand.
  - `[profiles.<id>.led_feedback]` je Gerät: Protokoll `midicraft-v2`, Liste der
    Noten mit LED sowie die Zuordnung von Farbe/Modus zu Velocity.
- **Farben aus der Web Remote**: Die Playback-Antwort enthält je Executor die
  Appearance-Hintergrundfarben als Hex (`bC`/`bdC`). Daraus wird die nächstliegende
  der 13 MIDICraft-Palettenfarben gewählt. Damit entfällt der Showfile-Export,
  den der offizielle gMA2-LUA-Script noch braucht.
- **Ausgelieferte Belegung** in `config.toml`: Fader 1–5 → Executoren 1–5
  (`fader`), Reihe über den Fadern → Button 2, Reihe darunter → Button 3,
  Encoder 1–5 → Executoren 6–10 (`fader`), Encoder-Klick → Button 1,
  untere Reihe → Floating-Executoren 101–105 (Button 1).
- **Nicht enthalten**: Fader-Pickup, Fader-LEDs (Hardware hat keine), MA3,
  OSC, Farbverläufe oder Blinkmuster jenseits von hell/dunkel.
- **BREAKING**: keine.

## Capabilities

### New Capabilities

- `executor-feedback`: Pollt den Executor-Zustand über den Web Remote und gibt
  daraus abgeleitete LED-Zustände an MIDI-Controller aus, inklusive
  Konfiguration, Farbabbildung und Verhalten bei Verbindungsverlust.

### Modified Capabilities

- `executor-playback`: Das Requirement „Kein Executor-Feedback in diesem
  Change" wird entfernt; Feedback ist ab jetzt Teil des Verhaltens.

## Impact

- **Code**: `ma2pi/midi_input.py` (Duplex-Handle, Schreibfunktion),
  `ma2pi/frames.py` (Playbacks-Request), `ma2pi/ma2_client.py`
  (Antwort-Routing), neu `ma2pi/feedback.py` (Polling, Zustand, LED-Frames),
  `ma2pi/config.py`, `ma2pi/__main__.py`.
- **Konfiguration**: `config.toml` (`[feedback]`), README,
  `--check-config`-Validierung, ggf. Web-Statusanzeige.
- **Tests**: `tests/test_feedback.py`, Erweiterungen an
  `tests/test_midi_input.py`, `tests/test_ma2_client.py`, `tests/test_config.py`,
  `tests/mock_ma2.py`.
- **Aktueller Bestand**: Nur `mc_click_1..3`, `mc_fader_1` und `mc_encoder_1`
  haben Playback-Ziele. Davon hat keine Note eine LED — die Encoder-Klick-Noten
  55–59 sind am Gerät ohne LED bestätigt. Die 15 RGB-Tasten (65–69, 75–79,
  80–84) sind noch keinem Executor zugeordnet; das ändert dieser Change mit der
  oben genannten Belegung.
