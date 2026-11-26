# Abschlussreview `add-ma2pi-core`

Stand: Software-Implementierung inklusive MIDI-Eingabe für den ASL, LUA-Hardkey-
Transport und Screen-Helper abgeschlossen; Hardware-/Deployment-Abnahme offen.
Dieses Dokument ordnet jeder Anforderung einen Nachweis oder eine begründete
Ausnahme zu. Es ersetzt nicht die Hardware-Abnahme (Tasks 3.8, 6.1–6.5, 7.3–7.5).
Task 3.7 (ASL-Capture), 5.8 (LED) und 1.6 (list-devices/dump-input) sind
abgeschlossen; Task 8.4 (Tests auf Pi und Entwicklungsrechner) mit 219 grünen Tests.

## `ma2-connection`

| Anforderung | Nachweis / Ausnahme |
| --- | --- |
| Verbindungsaufbau und Login | `Ma2Client.connect_once`, `tests/test_ma2_client.py::test_connect_once_success`, `tests/test_integration.py::test_end_to_end_input_to_recorded_frames`; Login-Fehler: `test_login_failure_raises`, `test_wrong_password_is_reported`. |
| Falsches Passwort → genau eine Meldung + Backoff | `_session_loop` loggt einmal pro Fehlversuch, `_backoff_delay(..., login_failed=True)`; `test_backoff_login_failure_uses_long_delay`. |
| onPC nicht erreichbar → wachsender Backoff | `_backoff_delay` mit `2**attempt`, Jitter und `max_delay`; `test_reconnect_after_connect_failure`. |
| Keepalive < 10 s, auch bei Traffic | Eigener Task `_keepalive_loop`; `test_keepalive_is_sent_on_idle`, `test_keepalive_covers_twelve_seconds_of_idle`; Konfiguration erzwingt `< 10` (`test_keepalive_must_be_below_ten`). |
| Reconnect, Queue leeren, kein Replay | `_handle_disconnect` + `MappingEngine.on_connection_lost`; `test_reconnect_after_server_drop` prüft genau einen Press nach Reconnect. |
| Globale Queue und Rate-Limit | `SendQueue` + `TokenBucket`; `test_queue_control_has_priority`, `test_queue_coalesces_encoder_targets`, `test_queue_never_drops_controls`, `test_token_bucket_limits_200_frames_in_100ms`. |
| Dry-Run ohne Socket, Frame-Logging | `DryRunTransport`, `tests/test_dry_run.py`; `test_dry_run_never_connects`. |
| Keine Passwort-/Hash-Logs | `logging_setup`-Redaktion; `test_secrets_are_redacted`, `test_password_keyword_is_redacted`. |
| Graceful Shutdown | SIGINT/SIGTERM in `run_daemon`, `Ma2Client.shutdown`; `test_shutdown_drains_release_before_close`, `test_shutdown_with_held_keys_releases_then_closes` (Release → `closeConnection`). |
| Backpressure | `BackpressureGuard`; `test_backpressure_guard_engages_and_recovers`, `test_backpressure_guard_buffer_threshold`, `test_backpressure_loop_engages_and_recovers`. |

## `mapping-engine`

| Anforderung | Nachweis / Ausnahme |
| --- | --- |
| Vollständige Konfigurationsvalidierung, Abbruch vor Frames | `config.py` (unbekannte Keys, Bereiche, Referenzen); `tests/test_config.py` deckt alle Fälle ab; `load_config` nennt Datei, Schlüsselpfad und Ursache. |
| Press/Release, Duplikat, verwaistes Release | `MappingEngine._press/_release`; `test_tap`, `test_hold_has_one_press_and_one_release`, `test_release_without_press_is_ignored`. |
| Modifier-Stack und Chords | `test_modifier_chord_order`, `test_desk_lock_acceptance`, `test_cleanup_releases_in_reverse_order`. |
| Desk Lock MA+Fix = vier Frames | `test_desk_lock_acceptance`, `test_end_to_end_input_to_recorded_frames`. |
| Hängende Tasten verhindern | `cleanup`, `release_device`, `on_connection_lost`; `test_device_loss_releases_only_that_device`, `test_connection_lost_clears_without_replay`. |
| CMD-Sequenzen unverändert, genau ein Frame | `test_cmd_key_only_sends_on_press`, `test_cmd_key_preserves_semicolon_sequence`. |
| Unmappte Controls ohne Frame | `test_unmapped_control_sends_nothing`, `test_unmapped_control_is_logged_once`. |
| Numerischer Hardkey-Override | `hardkeys.resolve` akzeptiert Zahlen; `test_numeric_hardkey_override`. |

## `encoder-control`

| Anforderung | Nachweis / Ausnahme |
| --- | --- |
| Zielmapping Slot 1–8 / festes Attribut, Bereich und Duplikate | `config.py`; `test_slot_out_of_range`, `test_slot_and_attribute_are_exclusive`, `test_midi_encoder_id_is_global`. |
| Akkumulation, 40-ms-Flush, Idle-Flush, Null-Delta | `flush_due`/`flush_all`; `test_slot_accumulates_and_flushes_once`, `test_zero_delta_sends_nothing`, `test_idle_flush_sends_last_detent`, `test_min_interval_between_flushes`. |
| Beschleunigung none/linear/exponentiell | `_acceleration_multiplier`; `test_acceleration_increases_delta_for_fast_rotation`, `test_acceleration_keeps_sign`, `test_fixed_attribute_encoder_is_supported`, `test_exponential_curve_accepts_german_spelling`. |
| Attribut-Fenster folgt der onPC | `EncoderPage.attributes()` leitet `(selected // 4) * 4` aus `presetTypes` ab, `page_refresh_interval` pollt jede Sekunde; `test_window_follows_selected_attribute`, `test_short_feature_stays_on_first_window`, `test_feature_change_uses_new_selection`. |
| Auflösung per Encoder-Klick (Normal/Fine/Ultra) | `ToggleFine` + `RESOLUTION_NAMES`; `test_fine_toggle_sends_resolution_frame` prüft 1 → 2 → 0. |
| Nativer Encoder-Frame, ein Frame pro Flush | `frames.encoder_attribute_frame`; `test_encoder_frame_uses_attribute_name`, `test_slot_encoder_uses_console_page`, `test_slot_encoder_ignored_without_page`. |
| Screen-Modus per Taste | `screen_mode` + `mapping.screen_encoders`; `test_screen_mode_key_toggles`, `test_screen_mode_key`, `test_screen_encoders_parsed`. |
| Rate-Limit, begrenzter Puffer, Nachlauf | `max_pending_delta` + Log; `test_pending_delta_is_capped`, `test_encoder_stress_against_mock_server` (100 Detents/s über 10 s, Summe 1000, ≤ 40 Frames/s, Queue-Tiefe ≤ 2). |
| Physische LED-Ansteuerung des ASL | `LedOutput` mit verifiziertem Protokoll (Enable `9F 7F 7F`, Kanal 1 Helligkeit, Kanal 2 Farbindex 8/48, Release nur beim Beenden); `test_led_output_writes_frames`; rot/grün am Gerät bestätigt (2026-11-25). |

## `hid-input`

| Anforderung | Nachweis / Ausnahme |
| --- | --- |
| Enumeration, Interface-Scoring, unbekannte Geräte | `select_devices`; `test_select_prefers_keyboard_interface`, `test_select_ignores_unknown`, `test_unknown_device_is_logged_once` (Debug, einmal pro Gerät). |
| Profile, fehlende Controls, fehlendes Profil | `validate_profile` bricht mit Profil/Gerät/Control ab; `test_profile_with_missing_control_aborts`; `test_vendor_match_without_profile_warns`. |
| Key-Normalisierung, Autorepeat, unbekannte Codes | `_normalise`; `test_normalise_key_and_autorepeat`. |
| Encoder-Decoding absolut/relativ, Wrap-around, Schwelle | `EncoderDecoder`; `test_encoder_absolute_three_and_minus_two`, `test_encoder_absolute_wrap_around`, `test_encoder_relative_and_direction`, `test_encoder_threshold_discards_noise`. |
| Hotplug, Geräteverlust, Wiederöffnen | `HidManager.reconcile`; `test_hid_manager_hotplug` (DeviceLost, Wiederöffnen ohne Neustart). |
| Fehlende Berechtigung mit udev-Hinweis und Backoff | `_schedule_retry`; `test_permission_error_keeps_daemon_running`, `test_open_failure_uses_backoff` (kein zweiter Versuch vor Ablauf, Retry danach). |
| Gerät fehlt beim Start, Backoff | `_next_delay` (Scan-Backoff bis 5 s, danach schnelles Polling); `test_missing_device_at_start_only_warns_once`. |
| MIDI-Enumeration und Backend-Filter | `midi_input.list_midi_devices` liest `/proc/asound/cards` und `/dev/snd/midiC*`; `select_midi_devices` filtert nach `backend = "midi"`; `test_midi_device_selection`; auf dem Pi liefert `--list-devices` `04d8:e817` und `/dev/snd/midiC3D0`. |
| MIDI-Parser, fragmentierte Nachrichten, Running Status | `MidiStreamParser`; `test_parser_note_on_and_velocity_one_release`, `test_parser_note_off_and_velocity_zero`, `test_parser_running_status_and_realtime`. |
| MIDI-Tasten und Encoder-Rastungen | `MidiManager._normalise`; `test_normalise_button`, `test_normalise_encoder`, `test_normalise_unknown_note_logged_once`. |
| MIDI-Hotplug und Rechtefehler | `MidiManager.reconcile`; `test_midi_manager_hotplug`, `test_midi_permission_error_keeps_daemon_running`, `test_missing_midi_device_warns_once`; auf dem Pi öffnet `--dump-input` beide Geräte ohne Root. |
| ASL-Hardware verifizieren | Task 3.7 abgeschlossen: geführter Mitschnitt vom 2026-11-25 ordnet Noten 1–4 den Encodern (Velocity `127` = rechts, `1` = links), Noten 5–8 den Encoder-Clicks und Noten 9–11 den Tasten zu. `--dump-input` auf dem Pi liefert `encoder.1..4 ±1` sowie `key fine`/`asl_click_1` mit `1/0`. |
| Cherry-Hardware verifizieren | Verifiziert 2026-11-26 (Task 3.8): einziges Interface `event4` (Cherry SPOS 046a:0038); geführter Capture über alle 123 Tasten (`docs/cherry-capture-2026-11-26.log`) – jede Taste genau 1 Press + 1 Release, keine Doppel-Events, keine fehlende/unerwartete Taste; Control-Reihenfolge identisch zur Profil-Belegung der gedruckten Tasten (X13 = schwarze Leertaste, MA = Logo-Taste). |

## Deployment und Abschluss

| Anforderung | Nachweis / Ausnahme |
| --- | --- |
| `deploy/install.sh` | Verifiziert 2026-11-26 (Task 6.1): zweimaliger Lauf auf Debian 13 Trixie fehlerfrei; `ma2pi`-User, `/opt/ma2pi/.venv`, pip install mit kompiliertem evdev. |
| `deploy/ma2pi.service` | Verifiziert 2026-11-26 (Task 6.2): `systemd-analyze verify` grün, Dienst `active`/`enabled`, Start/Stop/Restart ok; öffnet Cherry + ASL, LED aktiv, Session authentifiziert. **Abweichung:** `DeviceAllow`-Pfad-Globs entfernt (Cgroup-Filter → EPERM auf cgroup v2); Gerätezugriff über udev-Gruppe `ma2pi`. |
| udev-Regeln | Verifiziert 2026-11-26 (Task 6.3): Cherry (`input`, `046a`) und ASL (`sound`, `04d8:e817`) auf `root:ma2pi 0660`; Lesetest als `ma2pi` erfolgreich (Dienst öffnet beide Geräte). |
| README Installation/Update/Rollback | `README.md`; **Ausnahme:** vollständiger Befehlsdurchlauf auf dem Pi offen. |
| README Capture-Workflow | `README.md#wheel-protocol-capture` mit Chrome-DevTools-Schritten, Filter und Copy-Anleitung. |
| Konfigurationsreferenz | `README.md#configuration-reference`, Abgleich mit `config.py` inklusive `backend`, `notes` und `midi_encoders`. |
| `openspec validate --strict` | `Change 'add-ma2pi-core' is valid`. |
| `pytest` auf Entwicklungsrechner und Pi | 219 Tests grün auf dem Entwicklungsrechner (Task 8.4); Pi-Lauf steht mit dem Deployment aus. |
| Web-Remote-Hardkey-Transport | **Gelöst (2026-11-25):** Hardkeys laufen über `LUA 'gma.canbus.hardkey(code, press, hold)'` in der Command-Line (Press/Release getrennt, Halteschwelle 0.5 s, MA-Akkorde). Live verifiziert (MA+Fix → Desk Lock). ADR 0016 Accepted, Change `hardkey-lua-transport` archiviert (`99d6bd8`). |
| Screen-Tasten | **Gelöst (2026-11-26):** Screens haben keinen canbus-Code/Command/Keyname. Control-Typ `screen` (1–6) + `[screen_helper]` senden `screen <n>` per UDP an einen AutoHotkey-Helper (`docs/screen-helper.ahk`), der Insert → Ctrl+Alt+F1..F6 → Insert sendet. WinActivate nur für Screen 1. Screen 1/2/3 live verifiziert (`21a3452`, `831877c`). |
| Hardware-Smoke/Stress/Reconnect | **Ausnahme:** Tasks 7.3–7.5 benötigen onPC und Geräte. MA+Fix → Desk Lock und onPC-Neustart-Reconnect bereits live beobachtet. |
| ADR-Status | Erledigt 2026-11-26 (Task 7.6): 0002, 0003, 0004, 0005, 0006, 0007 auf Accepted mit Verifikations-Nachweis; 0001 auf Superseded by 0016 korrigiert; 0014 (MIDI) und 0016 (LUA-Hardkey) Accepted. |
