# Proposal

## Why

Zwei aufeinanderfolgende Code-Reviews des gesamten Repositories (einschließlich
aller Punkte aus dem bisherigen Change `harden-runtime-lifecycle`) haben über
Backend, Hardware-I/O, Laufzeit-Apply, Netzwerk/Recovery und Svelte-5-Oberfläche
hinweg kritische und hohe Fehler offengelegt:

- **API-/Schema-Bruch & Datenverlust im UI**: `GET /api/config` gibt rohes
  `dataclasses.asdict()` statt der TOML-Struktur aus (`device_banks.banks`,
  `attribute: null` in Encoder-Listen, abweichende Schlüsselnamen). Dadurch
  verschwinden Bank-Belegungen und `ma_page` nach dem Neuladen aus der
  Geräteansicht, Speichern überschreibt bestehende Bank-Overrides oder bricht
  mit HTTP `422`/`500` ab, Typwechsel im Mapping-Tab scheitern am RFC-7386-Merge
  und gebankte MIDICRAFT-Controls (inkl. `accelerated`) fehlen im Mapping-Tab.
- **Raw-MIDI-Deadlock & Crash-Loop**: `LedOutput` und `MidiManager` öffnen
  denselben ALSA-`rawmidi`-Knoten getrennt; bei USB-Replug blockiert
  `os.open(..., O_WRONLY)` ohne `O_NONBLOCK` im Event-Loop dauerhaft. Ein
  ungefangener `ProfileError` in `reconcile()` stürzt den Daemon nach einem
  Hot-Reload in eine permanente `systemd`-Restart-Schleife; ein fehlendes
  `remove_reader()` erzeugt beim Abziehen von USB-MIDI 100 % CPU-Last.
- **Lifecycle, Hot-Reload, Freeze & Tasten-Zustände**: `device_learn_task` läuft
  nach Shutdown weiter; `EventBus` lässt langsame Clients als Zombie-WebSockets
  offen; `LearnManager`, `[led]` und Log-Level folgen Konfigurationsänderungen
  nicht zur Laufzeit; `ConfigStore.apply()` friert Eingaben schon *vor* dem
  10–40 s langen Verbindungstest ein und verwirft `Release`-Frames;
  `MappingEngine` führt gehaltene Tasten nur nach Control-Name statt je Gerät;
  `PlaybackRouter` verliert das Press-Ziel über Bankwechsel; `LearnManager` und
  `DeviceLearnManager` können Live-Eingaben dauerhaft verschlucken.
- **Verbindung, Feedback, Zeitbasis & Web-Schicht**: Fehlgeschlagene MA2-Logins
  leaken WebSockets; `EncoderResolution` arbeitet auf veralteten `presetTypes`;
  `ExecutorFeedback` übersieht Replugs auf denselben `/dev/snd/midiC*D*`-Pfad,
  meldet Fehlalarme bei Dauer-Updates und ignoriert Bank-Kanäle; `NetworkService`
  und `RecoveryService` messen Fristen mit `time.time()` statt `time.monotonic()`;
  `PUT /api/config` erlaubt `ma2.password_file`/`password_env`, `POST /api/learn/start`
  wirft `500` bei Nicht-Objekt-JSON, PIN-Sessions laufen serverseitig nie ab und
  sind parallel brute-forcebar, `Host`/`Origin` werden nicht gegen DNS-Rebinding
  geprüft und die Log-Redaction übersieht Dict-/JSON-Schlüssel.

Bewusst **unverändert** bleibt die Auslegung für geschützte Show-Netze
(ADR-0013 / ADR-0018): `bind = "0.0.0.0"`, `pin_enabled = false` als Default
und das im UI sichtbare Rettungs-WLAN-Passwort sind gewollt.

Dieser Change **übernimmt alle sinnvollen Punkte aus `harden-runtime-lifecycle`
und ersetzt ihn vollständig** (der separate Change `harden-runtime-lifecycle` ist
gelöscht).

## What Changes

- **Kanonische Config-Serialisierung & sicheres Patching**: `GET /api/config`
  liefert exakt die TOML-konforme Struktur ohne `None`-Union-Felder;
  `ConfigStore` verwirft `ma2.password_file`/`password_env` aus API-Patches,
  bereinigt `None` in Listen, prüft `NaN`/`inf`, validiert Bank-Hardkeys,
  testet Zugangsdaten *vor* `engine.freeze()`, flusht `Release`-Frames vor
  Session-Wechsel und korrigiert Backup-Rotation, Passwort-Rollback und
  Pfad-Migration.
- **Einheitlicher Raw-MIDI-Pfad & fehlertolerantes Hotplug**: `LedOutput`
  schreibt über `MidiManager` statt über einen zweiten blockierenden FD (kein
  `infos[0]`-Fremdgeräte-Fallback); `RealMidiHandle` meldet Reader sofort bei
  `OSError`/EOF ab, verhindert Teil-Writes und unterstützt 64-Bit-`time64`-ioctls;
  `reconcile()` fängt `ProfileError` je Gerät ab, bereinigt Decoder-Caches und
  vergibt Geräteknoten eindeutig.
- **Lifecycle, Hot-Reload, Event-Stream & Web-Härtung (inkl. `harden-runtime-lifecycle`)**:
  Geordneter Shutdown aller Tasks inkl. `device_learn_task` vor `engine.cleanup()`;
  `EventBus` schließt überlaufende sowie abgemeldete WebSockets per
  `dropped`-Signal (kompatibel für direkte Queue-Nutzer); Activate-Hooks und
  `_led_step` aktualisieren Learn, Device-Learn, ASL-LED, Log-Level und Keepalive
  ohne Neustart; `PinSessions` erzwingt festen 12-h-Ablauf und wachsende Sperre
  (`429 pin_locked` + `Retry-After`) unter Lock; `learn_start` prüft JSON-Objekt
  (`400 invalid_json`); `Host`-/`Origin`-Prüfung verhindert DNS-Rebinding;
  `RedactionFilter` schwärzt JSON/Dicts, `pin`/`psk`/`token` und Tracebacks.
- **Mehrgeräte- & Bank-Konsistenz in Engine, Playback, Beschleunigung & Feedback**:
  Held-Keys nach `(device, control)` mit Referenz-Zählung je Konsolen-Taste
  (inkl. einmaligem Hold-Upgrade und gerätübergreifenden Modifiern);
  `PlaybackRouter` bindet gehaltene Buttons an das Press-Ziel, gibt bei
  `DeviceLost` frei und synchronisiert nach Reconnect neu; gebankte
  `relative-encoder` sind mappbar; `ValueAccelerator` trennt nach
  `(device, bank, control)`, vermeidet Endanschlag-Sprünge und loggt nur auf
  `DEBUG`; `ExecutorFeedback` erkennt Replugs über Handle-Generationen, prüft
  echten Puffer-Fortschritt und berücksichtigt Bank-Kanäle/`device_banks`;
  `activity.describe_frame` liest die echten onPC-Frame-Felder.
- **MA2-Verbindung, onPC-Auflösung, Learn-Timeouts & monotone Netzwerk-Timer**:
  Kein WebSocket-Leak bei Login-Fehlern, begrenzte Handshake-/Shutdown-Timeouts
  und Peer-Liveness, faire Queue-Priorität für `PlaybacksRequest`; bedarfsweise
  `presetTypes`-Aktualisierung beim Auflösungswechsel ohne Dauer-Polling;
  begrenzte Release-/Inaktivitäts-Timeouts in beiden Learn-Modi; `time.monotonic()`
  und atomare Fehlerbehandlung in `NetworkService` und `RecoveryService`.
- **Sofort-Fixes im Svelte-5-UI, Deploy & Contract-Tests**: Korrekte
  Merge-Patches, Inventar-Unterstützung, `AssignDialog`-Validierung/`<dialog>`,
  Learn-Abbruch/Cleanup, reaktiver Auth-Status + `429`-Anzeige in `PinGate`,
  Kontrast/A11y, `DEFAULT_DIST`-Fallback, `root:root`-Code-Ownership in
  `install.sh` sowie Contract-Tests gegen `redacted_config()` + `prepare_patch()`.
- **BREAKING**: keine für gültige `config.toml`-Dateien. `GET /api/config`
  wechselt von internen Dataclass-Feldnamen auf die kanonische TOML-Struktur.

## Capabilities

### New Capabilities

Keine.

### Modified Capabilities

- `config-ui`: Kanonische Config-Serialisierung, DNS-Rebinding-Schutz,
  Event-Stream-Überlauf & Reconnect, `PinSessions` mit TTL/Sperre,
  JSON-Body-Prüfung, Learn-Release-Timeout sowie Editor-/Dialog-/Auth-/A11y-Fixes.
- `hid-input`: Gemeinsamer nichtblockierender MIDI-FD für LED & Feedback,
  sofortiges `remove_reader`, `ProfileError`-Isolierung, Decoder-Reset und
  eindeutige Geräteknoten-Zuweisung.
- `runtime-config`: Pre-Freeze-Verbindungstest, Release-Drain, Activate-Hooks
  aller Hilfsdienste inkl. `[led]`, vollständiger Shutdown, `math.isfinite`,
  Pfad-/Backup-Konsistenz und vollständige Log-Redaction.
- `mapping-engine`: Held-Keys je `(device, control)`, Konsolen-Tasten-Zähler
  inkl. Hold-Upgrade, gerätübergreifende Modifier und gebankte `relative-encoder`.
- `executor-playback`: Press-Zielbindung über Bankwechsel/`DeviceLost`,
  Reconnect-Resync und Beschleunigungszustand je `(device, bank, control)`.
- `value-acceleration`: Zustand je `(device, bank, control)`, sprungfreie
  Bereichsenden und `DEBUG`-Logging.
- `ma2-connection`: Transport-Close im Fehlerpfad, Handshake-/Close-Timeouts,
  Peer-Liveness und niedrige Queue-Priorität für `PlaybacksRequest`.
- `encoder-control`: Bedarfsweise `presetTypes`-Aktualisierung vor
  Auflösungswechsel, korrektes Auswahl-Merge und konsistente ASL-Tasten-LEDs.
- `device-learn`: Schutz vor Prellen/Fader-Folgeframes, Velocity-Schwelle,
  EventBus-Updates und automatisches Sitzungsende nach langer Inaktivität.
- `network-config`: Monotone Rollback-Uhr mit Schleife und strikte
  Gateway-/DNS-Prüfung.
- `recovery-access`: Atomare Validierung/Rollback in `RecoveryService.save`,
  Locking in `auto_cycle` und monotone Karenzzeit.
- `executor-feedback`: Replug-Generationen, Fortschritts-Stauprüfung, leere
  Executor-Blöcke und Bank-Kanal-/`device_banks`-Auflösung.
- `device-activity`: Auswertung der realen onPC-Frame-Schlüssel im Ereignis-Log.

## Impact

- **Backend**: `ma2pi/__main__.py`, `runtime.py`, `config.py`, `config_store.py`,
  `logging_setup.py`, `hid_input.py`, `midi_input.py`, `led_output.py`,
  `ma2_client.py`, `encoder_page.py`, `mapping.py`, `playback.py`,
  `acceleration.py`, `feedback.py`, `learn.py`, `device_learn.py`,
  `activity.py`, `network.py`, `recovery.py`, `screen_helper.py`,
  `web/__init__.py`, `web/events.py`, `web/devices.py`, `web/serialize.py`.
- **Frontend & Deploy**: `web/src/App.svelte`, `web/src/lib/*.svelte`,
  `web/src/lib/status.ts`, `web/src/lib/api.ts`, `deploy/*`, `docs/api.md`,
  `README.md`.
- **Zusammenspiel mit offenen Changes**:
  - `harden-runtime-lifecycle`: vollständig übernommen und gelöscht.
  - `add-sustain-branding` & `add-device-activity-monitor`: bereits fertig,
    vorab archivieren.
  - `add-midicraft-led-feedback`, `fix-midicraft-led-output` &
    `add-per-device-led-protocols`: teilen denselben gemeinsamen `MidiManager`-
    Ausgabeweg (D2) und die Capability `executor-feedback`.
  - `mapping-device-feature-parity`: setzt direkt auf dem kanonischen
    `GET /api/config`-Vertrag (D1) dieses Changes auf.
