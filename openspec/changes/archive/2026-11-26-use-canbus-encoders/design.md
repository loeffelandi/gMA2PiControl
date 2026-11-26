# Design

## Kontext / Evidenz

Ein transparenter WebSocket-Proxy (Mac → onPC) hat den Datenverkehr von
ShowCockpit mitgeschnitten, das die Screen-Encoder nachweislich steuert.
Belegte Frames:

- Screen-Encoder: `LUA 'gma.canbus.encoder(4..7, ±1, nil)'` (Wheel 5–8).
- Normale Encoder: `LUA 'gma.canbus.encoder(0..3, ±1, nil)'` (Wheel 1–4).
- Encoder-Druck: `LUA 'gma.canbus.encoder(n, 0, true)'` / `(n, 0, false)`.
- ShowCockpit sendet **nie** `requestType:"encoder"`, nie `resolution`, nie
  `keyname`. `presetTypes`/`playbacks`/`getdata` sind reines UI-Feedback.

Daraus folgt: Index = Encoder-Nummer − 1; Schritte sind ganzzahlig (±1 pro
Detent); die onPC routet die Hardware-Encoder 0–3 selbst auf das aktuelle
Feature und wendet ihre eigene Encoder-Auflösung an.

## Entscheidungen

### Canbus statt nativem `encoder`-Request für Slots
`frames.lua_encoder_frame(index, steps, session)` baut
`command_frame(f"LUA 'gma.canbus.encoder({index},{steps},nil)'")`. Der
Slot-Dispatch in `Ma2Client._dispatch` berechnet den Index:
- Attribut-Modus: `slot - 1`.
- Screen-Modus (global oder MA-Hold): `int(screen_encoders[slot]) - 1`; fehlt der
  Eintrag → Warnung, kein Frame.

Feste Attribut-Encoder (`EncoderAttribute`) bleiben beim nativen
`encoder_attribute_frame`, da sie einen konkreten Attributnamen adressieren.

### Ganzzahlige Schritte + Rest-Vortrag
Die Engine akkumuliert weiterhin Float-Deltas (Beschleunigung). Der Client
führt pro Slot einen Rest `_screen_rest`/`_slot_rest`. Beim Flush:
`total = rest + delta; steps = int(total) trunciert Richtung 0; rest = total - steps`.
`steps == 0` → kein Frame, Rest bleibt. So geht bei langsamer Drehung kein
Detent verloren. Das Vorzeichen bleibt erhalten.

### Entfernung des Seiten-Modells
`EncoderPage`, `_page`, `_page_poll_loop`, `_schedule_page_refresh`,
`_refresh_page`, `_log_page_if_changed`, `_page_task`, `_page_signature` und
`ma2pi/encoder_page.py` entfallen. `preset_types_frame` wird nicht mehr vom
Daemon gesendet. Die Status-UI nutzt das Seiten-Modell nicht (geprüft:
`_status_snapshot` enthält keine Encoder-Labels).

### Klick und lokale Auflösung
`ToggleFine`, `toggle_fine`, `_fine`, `encoder_fine` und der Auflösungs-Frame
entfallen (der native Auflösungs-Frame braucht Attributnamen, die es ohne
Seitenmodell nicht mehr gibt). `asl_click_1..4` mappen auf
`encoder_press = <slot>` und senden `(index,0,true/false)`; das Ziel (Attribut
oder Screen/MA) wird beim Press festgehalten und für den Release wiederverwendet.
Ist der lokale Modifier `encoder_resolution.modifiers.cycle` (`asl_button_2`)
gehalten, schaltet der Klick stattdessen die Auflösung des Slots in der
Mapping-Engine (`_slot_resolution`) und sendet nichts. Die Faktoren kommen aus
`encoder_resolution.attribute`; Reste trägt der Client vor.

### Config-Validierung
`mapping.screen_encoders`: Werte müssen ganzzahlig 5–10 sein (als Zahl oder
numerischer String akzeptiert, intern als `int` gespeichert). Schlüssel
1–4 (Slots). Default `{1:5, 2:6, 3:7, 4:8}`. `encoder_fine` wird als
unbekannter Key-Schlüssel abgelehnt.

### UI
`MappingPage.svelte`: Screen-Encoder-Dropdown `5…10` plus `— keiner —`;
Default-Reihenfolge 1→5 … 4→8. Hilfetext anpassen. Werte werden als Zahlen
geschrieben/gelesen.

## Risiken / Gegenmaßnahmen

- **Canbus-Attribut-Encoder folgen nicht wie erwartet:** durch ShowCockpit-
  Capture belegt; Hardware-Abnahme nach Deploy.
- **Auflösung fühlt sich anders an:** onPC-Auflösung statt Daemon-Zyklus; vom
  Nutzer gewählt.
- **Bestehende Pi-Config enthält `encoder_fine`/alte Screen-Namen:** per API
  hot-applizieren (entfernen bzw. auf Nummern umstellen), sonst Validierungsfehler.