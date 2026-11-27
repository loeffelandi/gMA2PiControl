# Proposal

## Why

Mehrere Backend-Module sind über die Zeit zu Monolithen gewachsen, in denen
Schema, Parsing, Validierung, Laufzeitlogik und Verdrahtung in einer Datei
liegen:

| Datei | Zeilen | Befund |
|---|---|---|
| `ma2pi/config.py` | 2273 | 20+ Dataclasses (~390 Z.) und ~1850 Z. Parser/Prüfungen. `_parse_profiles` hat 443 Z., `_parse_mapping` 329 Z., `_parse_layouts` 123 Z., `_parse_led` 109 Z. in je **einer** Funktion. |
| `ma2pi/network.py` | 1623 | Modelle, `nmcli`-Parsing, Persistenz, `NetworkManagerBackend` und `NetworkService` (~650 Z.) in einer Datei. |
| `ma2pi/ma2_client.py` | 1199 | Transport, Login, `SendQueue`/`TokenBucket`/`BackpressureGuard` und `Ma2Client` (~725 Z.). |
| `ma2pi/web/__init__.py` | 945 | `create_app` ist ~535 Z. lang und enthält ~35 verschachtelte Handler-Closures; Middleware, Fehlerabbildung und `PinSessions` liegen daneben. |
| `ma2pi/__main__.py` | 732 | CLI, Daemon-Verdrahtung (`run_daemon` ~180 Z.), `_start_web` (~87 Z.), LED-Dienst, Input-Pipeline und Status-Snapshots. |
| `ma2pi/feedback.py` | 1067 | Palette, LED-Encoder, Playback-Parsing, Zielauflösung und `ExecutorFeedback`-Laufzeit in einer Datei; wuchs mit jedem LED-Change, jetzt stabil (Phase 5). |

Konkrete Folgen:

- **Invertierte Abhängigkeit**: `config.py` importiert Laufzeitmodule
  (`led_output`, `acceleration`, und über `feedback` das ganze
  Executor-Feedback für `PALETTE` **und** `build_feedback_targets`). Drei
  Querprüfungen am Ende von `parse_config` brauchen Laufzeitlogik:
  `_check_led_note_owner` (Feedback-Zielaufbau), `_check_midi_address_space`
  (`midi_remote`, `playback_targets` – per Lazy-Import, weil
  `playback_targets` selbst `config` importiert) und
  `_check_playback_transports` (reine Schemalogik). Das Schema ist kein Blatt
  im Abhängigkeitsgraphen; jede Schemaänderung zieht Laufzeitcode mit.
- **Hohe Konfliktrate**: In `config.py`, `web/__init__.py` und `__main__.py`
  trafen zuletzt mehrere Changes aufeinander (`fix-midicraft-led-output`,
  `add-per-device-led-protocols`, `resolve-combined-executors`; inzwischen
  archiviert); offen sind noch `encoder-mode-led-ui` und
  `device-profile-files`. Ein neues Feld
  bedeutet heute: Dataclass oben, Parser 800 Zeilen weiter unten, `serialize.py`,
  `config_store._clean_patch`, `api.ts` und `docs/api.md` anfassen.
- **Schlecht testbar und reviewbar**: 375-Zeilen-Funktionen lassen sich nur
  über komplette TOML-Dateien testen; Reviews müssen den ganzen Block lesen.
- **Tests koppeln an Privates**: Tests importieren `_process_input`,
  `_status_snapshot`, `_led_step` direkt aus `__main__` und patchen dort
  `_start_web`. Das verhindert jede Umgliederung von `__main__`, ohne dass die
  Tests es merken, bis sie brechen.

Der Zeitpunkt ist günstig, weil 819 Tests grün sind (Sicherheitsnetz) und
Hardware-Smoke-/Stresslogs vom 2026-11-26 vorliegen. Je mehr Funktionen noch
dazukommen, desto teurer wird der Schnitt; die LED-Changes sind archiviert,
offen sind nur noch Frontend-/Konfigurations-Changes (siehe Impact, Reihenfolge).

## What Changes

Reine **Struktur-Änderung ohne Verhaltensänderung**: gleiche Public-API, gleiche
TOML-Schlüssel und Fehlermeldungen, gleiche HTTP-Routen und Frames.

- **`ma2pi/config.py` → Paket `ma2pi/config/`**: Schema-Dataclasses und zugehörige
  Parser werden nach Domäne gebündelt (Verbindung, Geräte/Profile, Layouts,
  Hardkeys, Mapping, Hilfsdienste), die Feldprimitive (`_int`, `_choice`, …)
  in ein eigenes Modul gezogen und die Riesenfunktionen `_parse_profiles` und
  `_parse_mapping` in benannte Teilparser zerlegt. `ma2pi.config` re-exportiert
  die bisherige öffentliche Oberfläche unverändert.
- **Config als Blatt**: Schema-Typen, die `config` braucht (`LedSettings`,
  `ValueAccelerationSettings`, Paletten-Namen/`parse_color`), wandern in das
  Config-Paket bzw. ein Blattmodul; `led_output`, `acceleration` und `feedback`
  importieren sie von dort und re-exportieren sie für Bestandscode.
  Querprüfungen, die Laufzeitlogik brauchen (`_check_led_note_owner`,
  `_check_midi_address_space`), wandern in ein eigenes Modul
  `ma2pi/config/checks.py` mit Funktions-Lazy-Imports; es ist die einzige
  dokumentierte Ausnahme der Importrichtungs-Regel.
- **`ma2pi/web/`**: `create_app` wird auf Verdrahtung reduziert; Middleware
  (`PinSessions`, Host-/Origin-/PIN-/Request-Guard), Fehlerabbildung und die
  Handler werden in Routenmodule je Bereich (Auth, Status, Config, Learn,
  Backups, Netzwerk, Recovery, Geräte) ausgelagert.
- **`ma2pi/__main__.py`**: wird zur dünnen CLI-Fassade; Daemon-Verdrahtung
  (`daemon.py`), Input-Pipeline, LED-Dienst und Status-/Presence-Snapshots
  bekommen eigene Module (inklusive `_start_web`, `recovery_loop`,
  `_device_learn_loop`). `run_daemon` wird in Aufbau, Task-Supervision und
  geordneten Shutdown gegliedert; dabei kommen die neuen Dienste
  (`MidiRemoteService`, `ExecutorTopology`, `PlaybackRouter`,
  `ActivityTracker`) in die Verdrahtung.
- **`ma2pi/feedback.py` → Paket `ma2pi/feedback/`** (Phase 5, nach
  Phase 1): Encoder, Playback-Snapshot, Zielaufbau und `ExecutorFeedback`
  in getrennten Modulen hinter stabiler Fassade. Die Palette zieht schon in
  Phase 1 nach `ma2pi/palette.py`.
- **`ma2pi/network.py` und `ma2pi/ma2_client.py` → Pakete** mit stabiler
  `__init__`-Fassade (Modelle/Parsing/Backend/Service bzw. Transport/Login/
  Sendewarteschlange/Client).
- **Strukturwächter-Test**: Ein AST-basierter Test erzwingt die
  Abhängigkeitsrichtung (`config` importiert keine Laufzeitmodule) und eine
  Obergrenze für Moduldateien, damit die Monolithen nicht zurückkehren.
- **Tests**: Importe/Patch-Ziele privater Namen (`__main__._process_input`,
  `__main__._start_web`, `__main__.list_devices`, `__main__.run_dump_input`, …)
  werden auf die neuen Modulorte umgestellt;
  Assertions bleiben unverändert.
- **ADR**: neue ADR „Modulstruktur: Pakete mit stabiler Fassade und
  Abhängigkeitsrichtung“ (nächste freie Nummer beim Anlegen; 0024 und 0025 sind vergeben, derzeit 0026).
- **Keine BREAKING Changes** für Nutzer, `config.toml`, REST/WebSocket-API oder
  `systemd`-Unit. `python -m ma2pi` bleibt der Einstiegspunkt.

## Capabilities

### New Capabilities

Keine.

### Modified Capabilities

Keine. Das Verhalten ändert sich nicht; der Change setzt daher
`skip_specs: true`. Die Struktur-Garantien werden durch den
Strukturwächter-Test und die ADR festgehalten, nicht durch einen
Verhaltens-Spec.

## Impact

- **Packaging**: `pyproject.toml` führt Pakete explizit
  (`packages = ["ma2pi", "ma2pi.web"]`) und muss die neuen Unterpakete kennen.
- **Backend**: `ma2pi/config.py` (wird Paket), `ma2pi/network.py` (wird Paket),
  `ma2pi/ma2_client.py` (wird Paket), `ma2pi/web/__init__.py`,
  `ma2pi/__main__.py`, `ma2pi/led_output.py`, `ma2pi/acceleration.py`,
  `ma2pi/feedback.py` (Phase 1: Importe/Re-Exports; Phase 5: Paket),
  `ma2pi/playback_targets.py` (Importrichtung).
- **Tests**: `tests/test_cli.py`, `tests/test_led_output.py`,
  `tests/test_learn_api.py`, `tests/test_activity.py`, `tests/test_playback.py`,
  `tests/test_api_integration.py`, `tests/test_config_store.py`,
  `tests/test_feedback.py` (Importpfade);
  neu `tests/test_module_structure.py`.
- **Docs**: neue ADR (nächste freie Nummer), Abschnitt „Projektstruktur“ im `README.md`.
- **Nicht betroffen**: Frontend, `config.toml`-Format, `deploy/*`.
- **Reihenfolge / Abhängigkeit zu offenen Changes** (Details in `design.md`,
  D9): Archiviert sind `fix-code-review-findings`,
  `fix-review-followup-findings`, `add-per-device-led-protocols`,
  `fix-midicraft-led-output` und `resolve-combined-executors`. Zuerst läuft
  `mapping-device-feature-parity` (Frontend; backend-seitig nur der Golden-Test
  `tests/test_assignment_golden.py`, derzeit untracked). Offen mit möglicher
  Überschneidung zu `config.py`/`web/__init__.py`: `encoder-mode-led-ui`
  (`FieldSpec`-Katalog, `GET /api/config/schema`) und `device-profile-files`
  (Loader/Profile); `add-device-activity-leds` (6 offen) berührt keines der
  Zielmodule. Vorbedingung ist ein committeter Arbeitsbaum für `ma2pi/` und
  `tests/` und ein grüner `pytest -q`.
