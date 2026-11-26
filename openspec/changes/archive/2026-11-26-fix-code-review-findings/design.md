# Design

## Context

Das Repository umfasst den Python-`asyncio`-Daemon (`ma2pi/`), die eingebettete
`aiohttp`-API (`ma2pi/web/`) und die Svelte-5-Oberfläche (`web/src/`). Durch das
schnelle Wachstum um Geräteflächen, Bänke, geführtes Anlernen, Wertbeschleunigung,
LED-Feedback, Netzwerk-/Recovery-Verwaltung und Aktivitätsmonitor sind an den
Schnittstellen zwischen Modulen mehrere systematische Brüche entstanden. Dieser
Change bündelt alle Korrekturen aus dem Gesamt-Review **und übernimmt alle
sinnvollen Entscheidungen, Randfälle und Testkriterien aus dem aufgelösten
Change `harden-runtime-lifecycle`** (angepasst dort, wo der neue gemeinsame
Raw-MIDI-Pfad das direkte Öffnen eines zweiten LED-FDs ablöst).

## Goals / Non-Goals

**Goals:**

- **Symmetrischer API-Vertrag**: `GET /api/config` liefert dieselbe Struktur,
  die `PUT /api/config` (RFC 7386 Merge-Patch auf `config.toml`) erwartet — ohne
  Datenverlust bei Bänken, Encodern, Union-Typen oder Layouts.
- **Blockadefreie & fehlertolerante Hardware-Schicht**: Genau ein
  nichtblockierendes Raw-MIDI-Handle je Gerät, kein Event-Loop-Deadlock bei
  USB-Replug, kein CPU-Spin bei Disconnect und kein Boot-Crash-Loop bei
  `ProfileError`.
- **Unterbrechungsfreier Show-Betrieb**: Jede Laufzeit-Konfigurationsänderung
  wirkt in allen Hilfsdiensten ohne Neustart; kein Zombie-Task oder Zombie-Socket
  überlebt Shutdown oder Überlauf; kein Input-Freeze während laufender
  Verbindungstests; keine verlorenen Releases, keine dauerhaft verschluckten
  Eingaben durch Learn-Modi und keine hängenden oder verfrüht freigegebenen
  Tasten über Geräte- oder Bankgrenzen hinweg.
- **Robuste Zeit-, Verbindungs- und Web-Sicherheit im Show-LAN**: Monotone
  Timer, sauberes Schließen verworfener Transports/WebSockets, serverseitige
  PIN-Sessions mit Brute-Force-Sperre und Schutz vor DNS-Rebinding sowie
  `password_file`-Exfiltration.

**Non-Goals:**

- **Kein Internet-Bedrohungsmodell**: `bind = "0.0.0.0"`, `pin_enabled = false`
  als Default und das im UI lesbare Rettungs-WLAN-Passwort bleiben gemäß
  ADR-0013 und ADR-0018 unverändert.
- **Kein PIN-Hashing in `config.toml`** und keine pro-IP-Sperrtabelle (siehe D6).
- **Kein Umbau zu einem gemeinsamen Tab-Store** (bleibt Aufgabe von
  `mapping-device-feature-parity`, das auf diesem bereinigten API-Vertrag
  aufsetzt).
- **Kein `presetTypes`-Dauer-Polling**: Gemäß `encoder-control` bleibt es bei
  ereignis-/bedarfsgetriebener Abfrage.

## Decisions

### D1: Kanonischer TOML-Serializer statt `dataclasses.asdict()` (`ma2pi/web/serialize.py`, `config_store.py`)

`redacted_config(config)` wird von `asdict(config)` auf eine explizite
Serialisierungsfunktion `serialize_config(config)` umgestellt, deren Schlüssel
1:1 dem von `parse_config()` gelesenen TOML-Schema entsprechen:

- `mapping.device_banks[device]` enthält `bank_size` und direkt die Bank-Schlüssel
  `"1"`, `"2"`, … (ohne Zwischen-Schlüssel `"banks"`), wobei `encoders` je Bank
  als sortierte Liste `[{"id": 1, "slot": 1}]` (nur aktives Feld, ohne
  `"attribute": None`) ausgegeben wird.
- `mapping.encoders`, `mapping.keys`, `mapping.modifiers` und `mapping.playbacks`
  enthalten ausschließlich die für die jeweilige Variante gültigen Felder (keine
  `None`-Schlüssel).
- `mapping.encoder_acceleration` und `mapping.encoder_resolution` (mit
  verschachteltem `modifiers = {"fine": ..., "ultra": ..., "cycle": ...}`),
  `profiles.<id>.led_feedback.led_notes` sowie `layouts` geschlüsselt nach dem
  Layout-Tabellennamen (mit `profile = ...`) entsprechen exakt der TOML-Form.
- Geheimnisse bleiben wie bisher entfernt (`ma2.password_set`, `web.pin_set`).
- In `ConfigStore._clean_patch()` werden vom Client gesendete Felder
  `ma2.password_file` und `ma2.password_env` **immer** verworfen (nur intern
  gesetzt, wenn `password` übergeben wurde). `_apply_patch_to_table()` entfernt
  rekursiv `None`-Werte auch aus Dicts innerhalb von Listen, und `prepare_patch()`
  verifiziert das serialisierte `tomlkit`-Dokument per `tomllib.loads` +
  `validate`, bevor `PreparedConfig` zurückkehrt.

### D2: Gemeinsamer Raw-MIDI-Pfad für `LedOutput` & `ExecutorFeedback` (`midi_input.py`, `led_output.py`, `__main__.py`)

ALSA `rawmidi` erlaubt pro Richtung nur einen Substream-Öffner. Statt
`LedOutput` wie noch in `harden-runtime-lifecycle` einen eigenen Dateideskriptor
mit blockierendem `os.open(O_WRONLY)` öffnen zu lassen (was bei USB-Replug mit
`MidiManager` um den Ausgabesubstream konkurriert und den Event-Loop in
`snd_rawmidi_open` deadlocken kann):

- `LedOutput` erhält im Daemon einen Schreib-Adapter auf
  `MidiManager.send(device, data)` (kompatibel mit `add-per-device-led-protocols`,
  das für `[led]` und `asl-mk2`-Feedback ebenfalls einen gemeinsamen Ausgabeweg
  fordert; ein optionales Standalone-Handle für Einzeltests nutzt zwingend
  `O_WRONLY | O_NONBLOCK` + `rawmidi_drop_output` vor `close`).
- `_find_led_target` prüft ausschließlich konfigurierte MIDI-Geräte und fällt
  niemals auf `infos[0]` (fremde MIDI-Geräte) zurück.
- `RealMidiHandle._on_readable` ruft bei `OSError` (außer `BlockingIOError`) und
  EOF (`b""`) sofort `self._loop.remove_reader(self._fd)` auf; `__init__`
  schließt `self._fd`, falls `add_reader` fehlschlägt.
- `RealMidiHandle.write` prüft bei bekannter Puffergröße, ob mindestens
  `len(data)` Bytes frei sind, damit 3-Byte-MIDI-Frames nie durch Teil-Writes
  zerrissen werden; `rawmidi_output_free` fällt bei `ENOTTY`/`EINVAL` auf eine
  64-Bit-`time64`-Strukturdefinition zurück (32-Bit Raspberry Pi OS).
- `HidManager.reconcile` und `MidiManager.reconcile` fangen `ProfileError` je
  Gerät ab und gehen in `_schedule_retry`, statt den Daemon zu beenden;
  `HidManager._decoders` wird bei `set_config` und `_close_device` geleert;
  `select_devices` und `select_midi_devices` schließen bereits vergebene
  `info.path`-Knoten aus.

### D3: Lifecycle, EventBus-Überlauf, Hot-Reload, Pre-Freeze-Apply & Backups (`__main__.py`, `web/events.py`, `runtime.py`, `config_store.py`, `logging_setup.py`)

Integriert D1–D3 und D6 aus `harden-runtime-lifecycle` vollständig:

- **Shutdown vor `engine.cleanup()`**: `run_daemon()` bricht im `finally` auch
  `device_learn_task` wie `learn_task` **vor `engine.cleanup()`** ab und erwartet
  ihn mit `contextlib.suppress(CancelledError, Exception)`; außerdem schließt
  der Shutdown alle offenen `EventBus`-Verbindungen.
- **EventBus-Überlauf als Signal statt Sentinel**: Ein Sentinel in der Queue
  scheitert bei `QueueFull`, weil die Queue voll ist. Stattdessen hält `EventBus`
  je Subscriber ein `dropped: asyncio.Event`. Bei `QueueFull` (oder gezieltem
  Trennen nach Logout / PIN-Wechsel / Restore) setzt `publish()` das Event und
  entfernt den Subscriber; `events_handler` wartet auf Nachricht oder `dropped`
  und schließt den WebSocket aktiv (ohne pro Nachricht unnötige Tasks liegen zu
  lassen). Für direkte Queue-Nutzer bleibt das bisherige Verhalten
  (`subscriber_count` sinkt, bereits eingereihte Events bleiben lesbar,
  `test_events_slow_client_is_dropped`) erhalten; der getrennte Browser-Client
  reconnectet mit Backoff und erhält den Anfangsstand über `/api/status` bzw.
  Initial-Snapshot.
- **Hilfsdienste über Activate-Hooks & testbarer `_led_step`**:
  `LearnManager.set_config`, `DeviceLearnManager.set_config` (die redundante
  Poll-Zeile in `_device_learn_loop` entfällt) und das Setzen des Root-Log-Levels
  (`logging.level`) hängen als Activate-Hooks am `ConfigStore`; `Ma2Client` liest
  `keepalive_interval` dynamisch je Zyklus. Die LED-Nachführung wird in einen
  reinen, ohne Hardware testbaren Schritt `_led_step(config, client, midi, state)`
  und eine immer laufende 2-s-Schleife getrennt:
  - `led.enabled = false` und aktiv → sendet `DISABLE` über `MidiManager`,
    ruft `client.set_led(None)`.
  - Aktiv, aber `config.led` geändert oder MIDI-Handle neu geöffnet
    (neue Generation) → `LedOutput` mit neuen Einstellungen binden und aktuellen
    Modus + Ruhezustände setzen.
  - `led.enabled = true`, Gerät noch nicht offen → kostengünstiger No-Op bis zum
    Erscheinen des Geräts.
- **Pre-Freeze-Apply & Release-Drain**: Unter `ConfigStore._lock` laufen
  `prepare_patch()` und `_test_credentials()` **vor** `engine.freeze()`. Erst
  nach bestandenem Test frieren `MappingEngine` *und* `PlaybackRouter` ein,
  geben alle gehaltenen Hardkeys, Encoder-Klicks und Playback-Buttons in die
  `SendQueue` frei und flushen diese nach bestem Bemühen unter der alten
  Konfiguration, bevor `client.apply_config()` bzw. `client.reconnect()` läuft.
- **Pfad-, Zahlen-, Backup- & Log-Hygiene**: `_float()` prüft `math.isfinite()`;
  `_require_hardkey_codes()` prüft auch `mapping.device_banks`; `ConfigPaths`
  stützt benutzerdefinierte `--config`-Dateinamen und migriert beim Start von
  `/etc/ma2pi/config.toml` automatisch; `write_password()` rollt bei
  `commit_prepared()`-Fehler zurück; `last-good.toml` wird atomar geschrieben;
  `rotate_backups()` sortiert gleichsekündige Backups chronologisch; die
  Log-Redaction maskiert auch gequotete Dict-/JSON-Schlüssel, `pin`, `psk`,
  `wifi-sec.psk`, `token` und Exception-Tracebacks.

### D4: Mehrgeräte- & Bank-Konsistenz in Engine, Playback, Beschleunigung & Feedback (`mapping.py`, `playback.py`, `acceleration.py`, `feedback.py`, `activity.py`)

Übernimmt D4 aus `harden-runtime-lifecycle` an der Wurzel und ergänzt Bank- und
Feedback-Konsistenz:

- **Held-Keys je `(device, control)` + Konsolen-Referenzzähler**:
  `_held`, `_press_targets` und `_pending_hold` werden nach `(device, control)`
  geschlüsselt (Doppel-Press desselben Geräts bleibt ignoriert; zwei Geräte mit
  gleichem Control-Namen stören einander nicht). Da zwei Geräte auf denselben
  Hardkey oder Encoder-Klick zeigen können, zählt die Engine aktive Halter je
  Konsolen-Ziel: Press-Frame bei `0 → 1`, Release-Frame erst bei `1 → 0`,
  LUA-Hold-Upgrade höchstens einmal je Konsolen-Taste. Aufräumpfade
  (`release_device`, `cleanup`, `on_connection_lost`, Apply) arbeiten je Eintrag,
  senden aber je Konsolen-Taste höchstens ein Release in umgekehrter
  Press-Reihenfolge und hinterlassen leere Zähler. Modifier wirken
  gerätübergreifend („von mindestens einem Gerät gehalten“); `modifier_hook`
  meldet beim ersten Halter „gedrückt“, beim letzten (auch in Aufräumpfaden)
  „losgelassen“. Die Introspektion `engine.held` liefert `(device, control)`-Tupel.
- **`PlaybackRouter` Press-Zielbindung & Reconnect**: `_pressed` speichert je
  `(device, control)` das beim Press aufgelöste `(page, executor, button)`-Ziel.
  Release, `DeviceLost` und `cleanup` geben genau dieses Ziel frei (auch nach
  Bankwechsel) und reichen ein Release an `MappingEngine` durch, wenn das Control
  dort gehalten wird. Ein `connection_lost`-Callback leert `_pressed`,
  `_last_bank` und `_last_value`.
- **Gebankte `relative-encoder`**: Gebankte MIDI-Profile dürfen Controls mit
  `kind = "relative-encoder"` über `[mapping.encoders]` und `device_banks`
  abbilden.
- **`ValueAccelerator`**: Zustände je `(device, bank, control)`, kein Sprung auf
  `0.0`/`1.0` bei langsamer Rückdrehung aus einem inneren virtuellen Wert, und
  deutsche `DEBUG`-Protokollierung statt `INFO` (`DEBUGACCEL` entfällt).
- **`ExecutorFeedback` & `activity.describe_frame`**: Handle-Generationen je
  Gerät erkennen Replugs auf denselben `/dev/snd/midiC*D*`-Pfad und setzen nur
  das betroffene Gerät zurück; `_output_stalled` prüft echten Abnahmestillstand;
  leere `playbacks`-Antworten schalten auf `off`; Bank-Kanal, `device_banks` und
  Bank-Offset fließen in die Ziele ein; `describe_frame` wertet `pageIndex`,
  `execIndex`, `buttonId`, `name` und `hardkeyPress`/`hardkeyRelease` aus.

### D5: MA2-Verbindung, onPC-Auflösung, Learn-Schutz & Netzwerk-Timer (`ma2_client.py`, `encoder_page.py`, `learn.py`, `device_learn.py`, `network.py`, `recovery.py`)

- **`Ma2Client`**: `_handle_disconnect()` und der Fehlerpfad von `authenticate()`
  schließen `self._transport` immer (`close_timeout = 2.0 s`); Gesamt-Timeout
  `ma2.login_timeout` über den gesamten Handshake; WebSocket-Pings erkennen
  halboffene Verbindungen; `PlaybacksRequest` läuft koalesziert in einer vierten
  Queue niedrigster Priorität und `BackpressureGuard` prüft realen
  Socket-Schreibpuffer-Stau.
- **`EncoderResolution` & Tasten-LEDs**: Bedarfsweises `presetTypes`-Update vor
  dem Auflösungswechsel (ohne Dauer-Polling), Reset von `_page`/`_page_task` bei
  Disconnect, Zurücksetzen alter `"s"`-Flags auf Geschwistern in
  `EncoderPage._merge_by()` und `set_mode_color()` statt `apply_mode()` bei
  `ToggleScreenMode`.
- **Learn-Modi**: `LearnManager` begrenzt `awaiting_release` auf max. 2 s,
  fixiert `session.control` beim ersten Encoder-Detent und löst gebankte Noten
  auf; `DeviceLearnManager` verlangt Velocity `>= 2` für Buttons, ignoriert
  unmittelbare Folge-Frames derselben Note, publiziert `device_learn`-Events,
  beendet verwaiste pausierte Sitzungen nach Inaktivitätsfrist und gibt beim
  Start gehaltene Tasten frei.
- **`NetworkService` & `RecoveryService`**: `time.monotonic()` mit Warteschleife
  für Rollback- und Karenz-Timer; strikte Gateway-/DNS-Prüfung; strikte Typen,
  UTF-8-Bytelänge (`1..32`), WPA2-ASCII (`8..63`), Fehler-Rollback und Locking in
  `RecoveryService`.

### D6: `PinSessions`, DNS-Rebinding-Schutz & Svelte-5-Korrekturen (`web/__init__.py`, `web/src/**`, `deploy/`)

Übernimmt D5 (Option A mit festem 12-h-Ablauf) aus `harden-runtime-lifecycle`:

- **`PinSessions` mit festem Ablauf und wachsender Sperre**:
  - Feste Konstanten ohne neue Config-Schlüssel (Option A; kein gleitender
    Ablauf, globale Sperre im kleinen Show-Netz statt fehleranfälliger
    IP-Tabelle hinter NAT/Proxy).
  - `SESSION_TTL = 12 h` serverseitig erzwungen (passend zum Cookie-`max_age`),
    injizierbare Uhr (`time.monotonic`) für wartefreie Tests.
  - Serialisierte Prüfung unter `asyncio.Lock` mit längenunabhängigem
    UTF-8-Digest-Vergleich. Ab 5 aufeinanderfolgenden Fehlversuchen greift eine
    Sperre von `15 s`, die sich nach Ablauf mit jedem weiteren Fehlversuch
    verdoppelt (`30 s`, `60 s`, `120 s`, `240 s`, Obergrenze `300 s`). Während
    aktiver Sperre antwortet `/api/auth/login` mit `429 pin_locked` und
    `Retry-After` (auch für eine richtige PIN), **ohne den Fehlversuchszähler
    währenddessen weiter hochzuzählen**; eine richtige PIN nach Sperrende setzt
    den Zähler auf `0` zurück. Bestehende angemeldete Sessions bleiben von einer
    Login-Sperre unberührt.
  - Logout, PIN-Wechsel in `PUT /api/config` und ein Backup-Restore mit
    abweichender PIN widerrufen Sessions und schließen betroffene
    `/api/events`-WebSockets; `learn_start` nutzt `_json_body()`.
- **DNS-Rebinding- & Origin-Guard**: `Host` erlaubt IP-Literale, `localhost`,
  `.local` und den lokalen System-Hostnamen; `Origin` muss bei Schreibzugriffen
  und `/api/events` zum `Host` passen.
- **Svelte-5-Oberfläche & Deploy**: Vollständige Merge-Patches mit `null`-Feldern,
  `controls.inventory`/`banks` im Mapping-Tab, Update von `original*` nach
  `save()`, `Screen-Encoder` als `<select>` (`Keiner` + `5..10`, Slot `1..4`),
  Bewahren geerbter Bank-Offsets + „Belegung löschen“, reaktive Props ohne
  Compilerwarnungen, natives `<dialog>`, Learn-Abbruch/Cleanup, reaktiver
  Auth-Store + `PinGate`-Anzeige für `429 pin_locked`, Kontrast auf `"black"`,
  `.error` + `role="alert"` für Recovery, `DEFAULT_DIST`-Fallback und
  `root:root`-Ownership für `/opt/ma2pi/app` und `.venv`.

## Risks / Trade-offs

- **[Zähler für geteilte Konsolen-Tasten ist sicherheitsrelevant]** → Ein
  gemeinsamer Aufräumpfad gibt bei Geräteverlust, Verbindungsverlust, Apply und
  Shutdown garantiert frei und leert alle Zähler; Tests prüfen `engine.held == {}`
  und leere Halter-Zähler nach jedem Pfad.
- **[Globale PIN-Sperre und fester 12-h-Ablauf]** → Bewusst gemäß
  `harden-runtime-lifecycle` akzeptiert: Angemeldete Konsolen laufen während
  einer Sperre weiter, und `Retry-After` nennt die Restzeit klar; sollte in der
  Praxis Konfigurierbarkeit nötig werden, lassen sich die Konstanten später
  verlustfrei als Config-Felder herausziehen.
- **[Geänderte JSON-Form von `GET /api/config`]** → Durch Contract-Tests zwischen
  `serialize_config()`, Frontend-Patches und `ConfigStore.prepare_patch()` im
  selben Repo abgesichert.

## Migration Plan

Keine Konfigurationsmigration bestehender `config.toml`-Dateien erforderlich
(Legacy-`/etc/ma2pi/config.toml` migriert beim Start automatisch). Sessions und
Sperrzähler liegen ausschließlich im Speicher; Rollback jederzeit per Git-Revert.
