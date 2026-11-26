# Tasks

## 1. Feedback, Playback & MIDI-Close

- [x] 1.1 `ma2pi/feedback.py`: `_known_current_page`-Sperre in `_belongs_to_block`
  entfernen, sodass `"current"`-Abfragen auch auf Seiten in `_fixed_pages`
  gültig bleiben. Verifikation: `tests/test_feedback.py` — Master-Page wechselt
  auf eine gleichzeitig fest überwachte Seite, `"current"`-LEDs aktualisieren
  ohne Timeout.
- [x] 1.2 `ma2pi/playback.py`: ungepaarte Key-Ups (`value < 0.5` ohne Eintrag in
  `_pressed` und ohne `engine.is_held`) verwerfen, ohne `playback_button(..., False)`
  oder `Page` zu senden. Verifikation: `tests/test_playback.py` — Loslassen nach
  `on_connection_lost()` und `cleanup()` erzeugt keinen Frame.
- [x] 1.3 `ma2pi/midi_input.py`, `ma2pi/led_output.py` & `deploy/install.sh`:
  in `close()` bis zu `30 ms` auf `output_pending == 0` warten, bevor
  `rawmidi_drop_output` ausgeführt wird; in `deploy/install.sh`
  `chmod -R u+rwX,go+rX` auf `${APP_DIR}` und `${VENV_DIR}` ergänzen.
  Verifikation: `tests/test_midi_input.py`, `tests/test_led_output.py` —
  gesundes Gerät sendet `DISABLE` ohne Drop, gestautes Gerät verwirft nach
  `<= 30 ms`.

## 2. Encoder-IDs, Geräte-API, Learn & Hilfsdienste

- [x] 2.1 `ma2pi/config.py`, `ma2pi/web/serialize.py` & `ma2pi/web/devices.py`:
  automatische `encoder_id`s in `_parse_profiles` erst im zweiten Durchlauf nach
  allen expliziten IDs vergeben; `encoder_id` in `serialize.py` nur weglassen,
  wenn `ctrl.id == f"encoder.{ctrl.encoder_id}"`; `encoder_id` in
  `devices.py` (`controls.inventory`) ausgeben und `device_summary()` auf
  Score-Sortierung + `claimed_paths` angleichen. Verifikation:
  `tests/test_config.py`, `tests/test_config_api.py`, `tests/test_web_devices.py`.
- [x] 2.2 `ma2pi/__main__.py`, `ma2pi/device_learn.py` & `ma2pi/activity.py`:
  `learn.on_start` gibt immer alle Geräte frei; `DeviceLearnManager` absorbiert
  innerhalb `SWEEP_SETTLE_SECONDS` auch identische Folge-Velocities für
  Nicht-Button-Controls und prüft `self.config.devices.get(device)` in
  `_conflict()`; `describe_midi` beschreibt Ziel-Note/Farbe zusammengesetzter
  ASL-LED-Pakete. Verifikation: `tests/test_device_learn.py`,
  `tests/test_activity.py`, `tests/test_cli.py`.
- [x] 2.3 `ma2pi/screen_helper.py`, `ma2pi/network.py`, `ma2pi/recovery.py`,
  `ma2pi/web/events.py`, `ma2pi/logging_setup.py` & `ma2pi/web/__init__.py`:
  Resolver-Task-Referenz + Koaleszierung + Cancel in `ScreenHelper.close()`;
  `remaining`-Deckel auf `confirm_timeout` in `NetworkService.resume()`;
  NetworkManager-Rollback bei `OSError` in `RecoveryService._save_locked()`;
  Timeout/Drop-Abbruch bei `ws.send_json` in `events_handler`; Escaped-Quotes in
  `_SECRET_KEYS`; PIN-Session-Widerruf in `put_config` nur bei echter Änderung
  von `(pin_enabled, pin)`. Verifikation: zugehörige Pytest-Module.

## 3. Svelte-5-Oberfläche

- [x] 3.1 `MappingPage.svelte`: `learnStore`-Updates deduplizieren und
  Start-Ergebnis übernehmen; leere `hardkey`-Modifier vor dem Speichern mit
  Fehlermeldung abweisen; frei benannte `relative-encoder` über
  `inventory[].encoder_id` in `encoderIds`, `deviceForControl` und `applyLearn`
  unterstützen; unbelegte Bank-Wert-Controls ohne falsche Note `0` anzeigen.
  Verifikation: `MappingPage.test.ts`.
- [x] 3.2 `App.svelte`, `DevicesPage.svelte`, `LearnPanel.svelte` &
  `AssignDialog.svelte`: `statusStore` bis `LearnPanel` durchreichen,
  `startedSession` bei `!next?.active` zurücksetzen, `ApiError.detail` in
  `LearnPanel` nutzen, `dialog`/`showLearn`/`learnControl` in `selectDevice()`
  zurücksetzen und `versionError` nach Erholung löschen; im `AssignDialog`
  nichtleeren `Attributnamen`, gültige `Page` und `step` erzwingen,
  `encoderScreen` beim Slot-Wechsel aktualisieren, `dialogInherited` für
  `ma_page`/Teil-Overrides/Mehrfachauswahl schärfen, frei benannte
  `relative-encoder` über `encoder_id` speichern und `mapping.modifiers` beim
  Bearbeiten/Löschen berücksichtigen. Verifikation: `App.test.ts`,
  `DevicesPage.test.ts`, `LearnPanel.test.ts`, `AssignDialog.test.ts`.
- [x] 3.3 `NetworkPage.svelte`, `StatusPage.svelte` & `status.ts`: `hadPending`
  vor `setPending(null)` sichern, damit Formularwerte nach Rollback neu geladen
  werden; `info.generation` in `status.ts` übernehmen; auf `StatusPage` nach
  `entries.at(-1)?.seq` scrollen und Replug-Aktivität über `seq > lostSeq`
  erkennen. Verifikation: `NetworkPage.test.ts`, `StatusPage.test.ts`,
  `status.test.ts`.

## 4. Abnahme

- [x] 4.1 Gesamtlauf: `.venv/bin/pytest -q`, `cd web && npm run check && npm test -- --run && npm run build && npm run check:offline`, `svelte-autofixer` ohne Befunde sowie `openspec validate fix-review-followup-findings --strict`.
