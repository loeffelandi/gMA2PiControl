# Proposal

## Why

Die mittlere ASL-Taste (`asl_button_2`) schaltet gehalten die Encoder-Klick-Funktion
auf Auflösungswechsel um, hat aber keine Rückmeldung. Wie die NIPPLE-Taste soll sie
einen Ruhe- und einen Gedrückt-Zustand per LED zeigen.

## What Changes

- Neue `[led]`-Einstellungen `fine_note`, `fine_color`, `fine_idle_brightness`,
  `fine_pressed_brightness` (Default 10 / 123 / 25 / 127).
- Die LED der mittleren Taste leuchtet im Ruhezustand gedimmt und solange der
  Modifier gehalten wird hell.

## Capabilities

### New Capabilities

(keine)

### Modified Capabilities

- `encoder-control`: LED-Rückmeldung für die mittlere ASL-Taste.

## Impact

- `ma2pi/led_output.py`, `ma2pi/config.py`, `ma2pi/mapping.py` (Modifier-Hook),
  `ma2pi/__main__.py`, `config.toml`, README, Tests.
