# Design

## Context

Motivation und Zahlen: siehe `proposal.md` (Why). Für den Schnitt relevant:

- `ma2pi/config.py` (2273 Z.) besteht aus drei Schichten, die nur lose
  zusammenhängen: **Schema** (Dataclasses, bis ca. Z. 460), **Feldprimitive**
  (`_table`, `_int`, `_choice`, …) und **Parser/Validierung**
  (ca. Z. 500–2273; Zeilen ändern sich mit den offenen Changes, maßgeblich sind
  die Funktionsnamen). Die Parser sind pro TOML-Abschnitt gegliedert, aber
  `_parse_profiles` (443 Z.) und `_parse_mapping` (329 Z.) bündeln je ein
  halbes Dutzend Teilabschnitte (Controls, Encoder, Noten, MIDI-Encoder,
  MIDI-Werte, Bänke, LED-Feedback bzw. Modifier, Keys, Encoder, Screen-Encoder,
  Playbacks, Device-Banks) mit geteiltem Zustand (`global_encoder_ids`,
  `control_owner`) als lokale Variablen. Weitere Funktionen über 80 Z.:
  `_parse_layouts` (123), `_parse_led` (109), `_parse_ma2` (93),
  `parse_config` (79).
- `config.py` importiert `led_output` (`LedSettings`, `parse_color`),
  `acceleration` (`ValueAccelerationSettings`) und `feedback` (`PALETTE`,
  **`build_feedback_targets`**). Letzteres lädt das komplette Executor-Feedback
  (1067 Z.) beim Import der Konfiguration. `parse_config` endet mit drei
  Querprüfungen: `_check_led_note_owner` (ruft `build_feedback_targets`),
  `_check_midi_address_space` (Lazy-Import von `midi_remote` und
  `playback_targets`; letzteres importiert selbst `config`) und
  `_check_playback_transports` (reine Schemalogik).
- `web/__init__.py`: `create_app` schließt über `status_provider`,
  `devices_provider`, `dist` und `bus` ein. Die meisten Handler lesen ohnehin
  schon `request.app[...]`. Mehrere Handler (neun Zugriffe auf `CONFIG_STORE_KEY`) wiederholen den Block
  „`store = request.app.get(CONFIG_STORE_KEY)`, sonst 503“. `device_learn_finish`
  enthält ~70 Zeilen Fachlogik (Bank-Patch aus Learn-Ergebnis berechnen,
  Konflikte prüfen), die nicht in einen HTTP-Handler gehört.
- `__main__.py` (732 Z., `run_daemon` 181 Z., `_start_web` 87 Z.): Tests
  importieren `_process_input`, `_learn_loop`, `_status_snapshot`,
  `_activity_event`, `_led_step`, `_find_led_target`, `_config_paths` und
  patchen im Modul `__main__` `_start_web` (`test_cli.py`), `run_dump_input` und
  `list_devices` (`test_cli.py`) sowie `list_midi_devices` (`test_led_output.py`).
  `run_daemon` verdrahtet inzwischen auch `MidiRemoteService`,
  `ExecutorTopology`, `PlaybackRouter` und `ActivityTracker`; `_start_web`
  liefert ein 5-Tupel (`runner`, `task`, `bus`, `network`, `recovery_task`).
- Öffentliche Importpfade, die Bestandscode und Tests nutzen:
  `ma2pi.config`, `ma2pi.network`, `ma2pi.ma2_client`, `ma2pi.web`
  (`create_app`, `API_VERSION`, `BUS_KEY`, …), `ma2pi.web.events|serialize|devices`.
- Baseline: `.venv/bin/python -m pytest -q` → 819 passed (26 s; vor Phase 0 neu messen). Dieser Lauf ist
  das Abnahmekriterium jeder Phase.

## Goals / Non-Goals

**Goals:**

- Jede Moduldatei hat **eine** Verantwortung und bleibt unter einer
  Zeilenobergrenze (Ziel ≤ 400 Z., harte Grenze ≤ 600 Z. im Strukturtest);
  keine Funktion über ~80 Z., ausgenommen reine Datentabellen.
- `config` ist ein **Blatt** im Importgraphen: es importiert nur Standardbibliothek,
  `hardkeys` und eigene Untermodule.
- Neues Config-Feld = Änderung in **einem** Domänenmodul (Dataclass und Parser
  nebeneinander), nicht an zwei Stellen mit 800 Zeilen Abstand.
- Bestehende Importpfade (`from ma2pi.config import AppConfig, …`) funktionieren
  unverändert; Tests ändern nur Importpfade privater Namen.
- Phasenweise umsetzbar: nach jeder Phase ist die Testsuite grün und die Phase
  einzeln committ- und revertierbar.

**Non-Goals:**

- Keine Verhaltensänderung: gleiche TOML-Schlüssel, gleiche Fehlertexte und
  `ConfigError.path`-Werte, gleiche REST-Routen/Statuscodes/Fehler-Codes,
  gleiche WebSocket-Events, gleiche Frames.
- **Kein Format-Umbau der `config.toml`** (Includes, Profil-Templates, Split in
  mehrere Dateien) – siehe „Offene Punkte“.
- Kein Pydantic/Schema-Framework, keine neuen Abhängigkeiten auf dem Pi.
- Keine Single-Source-of-Truth-Generierung für Schema ↔ `serialize.py` ↔
  `config_store._clean_patch` ↔ `api.ts` ↔ `docs/api.md` (eigener Change; hier
  nur durch die Domänenaufteilung erleichtert).
- Frontend (`MappingPage.svelte` 846 Z., `DevicesPage.svelte` 772 Z.,
  `NetworkPage.svelte` 587 Z., `api.ts` 508 Z.) – eigener Change, andere
  Werkzeuge (Svelte-MCP, Vitest). Außerdem schreibt
  `mapping-device-feature-parity` (33 offene Tasks, baut den gemeinsamen
  Tab-Store) `MappingPage`, `DevicesPage` und `AssignDialog` um; ein
  paralleler Split würde damit kollidieren. Er muss **nach**
  `mapping-device-feature-parity` kommen. (`fix-code-review-findings` ist
  archiviert und nicht mehr zu beachten.)
- Nicht angefasst, da kohäsiv bzw. < ~830 Z.: `mapping.py` (690),
  `hid_input.py` (651), `midi_input.py` (824), `recovery.py`, `config_store.py`.
  Beobachtungsliste, falls sie weiter wachsen (siehe Offene Punkte).
  `feedback.py` (1067 Z.) ist **kein** Non-Goal mehr, sondern Phase 5 (D10);
  nur die Palette zieht schon in Phase 1 aus.

## Decisions

### D1: Modul → Paket mit unveränderter Fassade

`config.py`, `network.py`, `ma2_client.py` werden zu Paketen gleichen Namens;
`__init__.py` re-exportiert exakt die bisher genutzten öffentlichen Namen
(per explizitem `__all__`). Der Importpfad bleibt, `git mv` bewahrt die
Historie der größten Teile.

*Alternative:* Untermodule mit neuen Namen und alle Importe im Repo umstellen.
Verworfen: erzeugt Diff-Rauschen in ~35 Dateien/Tests, ohne Nutzen, und bricht
Bestandscode im offenen-Changes-Stapel.

### D2: Zielstruktur `ma2pi/config/`

```
config/
  __init__.py     Fassade: AppConfig, load_config, parse_config, find_config,
                  ConfigError, alle Settings-/Profil-/Mapping-Dataclasses
  errors.py       ConfigError
  fields.py       Feldprimitive (table, reject_unknown, require, string, int_,
                  float_, bool_, choice, midi_note, midi_velocity) – ohne Unterstrich-
                  Präfix, da modulübergreifend genutzt
  connection.py   Ma2Settings, ReconnectSettings, RateLimitSettings + Parser
  services.py     LoggingSettings, WebSettings, ScreenHelperSettings,
                  FeedbackSettings, LedSettings, MidiRemoteSettings (neu durch
                  `add-midi-remote-executors`) + Parser (led/feedback/web/
                  midi_remote/…)
  devices.py      DeviceConfig + Parser
  profiles/
    __init__.py   ProfileConfig + parse_profiles (orchestriert Teilparser)
    model.py      EncoderProfile, MidiEncoderProfile, MidiValueProfile,
                  ControlProfile, BankProfile, LedFeedbackProfile
    controls.py   Controls + Encoder-ID-Vergabe für gebankte Encoder
    encoders.py   evdev-Encoder, MIDI-Encoder, MIDI-Werte
    notes_banks.py flache Noten, Bänke
    led_feedback.py [profiles.*.led_feedback]
  layouts.py      LayoutCell, LayoutRow, DeviceLayout + Parser
  hardkey_codes.py HardkeyCode + Parser + Pflichtcode-Prüfung
                  (nicht `hardkeys.py`, um Verwechslung mit `ma2pi/hardkeys.py` zu vermeiden)
  mapping/
    __init__.py   MappingSettings + parse_mapping (orchestriert)
    model.py      Modifier/Key/Encoder/Playback/Acceleration/Resolution/
                  DeviceBank-Dataclasses
    modifiers.py, keys.py, encoders.py, playbacks.py,
    device_banks.py, acceleration.py, resolution.py
                  (`topology_interval_ms` aus `resolve-combined-executors`
                  bleibt Feld von `MappingSettings`; `effective_transport`
                  wird zu einer öffentlichen Funktion in `mapping/playbacks.py`
                  und über die Fassade exportiert, `playback_targets` nutzt sie)
  app.py          AppConfig (+ Methoden), Querverweis-Validierung zwischen
                  Abschnitten (led.device, Hardkey-Codes bei lua-Transport,
                  `_check_playback_transports`)
  checks.py       Querprüfungen mit Laufzeitlogik: `_check_led_note_owner`
                  (build_feedback_targets), `_check_midi_address_space`
                  (midi_remote, playback_targets). Imports nur innerhalb der
                  Funktionen (Lazy); einzige Ausnahme der Blatt-Regel (D4/D8.1)
  loader.py       parse_config, load_config, find_config, DEFAULT_CONFIG_PATHS
```

Regeln: Dataclass und Parser eines TOML-Abschnitts liegen im selben Modul;
Abschnittsparser kennen nur ihren Abschnitt, Querverweise (Gerät → Profil,
Mapping → Controls) werden explizit als Parameter hereingereicht, wie es
`_parse_devices(raw, profiles)` heute schon tut. Querverweis-Prüfungen, die
mehrere Abschnitte betreffen (z. B. `led.device ∈ devices`), liegen gesammelt
in `loader.py`/`app.py`, nicht in den Abschnittsparsern.

*Alternative:* nur zwei Dateien (`schema.py` + `parse.py`). Verworfen: halbiert
die Datei, löst aber weder die Riesenfunktionen noch das Zwei-Stellen-Problem.

### D3: Riesenparser zerlegen, Zustand explizit

`_parse_profiles` → je Teilabschnitt eine Funktion mit klarer Signatur
(`parse_controls(item, path) -> list[ControlProfile]`,
`parse_encoders(item, path, ids) -> …`, …). Der heute lokal geteilte Zustand
(`global_encoder_ids`, `control_owner`, `used_notes`) wird in ein kleines
`ProfileRegistry`-Objekt (mutable Dataclass, nur während des Parsens) gekapselt
und explizit übergeben. `_parse_mapping` analog, mit der Controls-/Encoder-ID-
Menge als einem `MappingContext`.

Entscheidend: **Reihenfolge der Prüfungen bleibt identisch**, weil sie die
zuerst gemeldete `ConfigError` bestimmt (`tests/test_config.py` hat 110 Tests,
viele prüfen `exc.path`/Meldung). Es gibt bewusst *keinen* „bessere
Fehlermeldungen“-Anteil in diesem Change.

*Alternative:* deklaratives Schema (Pydantic/msgspec/`attrs`+Validatoren).
Verworfen: andere Fehlertexte/Pfade, neue Abhängigkeit auf dem Pi (ADR-0004
deployt als venv unter `/opt/ma2pi`), und `tomlkit`-Roundtrip bleibt ohnehin
manuell.

### D4: Config als Blatt – Typen wandern zur Konfiguration, nicht umgekehrt

- `LedSettings` zieht nach `config/services.py`; `COLOR_INDICES`/`parse_color`
  in das Blattmodul `ma2pi/palette.py`; `led_output` importiert und
  re-exportiert sie (`from .config import LedSettings` bleibt gültig für
  Bestandscode/Tests).
- `ValueAccelerationSettings` zieht in `config/mapping/model.py`;
  `acceleration.py` importiert/re-exportiert.
- `PALETTE`/`PALETTE_RGB` ziehen in `ma2pi/palette.py` (reine Daten);
  `feedback.py` importiert sie von dort.
- **Querprüfungen mit Laufzeitlogik** (`_check_led_note_owner`,
  `_check_midi_address_space`) wandern nach `config/checks.py`. Sie bleiben
  fachlich in `parse_config` (gleiche Reihenfolge am Ende, gleiche
  `ConfigError.path`-Werte), importieren `feedback`/`midi_remote`/
  `playback_targets` aber nur **innerhalb der Funktion**. Folge: `import
  ma2pi.config` lädt `feedback` nicht mehr; ein Aufruf von `parse_config` lädt
  es weiterhin (unvermeidbar, solange die Prüfung das Zielmodell des Feedbacks
  braucht).
- Der Strukturtest (D8) erzwingt: `ma2pi.config.*` importiert auf **Modulebene**
  nur Stdlib, `ma2pi.hardkeys`, `ma2pi.palette` und sich selbst. Funktions-
  lokale Imports sind nur in `config/checks.py` erlaubt (Whitelist im Test).

*Alternativen:* (a) `build_feedback_targets`/Playback-Auflösung in ein
Blattmodul ziehen – deutlich größerer Umbau, der mit Phase 5 (D10)
zusammenfällt; (b) Lazy-Imports verstreut in `config` belassen – versteckt die
Abhängigkeit. Beides verworfen; `checks.py` macht die Ausnahme sichtbar und
auf zwei Funktionen begrenzt. Sobald D10 die Zielauflösung in
`feedback/targets.py` isoliert, kann `checks.py` darauf umgestellt werden.

### D5: `ma2pi/web/` – Verdrahtung, Middleware, Routen getrennt

```
web/
  __init__.py     Fassade: create_app, API_VERSION, BUS_KEY, … (bisherige Namen)
  app.py          create_app: Application bauen, App-Keys setzen, register_routes
  keys.py         AppKey-Konstanten (CONFIG_KEY, BUS_KEY, …) + neu:
                  STATUS_PROVIDER_KEY, DEVICES_PROVIDER_KEY
  middleware.py   no_cors, host_origin_guard, pin_guard, request_guard
  sessions.py     PinSessions (+ SESSION_TTL, PIN_COOKIE)
  errors.py       json_error, network_error, apply_error, json_body
  deps.py         require_store(request), require_*: einheitlicher 503-Pfad
  routes/
    __init__.py   register_routes(app)
    auth.py  system.py (health/version/status/events)  config.py
    learn.py  device_learn.py  backups.py  network.py  recovery.py  devices.py
    static.py     SPA-Mount
  events.py, serialize.py, devices.py   (unverändert)
```

Handler werden **Modul-Funktionen**, die alles aus `request.app[...]` lesen
(`status_provider`/`devices_provider`/`dist` kommen als zusätzliche App-Keys).
Damit sind sie einzeln importier- und testbar. Der 503-Block „Config-Store
fehlt“ wird zu einer Helferfunktion (`deps.require_store`) mit identischer
Antwort (`503 config_store_unavailable`).

Die Fachlogik von `device_learn_finish` (Bank-Patch berechnen,
Konflikterkennung) zieht in `device_learn.py` (Backend-Modul, nicht Web) als
reine Funktion `build_bank_patch(config, device, bank, captured)`; der Handler
behält nur HTTP-Mapping und Event-Publishing. Fehler werden als
`DeviceLearnError`-Subtypen modelliert, die der Handler auf dieselben
`409`-Codes (`device_learn_stale`, `device_learn_conflict`) abbildet.

*Alternative:* `aiohttp.web.RouteTableDef` mit Dekoratoren. Verworfen: braucht
Modul-globalen Zustand für die Routentabelle; explizites `register(app)` pro
Modul ist testfreundlicher und passt zum bestehenden App-Key-Muster.

### D6: `__main__.py` → CLI-Fassade + Daemon-Module

```
__main__.py     main() – nur CLI-Einstieg; KEIN Re-Export der Unterstrich-Namen
cli.py          Argument-Parser (Flags statt Subcommands) und main-Dispatch
daemon.py       run_daemon(): in build_services() / start_tasks() / shutdown()
                gegliedert; Task-Supervision (_watch/failure) als kleine Klasse
pipeline.py     _process_input, Learn-Loops, Release-für-Learn
led_service.py  _find_led_target, _resolve_led_device_name, _led_step, _led_loop
snapshots.py    _status_snapshot, _device_presence, _activity_event
web_service.py  _start_web (liefert benanntes `WebService`-Dataclass statt
                5-Tupel), recovery_loop
```

`run_dump_input` und `_device_learn_loop`/`_learn_loop` wandern nach `cli.py`
bzw. `pipeline.py` (Learn-Loops).

`run_daemon` bekommt eine benannte Struktur (`Services`-Dataclass: client,
engine, store, learn, device_learn, topology, playback, midi_remote, hid, midi,
feedback, activity, led_holder, web) statt 20 lose Lokalvariablen. Start- und
Shutdown-Reihenfolge (aus dem archivierten `fix-code-review-findings`, Gruppe 3,
Test `tests/test_cli.py::test_run_daemon_shutdown_leaves_no_ma2pi_tasks`) bleiben
erhalten, sie sind Verhalten. „Byte-genau“ wird verifizierbar, indem Task 3.3
die heutige Reihenfolge zuerst als Liste festhält (u. a.: Tasks starten →
`_led`/`feedback` abbrechen und abwarten → LED `close` → `midi_task` →
`playback.cleanup`/`engine.cleanup` → `sleep(0.05)` für Note-Offs →
`midi_remote.close()` → `client.shutdown()` → Web (`recovery`, `network`,
`web_task`, `bus`, `runner`) → `hid.close()`/`midi.close()`) und ein Test sie
mit Aufrufprotokoll gegenprüft.

Die Namen ohne Unterstrich im neuen Modul sind öffentlich innerhalb des
Pakets; `__main__` re-exportiert die alten Unterstrich-Namen **nicht** dauerhaft:
die ~8 Tests werden auf die neuen Importpfade umgestellt (kein
Shim-Altlasten). Patch-Ziele (`_start_web`, `run_dump_input`,
`list_midi_devices`) zeigen danach auf das Modul, das den Namen *nachschlägt*
(Patchen am Verwendungsort, nicht am Definitionsort).

*Alternative:* Re-Exports in `__main__` dauerhaft behalten. Verworfen: Tests, die
`__main__._start_web` patchen, würden stillschweigend wirkungslos, sobald
`run_daemon` das Symbol aus `daemon.py` auflöst – lieber laut umstellen.

### D7: `network` und `ma2_client` als Pakete

```
network/   errors.py, parsing.py (nmcli terse, mask/prefix), models.py
           (InterfaceInfo … ValidationResult), store.py (PendingStore),
           runner.py (Runner, SubprocessRunner), backend.py
           (NetworkManagerBackend), service.py (NetworkService), __init__.py
ma2_client/ errors.py, transport.py (Transport, WebSocketTransport,
           DryRunTransport), auth.py (authenticate, check_connection,
           ConnectionCheck), sendqueue.py (SendQueue, TokenBucket,
           BackpressureGuard), client.py (Ma2Client), __init__.py
```

`NetworkService` (~650 Z.) und `Ma2Client` (~725 Z.) bleiben als Klassen
unverändert in je einem Modul – sie sind kohäsiv; die Auslagerung der Umgebung
bringt sie unter die Obergrenze, ohne die Klasse selbst zu zerlegen. Ist
`NetworkService` danach noch > 600 Z., wird nur der Rollback-/Timer-Teil
(Monotonuhr, Pending-Lifecycle) als Mixin-freie Hilfsklasse
(`rollback.py`) extrahiert – im Task benannt, nicht vorab entschieden.

### D8: Strukturwächter statt Konvention

`tests/test_module_structure.py` (Stdlib `ast`, keine neue Abhängigkeit):

1. **Importrichtung**: für jedes Modul unter `ma2pi/config/` ist die Menge der
   internen Importziele **auf Modulebene** ⊆ {`ma2pi.config.*`,
   `ma2pi.hardkeys`, `ma2pi.palette`}. Funktionslokale Imports sind nur in
   `ma2pi/config/checks.py` erlaubt und dort auf eine Whitelist
   (`feedback`, `midi_remote`, `playback_targets`) beschränkt.
2. **Zeilenobergrenze**: kein Modul unter `ma2pi/` über 600 Z.; eine explizite
   Ausnahmeliste (`ALLOWED_LARGE`) mit Begründung pro Eintrag; zunächst
   `midi_input.py` (824), `feedback.py` (1067, bis Phase 5), `mapping.py` (690)
   und `hid_input.py` (651). Neue Ausnahmen brauchen einen sichtbaren
   Diff in dieser Liste.
3. **Fassaden-Vertrag**: `ma2pi.config`, `ma2pi.network`, `ma2pi.ma2_client`,
   `ma2pi.web` exportieren alle Namen aus ihrer jeweiligen `EXPECTED_EXPORTS`-
   Liste (aus dem Stand vor dem Umbau erzeugt).

Dies ist bewusst ein Test und kein OpenSpec-Requirement: es beschreibt keine
vom Nutzer beobachtbare Funktion. Die Entscheidung selbst wird in einer ADR
(`docs/adr/<nächste freie Nummer>-modulstruktur-pakete-mit-stabiler-fassade.md`,
0024 und 0025 sind vergeben, derzeit 0026; die Nummer wird erst beim Anlegen per `ls docs/adr` bestimmt, weil `encoder-mode-led-ui` und `device-profile-files` ebenfalls eine ADR planen; Format wie
`docs/adr/templates/template.md`) festgehalten.

### D9: Umsetzungsreihenfolge und Merge-Strategie

1. **Vorbedingungen** (Stand 2026-11-27):
   - `fix-code-review-findings` und `fix-review-followup-findings` sind
     archiviert; ihre Annahmen (78 geänderte Dateien, Abnahme 7.1) entfallen.
   - Zuerst wird `mapping-device-feature-parity` umgesetzt (Frontend; backend-
     seitig nur Golden-Test 1.5, der nur öffentliche Namen importieren soll).
   - Die LED-/Executor-Changes (`add-per-device-led-protocols`,
     `fix-midicraft-led-output`, `resolve-combined-executors`,
     `add-midi-remote-executors`) sind archiviert; `config.py`, `feedback.py`,
     `__main__.py` und `ma2_client.py` haben dadurch keine offenen Änderer mehr.
     Offen sind `add-device-activity-leds` (6 Tasks, keine Zielmodule),
     `encoder-mode-led-ui` (FieldSpec-Katalog in `config.py`,
     `GET /api/config/schema` in `web/__init__.py`) und `device-profile-files`
     (Loader/Profile). Die beiden Letzteren sind entweder vorher fertig oder
     müssen ihre Dateipfade nach Phase 1 und 2 nachziehen;
     `encoder-mode-led-ui` ist vorab daraufhin zu prüfen, dass der Katalog die
     Parser nicht ersetzt (Regel „Dataclass + Parser nebeneinander“).
   - Der Arbeitsbaum ist für `ma2pi/` und `tests/` sauber (aktuell nur die
     untracked Golden-Test-Dateien von `mapping-device-feature-parity`) und
     `pytest -q` ist grün.
2. Phasen: **config** (höchster Nutzen, niedrigstes Risiko wegen 110 Tests) →
   **web** → **daemon (`__main__`)** → **network/ma2_client** →
   **feedback** (D10). Jede Phase ist ein eigener
   Commit/PR und endet mit grüner Suite.
3. **Reine Verschiebungen zuerst, Umschreibungen danach**: in jeder Phase ein
   Commit „verschieben“ (`git mv`, nur Importe angepasst – Diff ist per
   `git diff -M` als Rename erkennbar) und ein zweiter „zerlegen“ (Riesenfunktionen).
   So bleibt Blame und Review handhabbar.

### D10: `feedback.py` → Paket (Phase 5)

`feedback.py` (1067 Z., 8 Commits) enthält fünf Verantwortlichkeiten:

```
feedback/
  __init__.py   Fassade (bisherige Namen: PALETTE, build_feedback_targets,
                ExecutorFeedback, parse_playbacks, led_notes_by_bank, …)
  encoders.py   LedEncoder, MidicraftEncoder, AslEncoder, encoder_for,
                led_velocity, palette_index, nearest_color
  snapshot.py   ExecutorState, PlaybackSnapshot, parse_playbacks
  targets.py    LedTarget, RequestBlock, resolve_playback_target,
                led_notes_by_bank, build_feedback_targets, build_dark_leds,
                blocks_from_ranges  (nutzt `config/checks.py`)
  service.py    ExecutorFeedback (Takt, Stau, Refresh, Senden), Outbox
```

Die Palette liegt schon seit Phase 1 in `ma2pi/palette.py`. Die LED-Changes, die
`feedback`/`led_output` erweitert haben, sind archiviert; Phase 5 kann daher
direkt nach Phase 1 folgen. Bis dahin steht `feedback.py` in `ALLOWED_LARGE`. Danach stellt
`config/checks.py` seinen Lazy-Import auf `feedback.targets` um, sodass nur noch
die kleine Zielauflösung geladen wird. `tests/test_feedback.py` läuft über die
Fassade und bleibt unverändert; `ExecutorFeedback` und `poller` greifen über die
Fassade zu.

Zwei Punkte aus den archivierten Changes (`add-per-device-led-protocols`,
`resolve-combined-executors`):

- `tests/test_feedback.py` und `tests/test_poller.py` importieren die privaten
  Namen `_belongs_to_block` und `_block_key` aus `ma2pi.feedback`. Die Fassade
  exportiert sie deshalb explizit (oder die beiden Tests stellen den Import auf
  `ma2pi.feedback.targets` um); das gehört in den Fassaden-Test.
- Die Playback-Auflösung existiert zweimal:
  `feedback.resolve_playback_target` (Bank-Layer mit Layer-Key-Ausschluss,
  liefert `(page, executor, kind)`) und `playback_targets.resolve_target`
  (Bank-Offset, `transport`; genutzt von `playback` und `midi_remote_service`),
  dazu der Frontend-Resolver aus `mapping-device-feature-parity`
  (`web/src/lib/assignment.ts`, abgesichert durch `tests/test_assignment_golden.py`).
  Die Backend-Duplikate werden in diesem Change **nicht** vereinheitlicht, weil
  das Verhalten berührt (Layer-Key-Ausschluss, Offset-Regeln). Phase 5 hält sie
  nur sauber getrennt (`feedback/targets.py` vs. `playback_targets.py`) und der
  Golden-Test deckt beide Seiten; eine Zusammenführung ist ein eigener Change.

## Risks / Trade-offs

- **[Risiko] Reihenfolge der Validierung ändert sich unbemerkt** → Beim
  Zerlegen von `_parse_profiles`/`_parse_mapping` die Aufrufreihenfolge der
  Teilparser exakt wie bisher; vor Phase 1 zusätzlich einen
  Golden-Test anlegen: `config.toml` einlesen und `redacted_config()` als
  JSON-Snapshot vergleichen, plus eine Tabelle „fehlerhafte Mini-Configs →
  erwartete `ConfigError.path`“ aus den Bestandstests.
- **[Risiko] Zirkuläre Importe nach dem Umzug der Typen** → Strukturtest D8.1
  und ein `python -c "import ma2pi.config"` mit `-X importtime` als
  Verifikationsschritt (darf `ma2pi.feedback` nicht mehr laden; `parse_config`
  darf es per `checks.py` nachladen).
- **[Risiko] `monkeypatch` wirkt stillschweigend nicht mehr** (Patch auf altem
  Modul) → Tests in `test_cli.py`/`test_led_output.py` gezielt prüfen: jeder Patch
  muss mit `raising=True` (Standard) scheitern, wenn das Ziel fehlt; zusätzlich
  Test, dass der gepatchte Pfad im Lauf aufgerufen wird.
- **[Risiko] Hardware-Pfade ohne Testabdeckung** (`RealMidiHandle`, evdev,
  `nmcli`) → werden **nicht** angefasst (nur `network.py` wird verschoben, das
  über `Runner` bereits mockbar ist). Nach Phase 4 ein Smoke-Lauf auf dem
  Pi gemäß `docs/hardware-smoke-*.log`.
- **[Risiko] Deploy**: `deploy/install.sh` kopiert den Code; neue Pakete
  brauchen `__init__.py` und müssen in `pyproject.toml` auftauchen: dort steht
  heute eine **explizite** Liste `packages = ["ma2pi", "ma2pi.web"]`; neue
  Unterpakete (`ma2pi.config`, `ma2pi.config.profiles`, `ma2pi.web.routes`, …)
  fehlen sonst bei `pip install .`. (`deploy/install.sh` nutzt `cp -a` und ist
  davon nicht betroffen; Umstellung auf `packages.find` ist die robustere Wahl) → Task prüft `pip install .` in einem frischen venv und
  `python -m ma2pi --help`; der Strukturtest vergleicht zusätzlich die
  Paketliste mit den tatsächlichen Verzeichnissen.
- **[Trade-off] Mehr Dateien, mehr Navigation** → bewusst akzeptiert; Regel
  „Dataclass und Parser nebeneinander“ hält die Wege kurz. Fassade verhindert,
  dass Aufrufer die Struktur kennen müssen.
- **[Trade-off] Stabilität vs. Aufräumen**: Das Projekt hat gerade eine
  Hardware-Verifikationsphase hinter sich. Ein reiner Struktur-Change ist
  riskant, wenn gleichzeitig Features landen – daher D9.1.

## Open Questions

- **`config.toml` ist 2657 Zeilen / 65 KB.** Ursache ist nicht Struktur-, sondern
  Datenredundanz: sechs MIDICRAFT-Profile (`enc`, `push`, `turn`, `spot`,
  `mix`, `fade`) mit je 25–30 fast identischen `[[controls]]`-Tabellen
  (~170 Zeilen je Profil), je 16 Bank-Tabellen (davon 15 mit `notes = {}`)
  und je einem ~40-zeiligen Layout mit demselben Raster. Das ist ein
  Format-/Schema-Thema (z. B. Profil-Templates oder `[[profiles.x.banks]]`-
  Defaults „Bank n → Kanal n, leer“, Controls aus Muster generieren) und
  berührt `ConfigStore`/`tomlkit`-Patching, die UI und ADR-0006. Es gehört in
  einen **eigenen Change** (`device-profile-files`, Entwurf liegt vor) und wird
  hier nicht entschieden. Dieser Change erleichtert ihn, weil `profiles/` dann ein
  klarer Ort ist.
- Beobachtungsliste: `midi_input.py` (824 Z.: rawmidi-ioctl, Parser, Manager),
  `mapping.py` (690 Z.) und `hid_input.py` (651 Z.). Sie liegen über der
  600-Z.-Grenze; der Strukturtest führt sie zunächst in `ALLOWED_LARGE`. Ob sie
  gesplittet werden, entscheidet sich nach Abschluss der Feature-Changes und
  ändert weder Specs noch diesen Task-Plan. `feedback.py` ist nicht mehr hier,
  sondern Phase 5 (D10).
