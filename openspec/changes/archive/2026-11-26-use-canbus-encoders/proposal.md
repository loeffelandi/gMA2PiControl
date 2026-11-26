# Proposal

## Why

Die Screen-Encoder funktionieren nicht: Der Daemon sendet im Screen-Modus
`{"requestType":"encoder","name":"8",...}`. Der Web-Remote-`encoder`-Request
kennt aber ausschließlich Attributnamen (`DIM`, `PAN`, …) aus dem
`presetTypes`-Modell — Zahlen werden von der onPC still ignoriert. Ein
Live-Capture von ShowCockpit (das die Screen-Encoder nachweislich steuert)
zeigt: Sowohl Screen- als auch normale Encoder laufen über
`LUA 'gma.canbus.encoder(<Index>, <Schritte>, nil)'`-Command-Frames, wobei
Index = Encoder-Nummer − 1. ShowCockpit sendet dafür nie `requestType:"encoder"`
und nie `resolution`; das `presetTypes`-Polling ist reines UI-Feedback.

## What Changes

- **BREAKING** Slot-Encoder (Attribut- und Screen-Modus) werden über
  `gma.canbus.encoder`-Command-Frames statt über den nativen
  `encoder`-Request gesteuert. Index = Ziel-Nummer − 1; normale Encoder
  1–4 → Index 0–3, Screen-Encoder 5–10 → Index 4–9.
- **BREAKING** `mapping.screen_encoders` enthält jetzt Screen-Encoder-Nummern
  5–10 statt frei wählbarer Namen. Standardbelegung (umgekehrt, entspricht der Verdrahtung):
  Slot 1 → 8, Slot 2 → 7, Slot 3 → 6, Slot 4 → 5.
- **BREAKING** `encoder_fine`/`ToggleFine` und der Auflösungs-Frame für Slots
  entfallen. Der Encoder-Klick sendet den echten Encoder-Druck der onPC
  (`encoder_press`). Halten von ASL-Taste 2 + Klick schaltet die Auflösung des
  Slots lokal durch (Normal → Fine → Ultra) und skaliert die Deltas.
- Die rechte ASL-Taste (NIPPLE) leuchtet leicht orange (121/25) und beim Drücken
  heller (116/127).
- Das `presetTypes`-Polling (`EncoderPage`, `_page_poll_loop`,
  `_schedule_page_refresh`) entfällt, da die onPC die Hardware-Encoder 0–3
  selbst auf das aktuelle Feature routet. Feste Attribut-Encoder
  (`attribute`) behalten den nativen `encoder`-Request.
- Ganzzahlige Schritte: akkumulierte Float-Deltas werden pro Slot ganzzahlig
  gesendet; der Rest wird vorgetragen, damit langsame Drehungen nicht verloren gehen.
- UI: Screen-Encoder-Dropdown bietet 5–10 (statt 5–8) in natürlicher Reihenfolge.

## Capabilities

### New Capabilities

(keine)

### Modified Capabilities

- `encoder-control`: Encoder-Transport wird canbus; Screen-Ziele sind Nummern
  5–10; Fine/Ultra pro Klick und das Seiten-Polling entfallen; Standard 1→8 … 4→5;
  Encoder-Klick per canbus; lokale Auflösung per Taste 2; NIPPLE-LED.
- `config-ui`: Screen-Encoder-Auswahl pro physischem Encoder ist eine Nummer
  5–10 (Dropdown 5–10) statt eines freien Namens.

## Impact

- `ma2pi/frames.py`: neue canbus-Encoder-Frame-Builder.
- `ma2pi/ma2_client.py`: Slot-Dispatch über canbus, Rest-Vortrag, Entfernung von
  `EncoderPage`/Polling/`ToggleFine`/`_fine`.
- `ma2pi/actions.py`: `ToggleFine` entfällt.
- `ma2pi/mapping.py`: `encoder_fine`-Zweig entfällt; MA-Hold/Screen-Logik bleibt.
- `ma2pi/config.py`: `screen_encoders` validiert Nummern 5–10; `encoder_fine` entfällt.
- `ma2pi/encoder_page.py`: entfällt (nur noch von Tests referenziert → entfernen).
- `web/src/lib/MappingPage.svelte`: Dropdown 5–10, Default-Reihenfolge.
- `config.toml`, Tests, README; aktive Pi-Konfiguration per API nachziehen.