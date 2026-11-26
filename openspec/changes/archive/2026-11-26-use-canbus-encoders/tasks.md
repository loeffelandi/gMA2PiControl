# Tasks

## 1. Frame-Bausteine
- [x] 1.1 `frames.lua_encoder_frame(index, steps, session)` ergänzt einen Command-Frame `LUA 'gma.canbus.encoder(<index>,<steps>,nil)'`; Test vergleicht das Frame exakt (positiv/negativ, Index 0 und 4).

## 2. Konfiguration
- [x] 2.1 `mapping.screen_encoders` akzeptiert nur Ganzzahlen 5–10 (Zahl oder numerischer String), intern `int`; Bereichsverletzung und nicht-numerische Werte lassen die Validierung scheitern. Tests in `tests/test_config.py`.
- [x] 2.2 Default-Config `screen_encoders = {1:8, 2:7, 3:6, 4:5}`; `encoder_fine` aus `[mapping.keys]` entfernt und als unbekannter Schlüssel abgelehnt. Tests für Default-Reihenfolge und Ablehnung.

## 3. Aktionen & Mapping
- [x] 3.1 `ToggleFine`/`toggle_fine`/`encoder_fine` durch `EncoderPress`/`encoder_press = <slot>` ersetzt; Press und Release nutzen denselben Index (auch bei Moduswechsel dazwischen). Stubs anpassen.
- [x] 3.3 Taste 2 (`asl_button_2`, lokaler Modifier `cycle`) gehalten: Klick schaltet pro Slot Normal → Fine → Ultra; Tests in `tests/test_mapping.py`.
- [x] 3.2 MA-Hold-/Screen-Modus-Logik und Flush-Trennung bleiben unverändert; bestehende Mapping-Tests laufen weiter (ggf. ohne Auflösungs-Assertions).

## 4. MA2-Client
- [x] 4.1 Slot-Dispatch sendet canbus-Frames: Attribut-Modus Index `slot-1`, Screen-Modus Index `screen_encoders[slot]-1`; fehlende Screen-Nummer → Warnung, kein Frame. Feste Attribut-Encoder bleiben nativ. Tests in `tests/test_ma2_client.py`.
- [x] 4.2 Ganzzahlige Schritte mit Rest-Vortrag pro Slot; Vorzeichen bleibt; Flush ohne ganzen Schritt sendet nichts. Tests für Rest-Vortrag und Vorzeichen.
- [x] 4.3 `EncoderPage`, `_page*`, `_page_poll_loop`, `_schedule_page_refresh`, `_refresh_page`, `_log_page_if_changed`, `ToggleFine`-Dispatch und `_fine` entfernt; `ma2pi/encoder_page.py` gelöscht. `presetTypes` wird nicht mehr gesendet.

## 4b. LED
- [x] 4b.1 `[led]`-Einstellungen `nipple_note`, `nipple_idle_color/brightness`, `nipple_pressed_color/brightness` (Default 11 / 121,25 / 116,127); `LedOutput` setzt Idle beim Öffnen und wechselt bei NIPPLE-Press/Release; Tests in `tests/test_led_output.py`.

## 5. Tests & Mocks aufräumen
- [x] 5.1 `tests/test_encoder_page.py` entfernt; `tests/mock_ma2.py`, `test_integration.py`, `test_dry_run.py` und alle `toggle_fine`-Stubs angepasst; volle Suite grün.

## 6. Web-UI
- [x] 6.1 `MappingPage.svelte`: Screen-Encoder-Dropdown 5–10 + `— keiner —`, Default-Reihenfolge 1→5…4→8, Hilfetext; Werte als Zahlen. `MappingPage.test.ts` aktualisiert; `npm run check`/Build grün.

## 7. Doku & Default-Config
- [x] 7.1 `config.toml` (Screen-Nummern, keine `encoder_fine`), README-Abschnitte zu Encodern/Screen/Auflösung aktualisiert.

## 8. Qualität
- [x] 8.1 `pytest` gesamt grün, `svelte-check` 0 Fehler, `npm run build` erfolgreich; `openspec validate --strict use-canbus-encoders` grün.

## 9. Deployment & Abnahme
- [x] 9.1 Code/UI auf den Pi installieren, aktive Config per API hot-applizieren (Screen-Nummern, `encoder_fine` entfernen), Dienst prüfen.
- [x] 9.2 Hardware-Abnahme: Attribut-Encoder folgen der onPC; MA-Hold + Encoder → Screen-Encoder 5–8; `asl_bank` → Screen-Modus; kein `presetTypes`-Polling mehr im Log.