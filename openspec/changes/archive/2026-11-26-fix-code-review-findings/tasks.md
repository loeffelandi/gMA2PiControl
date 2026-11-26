# Tasks

## 0. OpenSpec-Basis bereinigen

- [x] 0.1 Fertig umgesetzte Changes `add-sustain-branding` und
  `add-device-activity-monitor` archivieren (`openspec archive`), damit die
  Haupt-Specs den produktiven Stand widerspiegeln. (`harden-runtime-lifecycle`
  ist vollständig in diesen Change eingeflossen und gelöscht.)

## 1. Kanonische Config-Serialisierung, `ConfigStore` & Logging

- [x] 1.1 `ma2pi/web/serialize.py`: `redacted_config` durch einen kanonischen
  TOML-Schema-Serializer ersetzen (`device_banks.<dev>.<bank>` flach mit
  `encoders` als Liste ohne `None`-Felder, `encoder_acceleration`,
  `encoder_resolution.modifiers`, `led_notes`, `layouts.<key>`, keine inaktiven
  Union-Schlüssel). Verifikation: Roundtrip-Test lädt `config.toml`, serialisiert
  per `redacted_config` und wendet das Ergebnis per `prepare_patch` verlustfrei
  an.
- [x] 1.2 `ma2pi/runtime.py` & `ma2pi/config_store.py`: `ma2.password_file` und
  `ma2.password_env` in `_clean_patch` immer verwerfen; `None`-Felder in Dicts
  innerhalb von Listen bereinigen; `tomlkit.dumps` vor Rückgabe mit
  `tomllib.loads` gegenprüfen. Verifikation: `tests/test_config_api.py` (kein
  File-Oracle über `password_file`, kein `500 ConvertError`).
- [x] 1.3 `ma2pi/runtime.py`: `prepare_patch` und `_test_credentials` **vor**
  `engine.freeze()` ausführen; `PlaybackRouter` auf `engine.frozen` prüfen;
  Release-Frames (Hardkeys, Encoder-Klicks, Playback-Buttons) vor
  `apply_config`/`reconnect` aus der `SendQueue` flushen. Verifikation:
  `tests/test_runtime.py` (Live-Inputs laufen während fehlgeschlagenem
  Host-Test weiter; gehaltene Tasten senden Release vor Reconnect).
- [x] 1.4 `ma2pi/config.py`, `ma2pi/config_store.py` & `ma2pi/__main__.py`:
  `math.isfinite` in `_float()`; `_require_hardkey_codes` auch für
  `mapping.device_banks`; automatisches `migrate()` beim Start von
  `/etc/ma2pi/config.toml` sowie Unterstützung abweichender `--config`-Dateinamen;
  atomares `last-good.toml`, Passwort-Rollback bei `commit_prepared`-Fehler und
  korrekte Sortierung gleichsekündiger Backups in `rotate_backups()`.
  Verifikation: `tests/test_config.py`, `tests/test_config_store.py`,
  `tests/test_backups.py`.
- [x] 1.5 `ma2pi/logging_setup.py`: Redaction auf gequotete Dict-/JSON-Keys
  (`'password': ...`, `"password": ...`), `pin`, `psk`, `wifi-sec.psk`, `token`
  und formatierte Exception-Tracebacks erweitern. Verifikation:
  `tests/test_logging.py`.

## 2. Gemeinsamer Raw-MIDI-Pfad, Hotplug & `ProfileError`-Isolierung

- [x] 2.1 `ma2pi/led_output.py`, `ma2pi/midi_input.py` & `ma2pi/__main__.py`:
  `LedOutput` im Daemon über `MidiManager.send` betreiben (kein zweites
  `os.open(O_WRONLY)` auf denselben ALSA-Knoten; Standalone-Fallback mit
  `O_WRONLY | O_NONBLOCK` + `rawmidi_drop_output`); fremden `infos[0]`-Fallback
  in `_find_led_target` entfernen. Verifikation: `tests/test_led_output.py`,
  `tests/test_midi_input.py` (Replug ohne Blockade, kein Senden an fremdes
  Gerät).
- [x] 2.2 `ma2pi/midi_input.py`: `remove_reader(self._fd)` sofort in
  `RealMidiHandle._on_readable` bei `OSError`/EOF aufrufen; FD-Cleanup bei
  `__init__`-Fehler; vor `os.write` freien Platz `>= len(data)` prüfen;
  64-Bit-`time64`-Fallback für `_RawmidiStatus` ergänzen. Verifikation:
  `tests/test_midi_input.py` (kein wiederholter Reader-Callback bei voller
  Queue, kein 1-Byte-Teilwrite, 64-Bit-ioctl-Fallback).
- [x] 2.3 `ma2pi/hid_input.py` & `ma2pi/midi_input.py`: `ProfileError` in
  `reconcile()` je Gerät abfangen und per `_schedule_retry` drosseln;
  `HidManager._decoders` in `set_config` und `_close_device` leeren; bereits
  beanspruchte `info.path`-Knoten in `select_devices` und `select_midi_devices`
  ausschließen; `absinfo`-Bereiche cachen. Verifikation:
  `tests/test_hid_input.py`, `tests/test_midi_input.py`.

## 3. Daemon-Lifecycle, Activate-Hooks, Event-Stream & Web-Härtung

- [x] 3.1 `ma2pi/__main__.py`: `device_learn_task` im `finally` von
  `run_daemon()` **vor `engine.cleanup()`** abbrechen und erwarten; offene
  `EventBus`-Verbindungen beim Shutdown schließen. Verifikation: Test startet
  `run_daemon` im Dry-Run, löst das Stop-Signal aus und prüft, dass kein Task
  mit Namen `ma2pi-*` mehr läuft und der Exit-Code `0` ist.
- [x] 3.2 `ma2pi/__main__.py`: `LearnManager.set_config`,
  `DeviceLearnManager.set_config` (Poll-Zeile in `_device_learn_loop` entfällt)
  und Root-Log-Level als Activate-Hooks einhängen; LED-Nachführung in reinen
  `_led_step(config, client, midi, state)` und immer laufende 2-s-Schleife
  trennen (`README.md` um Laufzeitwirkung von `[led]` ergänzen). Verifikation:
  Unit-Tests ohne Hardware für Apply auf beide Learn-Manager, Log-Level sowie
  Aktivieren, Deaktivieren (`DISABLE` + `set_led(None)`), Farbwechsel, Replug
  und Leerlauf von `[led]`.
- [x] 3.3 `ma2pi/web/events.py`: je Subscriber ein `dropped: asyncio.Event`
  einführen; `events_handler` schließt den WebSocket, sobald `dropped` (durch
  `QueueFull` oder Session-Ende) gesetzt ist, ohne unnötige Tasks pro Event.
  Verifikation: `tests/test_web.py` — langsamer Client (`queue_size=1`) wird
  getrennt, zweiter Client erhält weiter Events, Reconnect erhält Anfangsstand,
  und `test_events_slow_client_is_dropped` (`subscriber_count` sinkt, bereits
  eingereihtes Event bleibt lesbar) bleibt grün.
- [x] 3.4 `ma2pi/web/__init__.py`: `PinSessions` mit festem 12-h-Ablauf,
  injizierbarer `time.monotonic`-Uhr, `asyncio.Lock`, längenunabhängigem
  UTF-8-Vergleich und wachsender Sperre ab 5 Fehlversuchen (`15..300 s`,
  `429 pin_locked` + `Retry-After`, ohne Weiterzählen während aktiver Sperre)
  einführen; Sessions und `/api/events`-WebSockets bei Logout, PIN-Wechsel und
  PIN-änderndem `restore_backup` widerrufen; `learn_start` auf `_json_body()`
  umstellen (`400 invalid_json`). Verifikation: `tests/test_web_auth.py`,
  `tests/test_learn_api.py`.
- [x] 3.5 `ma2pi/web/__init__.py`: Middleware zur Prüfung von `Host` (IP-Literale,
  `localhost`, `.local`, lokaler Hostname) und `Origin` (auf Schreibmethoden und
  `/api/events`) ergänzen; `DEFAULT_DIST`-Fallback für Paket-Entrypoints prüfen.
  Verifikation: `tests/test_web.py`.

## 4. Engine, Playback, Beschleunigung, Feedback & Aktivität

- [x] 4.1 `ma2pi/mapping.py`: `_held`, `_press_targets` und `_pending_hold` nach
  `(device, control)` schlüsseln; Halter-Zähler je Konsolen-Taste und je
  Encoder-Slot (Klick) für Press (`0 → 1`), Release (`1 → 0`) und höchstens
  einmaliges LUA-Hold-Upgrade; gerätübergreifende Modifier und `modifier_hook`
  (erster/letzter Halter inkl. Reset in `release_device`, `cleanup`,
  `on_connection_lost`); `engine.held` auf `(device, control)`-Schlüssel
  umstellen und Abfragen in `tests/test_mapping.py`, `tests/test_runtime.py` und
  `tests/test_ma2_client.py` anpassen. Verifikation: Tests für fremdes Release,
  geteilte Taste (Hardkey & Encoder-Klick), Hold-Upgrade, Modifier über zwei
  Geräte und leere Zähler nach Geräteverlust, Disconnect, Apply und Shutdown.
- [x] 4.2 `ma2pi/config.py` & `ma2pi/mapping.py`: `relative-encoder`-Controls in
  gebankten MIDI-Profilen für `[mapping.encoders]` und `device_banks`-Encoder
  freischalten. Verifikation: `tests/test_config.py`, `tests/test_mapping.py`.
- [x] 4.3 `ma2pi/playback.py` & `ma2pi/acceleration.py`: gedrückte
  Playback-Buttons als `(device, control) -> (page, executor, button)` verfolgen
  (korrektes Release über Bankwechsel, bei `DeviceLost` und `cleanup`, kein
  Schlucken von Engine-Releases); `_last_bank`/`_last_value` bei
  MA2-Disconnect zurücksetzen; `ValueAccelerator` nach `(device, bank, control)`
  schlüsseln, Sprung am Anschlag `0.0`/`1.0` beseitigen und Beschleunigungs-Log
  auf `DEBUG` stellen. Verifikation: `tests/test_playback.py` (inkl. `caplog`
  auf `INFO` ohne Beschleunigungszeile), `tests/test_acceleration.py`.
- [x] 4.4 `ma2pi/feedback.py`: Handle-Generationen je Gerät für gezielten
  Replug-Reset nutzen; Fortschrittsprüfung in `_output_stalled` (kein Fehlalarm
  bei Dauer-Updates); leere `playbacks`-Antworten als `off` werten und
  `"current"`-Antwortprüfung schärfen; Bank-Kanal, `device_banks` und
  Bank-Offset in `build_feedback_targets` berücksichtigen. Verifikation:
  `tests/test_feedback.py`.
- [x] 4.5 `ma2pi/activity.py`: `describe_frame` auf `pageIndex`, `execIndex`,
  `buttonId`, `name` und `hardkeyPress`/`hardkeyRelease` (`keyname`) anpassen.
  Verifikation: `tests/test_activity.py`.

## 5. MA2-Client, onPC-Auflösung, Learn-Modi & Netzwerk/Recovery

- [x] 5.1 `ma2pi/ma2_client.py` & `ma2pi/encoder_page.py`: `self._transport.close()`
  in `_handle_disconnect` und bei `authenticate`-Fehlern garantieren; Gesamt-
  Timeout für `authenticate`, kurzes `close_timeout`, WebSocket-Pings, saubere
  `shutdown`-Drain-Frist und dynamisches `keepalive_interval`; `PlaybacksRequest`
  in eigene koaleszierende Niedrigprioritäts-Queue legen und `BackpressureGuard`
  an echten Socket-Puffer knüpfen; bedarfsweises `presetTypes`-Update vor
  `EncoderResolution` + Geschwister-`"s"`-Reset in `EncoderPage._merge_by`;
  `set_mode_color` statt `apply_mode` bei `ToggleScreenMode`; asynchrone/gecachte
  Adressauflösung in `ScreenHelper`. Verifikation: `tests/test_ma2_client.py`,
  `tests/test_encoder_page.py`, `tests/test_screen_helper.py`.
- [x] 5.2 `ma2pi/learn.py` & `ma2pi/device_learn.py`: 2-s-Timeout für
  `awaiting_release`, Control-Lock für Encoder und Bank-Noten-Auflösung in
  `LearnManager`; Velocity `>= 2` für Buttons, Ignorieren unmittelbarer
  Folge-Frames derselben gelernten Note, `EventBus`-Publikation, Inaktivitäts-
  Ablauf pausierter Sitzungen und Freigabe gehaltener Tasten beim Lernstart in
  `DeviceLearnManager` + atomarer Lock in `device_learn_finish`. Verifikation:
  `tests/test_learn.py`, `tests/test_device_learn.py`, `tests/test_learn_api.py`.
- [x] 5.3 `ma2pi/network.py` & `ma2pi/recovery.py`: `time.monotonic()` +
  Warteschleife im Rollback-Timer sowie für die 60-s-Recovery-Karenzzeit;
  Loopback-/Broadcast-/Reserved-Prüfung für `gateway` und `dns`; strikte Typ-,
  UTF-8-Byte- und ASCII-Prüfung, Rollback bei `nmcli`-Fehler und Locking von
  `auto_cycle` in `RecoveryService`; Disk-Writes per `to_thread` entkoppeln.
  Verifikation: `tests/test_network.py`, `tests/test_recovery.py`.

## 6. Svelte-5-Oberfläche, Deploy & Contract-Tests

- [x] 6.1 `MappingPage.svelte`: `null`-Tombstones bei Union-Wechseln (`keys`,
  `playbacks`, `modifiers`), Einbindung von `controls.inventory`/`banks` (inkl.
  `accelerated` für MIDICRAFT-Encoder und feste Fader-Zeilen), Update von
  `original*` nach `save()`, `Abbrechen`-Button + Reset bei `'timeout'`/`'cancelled'`
  + `onDestroy`-Cleanup, Korrektur der doppelten Screen-Optionen `9`/`10`.
  Verifikation: `MappingPage.test.ts` mit echtem `redacted_config`-Fixture.
- [x] 6.2 `DevicesPage.svelte` & `AssignDialog.svelte`: Anpassen an flache
  `device_banks[dev][bank]`-Form, `untrack` im Geräte-`$effect`, Bewahren
  geerbter Bank-Offsets, Aktion „Belegung löschen“, `Screen-Encoder` als
  `<select>` (`Keiner` + `5..10`, nur Slot `1..4`) mit `null`-Bereinigung,
  reaktive Prop-Synchronisation ohne Svelte-5-Compilerwarnungen, korrekte
  Defaults für Fader/`relative-encoder`, Deaktivieren von Submit bei
  Mehrfachauswahl + Encoder sowie natives `<dialog>` (auch in `NetworkPage`).
  Verifikation: `DevicesPage.test.ts`, `AssignDialog.test.ts`, `npm run check`
  mit `0` Warnungen.
- [x] 6.3 `LearnPanel.svelte`, `App.svelte`, `PinGate.svelte`, `StatusPage.svelte`,
  `NetworkPage.svelte`, `DeviceSurface.svelte`, `AdvancedPage.svelte` & `status.ts`:
  sauberes Abbrechen/Sperren bei Bank-/Geräte-/Tab-Wechsel und `device_learn`-WS-Events;
  reaktiver Auth-Status nach PIN-Speichern, Restore und `401` sowie Anzeige von
  `429 pin_locked` in `PinGate`; Hotplug-Refresh auf `StatusPage`; `.error` +
  `role="alert"` + Feldbezug beim Rettungs-WLAN; lesbarer Text auf
  `"black"`-Tasten, `CSS.escape`, keyed `{#each}` und `prefers-reduced-motion`;
  `CRITICAL`-Level und Rate `5..40`. Verifikation: `PinGate.test.ts` (`429`),
  zugehörige Vitest-Dateien und neues `status.test.ts`.
- [x] 6.4 `deploy/` & Doku: `/opt/ma2pi/app` und `/opt/ma2pi/.venv` in
  `deploy/install.sh` auf `root:root` setzen, udev-/Polkit-Regeln schärfen,
  gemeinsames `NullSink` in `tests/conftest.py` konsolidieren, `docs/api.md` und
  `README.md` aktualisieren und `web/dist` neu bauen.

## 7. Abnahme

- [x] 7.1 Vollständige Prüfung: `.venv/bin/pytest -q`, `cd web && npm run check && npm test -- --run && npm run check:offline && npm run build` sowie `openspec validate fix-code-review-findings --strict` laufen ohne Fehler oder Warnungen.
- [x] 7.2 Live-Smoke auf dem Pi: Bank-Belegung & Encoder im UI speichern und neu
  laden, `[led]` in der Oberfläche aus- und einschalten, falsche PIN mehrfach
  eingeben (`429`), MIDICRAFT/ASL ab- und anstecken, Learn abbrechen und Dienst
  per `systemctl stop` sauber beenden (`< 5 s`).
