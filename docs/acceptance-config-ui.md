# Abnahmematrix `add-ma2pi-config-ui`

Stand: automatisierte Nachweise auf dem Entwicklungsrechner sowie Live-Abnahme
auf dem Pi mit echter Cherry-/ASL-Hardware und systemd. Alle Abnahmen
einschließlich Abschlussreview 7.4 sind abgeschlossen.

## `config-ui`

| Anforderung / Szenario | Nachweis | Status |
| --- | --- | --- |
| Eingebettete Web-Oberfläche, lokale Assets | `ma2pi/web/__init__.py`, `web/dist`, `npm run check:offline`; Browser-Lasttest gegen lokalen Dateiserver (nur lokale Anfragen) | automatisiert |
| Zugriff aus dem LAN | Live-Aufruf `http://192.168.178.21:8080/` mit PIN-Sperre, Sperrseite, Entsperren und Warnbanner; `tests/test_web.py`, `tests/test_api_integration.py` | erledigt |
| Bind-Adresse geändert → Hinweis auf Neustart | UI-Hinweis „LAN-Port“ in `BackupsPage.svelte`/`BackupsPage.test.ts`; `[web]`-Doku in README; Listener bleibt bis zum Neustart | automatisiert/dokumentiert |
| Passwort nie in Antwort/Log/Fehler | `tests/test_config_api.py::test_get_config_never_returns_password`, `test_put_password_is_write_only`; `redacted_config()` | automatisiert |
| Verbindungstest erfolgreich/fehlgeschlagen | `tests/test_runtime_connection.py::test_check_connection_success`, `test_check_connection_wrong_password`, `test_check_connection_unreachable_host` | automatisiert |
| Laufende Session bleibt beim Test | `test_check_connection_reuses_active_session` | automatisiert |
| Geräte/Controls anzeigen | `tests/test_web_devices.py`, `MappingPage.test.ts` | automatisiert |
| Taste zuweisen | `MappingPage.test.ts` „edits a key mapping and tracks unsaved changes“ | automatisiert |
| Ungültiges Encoder-Ziel/Wheel | `MappingPage.test.ts` „shows a server validation error for an invalid wheel“; `test_config_api.py::test_put_rejects_invalid_config_without_writing` | automatisiert |
| Screen-Encoder bearbeiten/leeren | `MappingPage.test.ts` „edits the screen target per physical encoder“; `tests/test_config_api.py::test_put_sets_and_removes_screen_encoders` | automatisiert |
| Learn Taste/Encoder, Timeout, Abbruch | Live: `num_5`/`KEY_5`, `encoder.1`/`note 1` mit 54 Detents; `tests/test_learn.py`, `tests/test_learn_api.py` | erledigt |
| Live-Status, Reconnect-Anzeige, Encoder-Modus | `StatusPage.test.ts` (Statuswechsel, Reconnect, Attribut/Screen); `tests/test_web.py` WebSocket-Tests | automatisiert |
| Backups anlegen/listen/restore, ungültiges Backup | Live: Backup `config-20261126-023508.toml`, Änderung auf `DEBUG`, Restore auf Generation 5; `tests/test_backups.py`, `BackupsPage.test.ts` | erledigt |
| Zugriffsmodell, Formular-POST abgelehnt | Live: Formular-POST `415`, falsche PIN `401`, PIN/Passwort nicht in Antwort oder Journal; `tests/test_web.py`, `tests/test_config_api.py` | erledigt |
| PIN-Sperre, falsche/korrekte PIN, Logout, Warnbanner ohne PIN | Live: Sperrseite, Entsperren, Warnbanner bei deaktivierter PIN; `tests/test_web_auth.py`, `PinGate.test.ts`; PIN optional, serverseitig erzwungen | erledigt |
| PIN optional, Validierung und Geheimhaltung | `tests/test_web.py::test_web_config_accepts_changed_pin`, `test_web_config_requires_pin_when_enabled`, `test_web_auth.py::test_redacted_config_hides_pin` | automatisiert |

## `runtime-config`

| Anforderung / Szenario | Nachweis | Status |
| --- | --- | --- |
| Validierung vor dem Anwenden | `tests/test_runtime.py::test_apply_rejects_invalid_patch_without_changing_anything`, `tests/test_config_store.py::test_apply_patch_rejects_invalid_before_writing` | automatisiert |
| Atomares Schreiben, Kommentare, Backup | `tests/test_config_store.py::test_apply_patch_preserves_comments`, `test_apply_patch_creates_backup_and_last_good`, `test_apply_patch_aborts_without_partial_write` | automatisiert |
| Gehaltene Tasten in umgekehrter Reihenfolge freigeben | `test_runtime.py::test_apply_releases_held_keys_reverse_and_bumps_generation` | automatisiert |
| Offene Encoder-Deltas verwerfen | `test_runtime.py::test_apply_discards_open_encoder_delta` | automatisiert |
| Mapping-Tausch ohne Replay | `test_runtime.py`, `test_mapping.py`; `MappingEngine.swap_config` | automatisiert |
| Zugangsdaten testen und Reconnect | `test_runtime_connection.py::test_changed_credentials_reconnect_to_new_target`, `test_failed_credential_test_keeps_config_and_session` | automatisiert |
| Reine Mapping-Änderung ohne Session-Verlust | Live: mehrere Apply-Läufe bei verbundener Session 7; `test_runtime_connection.py::test_mapping_only_apply_keeps_session`, `test_api_integration.py` | erledigt |
| Ein Apply gleichzeitig / Generation | Live: Generation 6 → 7; `test_runtime.py::test_apply_rejects_second_call_while_busy`, `test_apply_releases_held_keys_reverse_and_bumps_generation` | erledigt |
| Kein Dienstneustart, gleiche PID | Live: MA+Store gehalten, Apply Generation 7, PID `5570` vor/nach, `ActiveEnterTimestamp` unverändert, kein neuer Dienststart | erledigt |
| Kein systemd-Eingriff | Live-Journal 02:41:38–02:41:46: nur Hardkey-/Encoder-Frames, kein `Started`/`Stopped` | erledigt |
| Verbindungsfehler nach erfolgreichem Apply | `tests/test_integration.py::test_reconnect_after_server_drop`, `tests/test_ma2_client.py::test_reconnect_after_connect_failure`; echter onPC-Ausfall während der Abnahme bewusst nicht induziert (laufende Show) | automatisiert/begründete Ausnahme |
| Wiederherstellung über Backup | Live: Restore auf Generation 5; `tests/test_backups.py::test_create_list_and_restore_backup`, `BackupsPage.test.ts` | erledigt |

## Pi-/LAN-Abnahme

Erledigt:

- 5.1: Installierte Unit mit `StateDirectory=ma2pi`, `StateDirectoryMode=0750`
  und `ReadWritePaths=/var/lib/ma2pi`; `systemd-analyze verify` grün.
- 5.2: `deploy-live.sh` hat `install.sh` zweimal auf Trixie ausgeführt; Dienst
  läuft danach.
- 5.3: README-Befehle für Build, Installation, Config-Check, Systemd-Verify,
  UI-Zugriff und Backups wurden auf dem Pi ausgeführt.
- 6.2: Browser-Smoke-Test im LAN: Status und Session 7, Zugangsdaten-Test,
  Mapping-Apply, Backup anlegen/ändern/restore, Sicherheitsprüfungen sowie
  echtes Lernen. Learn-Lauf am 26.11.2026: Taste `num_5` (`KEY_5`, Gerät
  `cherry`) und Encoder `encoder.1` (`note 1`, Richtung `1`, 54 Detents,
  Gerät `asl`); im Learn-Fenster wurden keine Mapping-Frames gesendet.
- 6.3: Hot-Reload mit gehaltener MA+Store-Taste. Press-Reihenfolge MA → Store,
  Apply auf Generation 7, danach Releases `STORE` → `MA` in umgekehrter
  Reihenfolge. PID `5570` vor/nach identisch, `ActiveEnterTimestamp`
  unverändert, kein neuer systemd-Start; nach dem physischen Loslassen keine
  weiteren Hardkey-Frames (keine hängenden Modifier).
- 6.4: UI aus dem LAN erreichbar, Formular-POST `415`, falsche PIN `401`,
  Passwort/PIN nicht in Antworten oder Journal, Build ohne externe Assets.
- 6.5: ADRs 0008–0013 auf `Accepted` gesetzt; die „Amends“-Links
  0009→0004 und 0010→0006 bleiben erhalten.
- 7.3: Pytest `339 passed`, Vitest `29 passed`, `svelte-check` 0/0,
  `npm run build` und `npm run check:offline` auf Entwicklungsrechner und Pi
  mit dem finalen Stand.

## Abschlussreview 7.4

Beide Deltas wurden Anforderung für Anforderung gegen die Matrix geprüft:

- `config-ui`: eingebettete Oberfläche/lokale Assets, LAN-Zugriff,
  Bind-Hinweis, Zugangsdaten und Session-Erhalt, Geräte-/Mapping-Editor,
  Screen-Encoder, Learn-Modus, Live-Status mit Encoder-Modus, Backups,
  PIN-Sperre in allen Zuständen sowie Schreibzugriffe/Geheimnisse sind durch
  automatisierte Tests und, wo nötig, durch die Live-Abnahme belegt.
- `runtime-config`: Validierung, atomares Schreiben mit Kommentaren und
  Backup, Freigabe gehaltener Tasten, Encoder-Delta-Verwerfung, Mapping-Tausch
  ohne Replay, Zugangsdaten/Reconnect, ein Apply gleichzeitig, Generation,
  kein Dienstneustart und Backup-Restore sind belegt oder als Ausnahme
  begründet.
- Bewusste Ausnahme: Ein echter onPC-Ausfall nach erfolgreichem Apply wurde
  während der laufenden Show nicht künstlich herbeigeführt. Das Verhalten ist
  durch `test_reconnect_after_server_drop` und
  `test_reconnect_after_connect_failure` automatisiert abgedeckt.
- `openspec validate add-ma2pi-config-ui --strict` ist grün; Pytest `339`,
  Vitest `29`, `svelte-check` 0/0, Build und Offline-Check sind grün.

Auf dem Pi ist die PIN-Sperre lokal aktiv; ohne gesetzte PIN
zeigt die Oberfläche den Warnbanner. Der Default bleibt bewusst offen und die
PIN wird nicht öffentlich dokumentiert.
