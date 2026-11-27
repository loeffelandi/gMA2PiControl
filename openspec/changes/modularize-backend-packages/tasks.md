# Tasks

Abnahmekriterium jeder Gruppe: `.venv/bin/python -m pytest -q` bleibt grün
(Baseline: 819 passed, vor Phase 0 neu messen) und `git diff -M --stat` zeigt Verschiebungen als Renames.
Pro Gruppe zwei Commits: erst „verschieben“ (nur Importe angepasst), dann
„zerlegen“ (Funktionen aufteilen), siehe `design.md` D9.3.

## 0. Vorbedingungen und Sicherheitsnetz

- [ ] 0.1 Vorbedingungen aus `design.md` D9.1 prüfen: `mapping-device-feature-parity`
  abgeschlossen (LED-/Executor-Changes sind bereits archiviert); Entscheidung
  zu `encoder-mode-led-ui` und `device-profile-files` (vorher fertig oder Pfade
  nachziehen) getroffen; `add-device-activity-leds` darf offen bleiben.
  Arbeitsbaum committen (mindestens `ma2pi/`, `tests/`). Verifikation:
  `git status` ist für `ma2pi/` und `tests/` sauber, `pytest -q` grün,
  Baseline-Zahl notiert.
- [ ] 0.2 Fassaden-Inventar erzeugen: die öffentlichen Namen von `ma2pi.config`,
  `ma2pi.network`, `ma2pi.ma2_client`, `ma2pi.web` per Skript aus dem
  Ist-Stand ermitteln und als `EXPECTED_EXPORTS` in
  `tests/test_module_structure.py` ablegen (Test prüft `hasattr` je Name).
  Verifikation: Test ist vor dem Umbau grün.
- [ ] 0.3 Golden-Test für die Config: `config.toml` laden, `redacted_config()` als
  JSON-Snapshot (`tests/golden/config_redacted.json`) festschreiben und
  vergleichen; zusätzlich eine Tabelle „fehlerhafte Mini-Config →
  erwartete `ConfigError.path`“ aus den Fehlerfällen von `tests/test_config.py`.
  Verifikation: Test vor dem Umbau grün; beim Ändern der Parser-Reihenfolge rot.
- [ ] 0.4 Strukturtest-Gerüst anlegen: Importrichtung `ma2pi.config.*` (noch
  `xfail`, solange Phase 1 nicht fertig), Zeilenobergrenze 600 mit
  `ALLOWED_LARGE` (`config.py`, `network.py`, `ma2_client.py`, `web/__init__.py`,
  `__main__.py` plus `midi_input.py`, `feedback.py` (bis Phase 5), `mapping.py`,
  `hid_input.py`) und Paketlisten-Vergleich gegen `pyproject.toml`. Die
  Importregel kennt die `checks.py`-Ausnahme (Whitelist `feedback`,
  `midi_remote`, `playback_targets`, nur funktionslokal).
  Verifikation: `pytest tests/test_module_structure.py` läuft.
- [ ] 0.5 `pyproject.toml`: `packages` auf `[tool.setuptools.packages.find]`
  (`include = ["ma2pi*"]`) umstellen, damit neue Unterpakete automatisch
  mitgebaut werden. Verifikation: frisches venv, `pip install .`,
  `python -m ma2pi --help` und `python -c "import ma2pi.web"`.

## 1. Phase 1: `ma2pi/config/`

- [ ] 1.1 Verschieben: `config.py` → Paket `ma2pi/config/` mit `__init__.py`-
  Fassade, `errors.py`, `fields.py` (Primitive ohne Unterstrich), Rest zunächst
  unverändert in `loader.py`/`app.py`. Verifikation: Suite grün, Golden-Test grün.
- [ ] 1.2 Blatt herstellen: `ma2pi/palette.py` (`PALETTE`, `PALETTE_RGB`,
  `COLOR_INDICES`, `parse_color`), `LedSettings` nach `config/services.py`,
  `ValueAccelerationSettings` nach `config/mapping/model.py`; `led_output.py`,
  `acceleration.py`, `feedback.py` importieren und re-exportieren.
  `_check_led_note_owner` und `_check_midi_address_space` nach
  `config/checks.py` verschieben (Imports nur in der Funktion, Aufruf-
  reihenfolge am Ende von `parse_config` unverändert; `playback_targets`
  importiert weiterhin `config`, also kein Modulebenen-Import in die Gegen-
  richtung). Verifikation: Strukturtest „Importrichtung“ ohne `xfail` grün;
  `python -X importtime -c "import ma2pi.config" 2>&1 | rg feedback` liefert
  keinen Treffer; Golden-Test und Fehlerpfad-Tabelle aus 0.3 grün (Prüfung
  `ConfigError.path` für `led.note`/`led.fine_note`/`led.nipple_note` und
  `midi_remote.channels`).
- [ ] 1.3 Abschnittsmodule (`services.py` enthält auch `MidiRemoteSettings`;
  `effective_transport` wird öffentlich exportiert): `connection.py`, `services.py`, `devices.py`,
  `layouts.py`, `hardkey_codes.py` mit Dataclass und Parser nebeneinander;
  `_parse_layouts` (123 Z.), `_parse_led` (109 Z.) und `_parse_ma2` (93 Z.) in
  benannte Teilparser zerlegen. Verifikation: Suite grün; keines dieser Module
  > 400 Z.; keine Funktion > 80 Z.
- [ ] 1.4 `profiles/` zerlegen: `parse_profiles` in `controls`, `encoders`,
  `notes_banks`, `led_feedback` aufteilen; geteilten Zustand
  (`global_encoder_ids`, `control_owner`, `used_notes`) in ein
  `ProfileRegistry` kapseln; Prüfreihenfolge unverändert. Verifikation:
  Golden-Test und alle 110 Tests in `tests/test_config.py` grün; keine Funktion
  > 80 Z.
- [ ] 1.5 `mapping/` zerlegen: `parse_mapping` in `modifiers`, `keys`, `encoders`,
  `playbacks`, `device_banks`, `acceleration`, `resolution` aufteilen, Kontext
  (Controls, Encoder-IDs, Wertarten) als `MappingContext`. Verifikation:
  Golden-Test, `tests/test_config.py`, `tests/test_layouts.py`,
  `tests/test_config_api.py` grün.
- [ ] 1.6 Querverweis-Prüfungen (`led.device`, Hardkey-Codes bei `lua`-Transport)
  in `loader.py` bündeln; `parse_config` auf Orchestrierung reduzieren
  (< 60 Z.). Verifikation: Suite grün; Strukturtest: kein Modul unter
  `ma2pi/config/` über 400 Z.
- [ ] 1.7 Docs: `README.md`-Abschnitt „Projektstruktur“ (Config-Paket, Regel
  „Dataclass + Parser nebeneinander“, Checkliste „neues Config-Feld: welche
  Dateien“). Verifikation: dokumentierte Checkliste an einem Probe-Feld
  nachvollzogen (nicht committet).

## 2. Phase 2: `ma2pi/web/`

- [ ] 2.1 Verschieben: `keys.py`, `sessions.py` (`PinSessions`), `middleware.py`,
  `errors.py` aus `web/__init__.py` herauslösen; `__init__` re-exportiert
  `create_app`, `API_VERSION`, `BUS_KEY`, `REQUEST_HEADER`, … Verifikation:
  `tests/test_web*.py`, `tests/test_api_integration.py`, `tests/test_recovery.py`,
  `tests/test_network_api.py` grün.
- [ ] 2.2 `status_provider`, `devices_provider`, `dist` als App-Keys ablegen;
  `deps.require_store(request)` einführen und alle 503-Blöcke („Config-Store
  fehlt“, derzeit neun Zugriffe auf `CONFIG_STORE_KEY`) ersetzen
  (identische Antwort `503 config_store_unavailable`). Verifikation: neuer Test,
  der alle Store-abhängigen Routen ohne Store aufruft und den Body vergleicht.
- [ ] 2.3 Handler aus `create_app` in `web/routes/*.py` (`auth`, `system`,
  `config`, `learn`, `device_learn`, `backups`, `network`, `recovery`,
  `devices`, `static`) als Modulfunktionen mit `register(app)`;
  `create_app` nur noch Verdrahtung (< 80 Z.). Verifikation: Routentabelle vor
  und nach dem Umbau identisch (Test vergleicht
  `[(r.method, r.resource.canonical) for r in app.router.routes()]` gegen eine
  gespeicherte Liste); Suite grün.
- [ ] 2.4 Fachlogik aus `device_learn_finish` nach `ma2pi/device_learn.py`
  (`build_bank_patch`) mit typisierten Fehlern; Handler mappt auf
  `409 device_learn_stale|device_learn_conflict`. Verifikation: neue
  Unit-Tests für `build_bank_patch` (Konflikt, stale, Neu-Learn ersetzt
  Control) plus unveränderte Tests in `tests/test_learn_api.py`.

## 3. Phase 3: `ma2pi/__main__.py` und Daemon

- [ ] 3.1 Verschieben: `cli.py`, `daemon.py`, `pipeline.py`, `led_service.py`,
  `snapshots.py`, `web_service.py` (`_start_web` mit benanntem `WebService`
  statt 5-Tupel, `recovery_loop`) anlegen; `run_dump_input` nach `cli.py`;
  `__main__.py` bleibt dünn (`main`). Kein dauerhafter Re-Export der
  Unterstrich-Namen. Verifikation: `python -m ma2pi --help`
  und `python -m ma2pi --dry-run` (mit Test-Config) starten wie zuvor.
- [ ] 3.2 Tests umstellen: Importe und Patch-Ziele in `test_cli.py`,
  `test_led_output.py`, `test_learn_api.py`, `test_activity.py`,
  `test_playback.py`, `test_api_integration.py`, `test_config_store.py` auf die
  neuen Module (Patchen am Verwendungsort; betroffene Patch-Ziele:
  `_start_web`, `run_dump_input`, `list_devices` in `test_cli.py`,
  `list_midi_devices` in `test_led_output.py`). Verifikation: Suite grün; Test
  in `test_cli.py` bestätigt, dass der gepatchte `_start_web`/`run_dump_input`
  tatsächlich aufgerufen wurde.
- [ ] 3.3 Vorab die heutige Start- und Shutdown-Reihenfolge von `run_daemon` als
  Aufrufprotokoll-Test festhalten (inkl. `midi_remote.start()/close()`,
  `sleep(0.05)` vor `client.shutdown()`, Web-Abbau, `hid`/`midi.close()`); dann
  `run_daemon` gliedern: `Services`-Dataclass (inkl. `topology`,
  `midi_remote`, `playback`, `activity`, `web`), `build_services()`,
  `start_tasks()`, `shutdown()`. Verifikation: Reihenfolge-Test und der
  bestehende Test `tests/test_cli.py::test_run_daemon_shutdown_leaves_no_ma2pi_tasks`
  (kein `ma2pi-*`-Task übrig, Exit-Code 0) bleiben grün; keine Funktion > 80 Z.

## 4. Phase 4: `ma2pi/network/` und `ma2pi/ma2_client/`

- [ ] 4.1 `network.py` → Paket (`errors`, `parsing`, `models`, `store`, `runner`,
  `backend`, `service`); Fassade exportiert alle bisherigen Namen.
  `_validate_locked` (136 Z.) und `_rollback_locked` (105 Z.) in Teilschritte
  zerlegen.
  Verifikation: `tests/test_network.py` (37), `tests/test_network_api.py`,
  `tests/test_recovery.py` grün; Fassaden-Test grün.
- [ ] 4.2 `ma2_client.py` → Paket (`errors`, `transport`, `auth`, `sendqueue`,
  `client`); Fassade unverändert; `_dispatch` (127 Z.) in Teilhandler
  zerlegen. Verifikation: `tests/test_ma2_client.py` (55),
  `tests/test_integration.py`, `tests/test_runtime_connection.py` grün.
- [ ] 4.3 Liegt `network/service.py` oder `ma2_client/client.py` danach über 600 Z.,
  nur den Rollback-/Timer-Teil bzw. die Wartungsschleifen in eine
  Hilfsklasse auslagern; sonst Eintrag in `ALLOWED_LARGE` mit Begründung.
  Verifikation: Strukturtest grün.

## 5. Phase 5: `ma2pi/feedback/` (`design.md` D10)

- [ ] 5.1 Voraussetzung prüfen: `feedback.py` wird von keinem offenen Change mehr
  geändert (`encoder-mode-led-ui`, `add-device-activity-leds` darauf prüfen).
  Verifikation: `rg feedback openspec/changes/*/tasks.md` (ohne Archiv) zeigt
  keine offene Arbeit an `ma2pi/feedback.py`.
- [ ] 5.2 Verschieben: `feedback.py` → Paket `ma2pi/feedback/` mit Fassade
  (`encoders`, `snapshot`, `targets`, `service`); alle bisherigen Namen
  (`PALETTE`, `build_feedback_targets`, `led_notes_by_bank`,
  `resolve_playback_target`, `parse_playbacks`, `ExecutorFeedback`, …) bleiben
  importierbar, ebenso die privaten Namen `_belongs_to_block` und `_block_key`,
  die `tests/test_feedback.py` und `tests/test_poller.py` importieren.
  Verifikation: `tests/test_feedback.py`, `tests/test_poller.py`,
  `tests/test_led_output.py`, `tests/test_playback.py` unverändert grün;
  Fassaden-Test erweitert.
- [ ] 5.3 `config/checks.py` auf `feedback.targets` umstellen und `feedback.py`
  aus `ALLOWED_LARGE` streichen. Verifikation: Strukturtest grün; kein Modul
  unter `ma2pi/feedback/` über 600 Z.

## 6. Abschluss

- [ ] 6.1 ADR `docs/adr/<nächste freie Nummer>-modulstruktur-pakete-mit-stabiler-fassade.md`
  (0024 und 0025 sind vergeben, derzeit 0026; Nummer erst beim Anlegen per
  `ls docs/adr` bestimmen, da `encoder-mode-led-ui` und `device-profile-files`
  ebenfalls ADRs planen; Dateiname und Index-Eintrag müssen übereinstimmen) nach
  `docs/adr/templates/template.md` (Kontext, Entscheidung D1–D10, Folgen) und
  Eintrag in `docs/adr/README.md`. Verifikation: Datei vorhanden, ADR-Index
  verlinkt sie.
- [ ] 6.2 Strukturtest finalisieren: `xfail`-Marker entfernt, `ALLOWED_LARGE`
  enthält nur noch begründete Einträge. Verifikation: `pytest
  tests/test_module_structure.py` grün; absichtlich eine Config-Datei mit
  `import ma2pi.feedback` auf Modulebene versehen lässt den Test rot werden
  (danach zurückgenommen); ein funktionslokaler Import in `checks.py` bleibt
  grün.
- [ ] 6.3 Vollständige Prüfung: `.venv/bin/python -m pytest -q` (≥ Baseline aus 0.1),
  `cd web && npm run check && npm test -- --run` (unverändert grün, da
  Frontend unberührt), frisches venv `pip install .` + `python -m ma2pi --help`,
  `openspec validate modularize-backend-packages --strict`.
- [ ] 6.4 Hardware-Smoke nur auf ausdrückliche Freigabe: Dienst auf dem Pi
  starten und gemäß `docs/hardware-smoke-2026-11-26.log` prüfen (MA2-Login,
  HID/MIDI-Eingabe, LED, Netzwerkseite). Verifikation: Log analog zum
  bestehenden Smoke-Log, keine Fehler beim Start.

## Workflow follow-up

- Nach Phase 1 den Folge-Change `device-profile-files` (Profile als Dateien je
  Gerät plus kompakte Deklaration, Status: Entwurf, Review ausstehend) umsetzen,
  sobald dessen Review-Gate abgehakt ist.
- Danach Frontend-Split (`MappingPage`, `DevicesPage`, `NetworkPage`, `api.ts`)
  als eigener Change, sobald `mapping-device-feature-parity` abgeschlossen ist.
- Change archivieren, sobald die Review-Anforderungen des Projekts erfüllt sind.
