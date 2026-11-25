# Design

## Context

Siehe `proposal.md` für Motivation und Scope. Ausgangslage ist ein leeres
Repository; es gibt keine bestehende Implementierung, keine Haupt-Specs und
keine Kompatibilitätslast. Verifiziert sind:

* Die Web-Remote-API unter `ws://<onPC-IP>:80/?ma=1` mit JSON-Frames,
  Session-ID, MD5-Login und Keepalive.
* Der Login-Ablauf aus `ma2apcmini` und dem Chataigne-Modul.
* Hardkey-IDs und der LUA-Wrapper `gma.canbus.hardkey(id, pressed, hold)` aus
  dem Chataigne-Modul.
* Die dynamische Rate-Limiter-Formel aus dem Chataigne-Modul.
* Die Press/Release-Grenze `> 0.9` der Web-Remote-Semantik.

Nicht verifiziert sind das native Wheel-Frame-Format und die Geräteklasse des
ASL MK2 E4B3. Beide werden über eigene Aufgaben und ADR-0002 abgesichert.

## Goals / Non-Goals

**Goals:**

* Ein asyncio-Event-Loop für HID, Mapping, Queue und WebSocket.
* Deterministische Press/Release-Reihenfolge inklusive Modifier-Kombis.
* Verlustfreie Encoder-Deltas trotz harter globaler Rate-Begrenzung.
* Ein Konfigurationsschema, das Geräteprofile, Mapping und Geheimnisse trennt.
* Ohne Hardware testbare Module durch injizierbare Event-Quellen und einen
  Mock-Server.
* Deployment ohne Root, PEP-668-konform und mit systemd-Hardening.

**Non-Goals:**

* Parameter-Unlock oder zusätzliche Parameterkanäle.
* LED-, Motor- oder Fader-Feedback.
* Grafische Oberfläche, Web-Dashboard oder Hot-Reload der Konfiguration.
* MIDI-, OSC-, Telnet- oder Showcockpit-Transport.
* Unterstützung anderer Betriebssysteme als Raspberry Pi OS Trixie/Debian 13.

## Decisions

### Modulzuschnitt und Datenfluss

```
/dev/input/event* ──► hid_input.py ──┐
                                     ├──► asyncio.Queue[InputEvent]
/dev/snd/midiC*   ──► midi_input.py ─┘
                                              │
                                              ▼
                                        mapping.py
                                   (Keys, Modifier, Encoder)
                                              │  Action
                                              ▼
                                        ma2_client.py
                                  (SendQueue + RateLimiter)
                                              │
                                              ▼
                                   ws://<onPC>:80/?ma=1
```

* `hid_input.py` enumeriert evdev-Geräte, wählt Interfaces, liest Events und
  normalisiert auf `InputEvent(kind, control, value, device)`.
* `midi_input.py` enumeriert rohe ALSA-MIDI-Knoten, parst Note-On/Note-Off und
  normalisiert die ASL-Buttons und Encoder-Rastungen auf dieselbe
  `InputEvent`-Schnittstelle.
* `mapping.py` verarbeitet Events strikt sequenziell. Es kennt logische
  Controls, Modifier, Hardkey-/CMD-Aktionen und die Encoder-Akkumulation.
* `ma2_client.py` kennt nur fertige Aktionen (`press`, `release`, `command`,
  `encoder`) und baut daraus Frames. Es verwaltet Session, Queue und Limiter.
* `wheel_protocol.py` enthält ausschließlich die nativen Wheel-Konstanten und
  Builder. `hardkeys.py` enthält den Namens→ID-Katalog. `config.py` lädt und
  validiert TOML. `__main__.py` enthält CLI und Logging-Setup.

Alternative: Mapping direkt in evdev-Callbacks. Verworfen, weil dadurch
Reihenfolge, Backpressure und Testbarkeit an die Geräte-API gekoppelt würden.

### Session-Zustandsmaschine

```
DISCONNECTED ──connect──► CONNECTING ──ws open──► HANDSHAKE
      ▲                        │                     │
      │                     failure               login ok
      │                        ▼                     ▼
      └──── BACKOFF ◄─────── failure ◄──────── AUTHENTICATED
```

Handshake in fester Reihenfolge:

1. WebSocket zu `ws://<host>:<port><path>` öffnen.
2. Auf `{"status":"server ready","appType":"gma2"}` warten.
3. `{"session":0}` senden.
4. `sessionInformation` mit `forceLogin: true` und `session: <id>` empfangen.
5. Login senden:
   `{"requestType":"login","username":"…","password":"<md5>","session":<id>,"maxRequests":1}`.
6. `loginResponse` mit `result: true` abwarten.
7. Keepalive-Task starten: alle `keepalive_interval` Sekunden
   `{"session":<id>}` senden (Default 5 s, hart begrenzt auf < 10 s).
8. Bei Shutdown `{"requestType":"close","session":<id>,"maxRequests":1}` senden.

Der MD5-Hash wird nur im Speicher gehalten und nie geloggt. Ein
`loginResponse` mit `result: false` führt zu einer eindeutigen Fehlermeldung und
einem langen Backoff, nicht zu einer Login-Schleife.

### Hardkey- und Modifier-Semantik

Die Engine führt ein Register `held: dict[str, HeldKey]` mit logischem Namen,
Aktion, Gerät und monotoner Press-Reihenfolge.

* **Press:** Ist der Key bereits im Register, wird nichts gesendet. Sonst wird
  die Aktion ausgeführt (Hardkey-Press, CMD-Frame oder nur lokaler Modifier)
  und der Key mit Ordnungsnummer eingetragen.
* **Release:** Ist der Key nicht im Register, wird nichts gesendet. Sonst wird
  die Release-Aktion ausgeführt und der Eintrag entfernt.
* **Modifier:** Ein Modifier ist ein Key mit `modifier = true`. Sein Press wird
  sofort gesendet; er bleibt gedrückt, bis das physische Release kommt. Dadurch
  sieht die onPC die Chord-Reihenfolge MA-Press → Fix-Press → Fix-Release.
  Lokale Modifier (`fine`, `ultra`) senden keinen Frame und beeinflussen nur die
  Encoder-Auflösung.
* **Cleanup:** Bei Shutdown, Verbindungsverlust oder Geräteverlust werden alle
  offenen Presses nach absteigender Ordnungsnummer freigegeben. Nach einem
  Reconnect wird das Register geleert, ohne alte Frames nachzuspielen.
* **CMD-Keys:** Ein CMD-Key sendet beim Press genau einen `command`-Frame und
  beim Release nichts. Er wird trotzdem im Register geführt, damit ein zweiter
  Press ohne Release unterdrückt wird.

Hardkey-Transport (ADR-0007):

* `native`: `{"requestType":"hardkey","hardkey":<id>,"value":1.0|0.0,"session":<id>,"maxRequests":0}`.
* `lua`: `{"command":"LUA 'gma.canbus.hardkey (<id>, true|false, false)'","session":<id>,"requestType":"command","maxRequests":0}`.
* Die Frame-Form wird in `ma2_client.py` zentral gebaut; die Engine übergibt
  nur `(hardkey_id, pressed)`.

### Encoder-Pipeline

1. `hid_input` liefert signed Detent-Deltas pro Encoder.
2. `mapping` addiert `delta × Beschleunigung × Auflösung` in `pending_units`.
   Für Wheel-Ziele werden ganze Ticks gesendet und der Rest als Bruchteil
   behalten; für Attribut-Ziele wird der Float-Wert gesendet.
3. Ein Flush ist fällig, wenn das Flush-Intervall abgelaufen ist und das
   Per-Encoder-Mindestintervall erreicht ist, oder wenn die Idle-Frist nach dem
   letzten Input abgelaufen ist.
4. Beim Flush wird genau eine Aktion an `ma2_client` übergeben:
   * CMD-Attribut: `Attribute "<Name>" At +<delta> Please`
   * CMD-Wheel: `Feature $feature.<wheel> At +<delta>`
   * Native Attribut: `{"requestType":"encoder","name":"<Name>","value":<delta>,…}`
   * Native Wheel: Builder aus `wheel_protocol.py`

Beschleunigung: `none` (Multiplier 1), `linear`
(`1 + k·(rate−1)`, gekappt auf `max_multiplier`) oder `exponentiell`
(`rate^α`, gekappt). `rate` ist die Anzahl Detents pro Beschleunigungsfenster.
Das Vorzeichen bleibt erhalten; ein von Null verschiedener Input ergibt nie
einen Delta von 0.

Auflösung: getrennte Multiplikatoren für Wheel und Attribut. Beim Umschalten
wird der offene Pending-Delta zuerst mit der alten Auflösung geflusht. Bei
gleichzeitigem Fine und Ultra gewinnt Ultra.

### Rate-Limiter und Queue

Zwei Ebenen (ADR-0005):

* **Globaler Token-Bucket:** `messages_per_second` (Default 25), `burst` 10.
  Jeder Frame verbraucht ein Token.
* **Per-Encoder-Scheduler:** Mindestabstand
  `base_interval + stream_penalty × aktive_encoder` (Default 25 ms + 2,4 ms),
  Idle-Flush `idle_base + idle_penalty × aktive_encoder` (Default 40 ms + 2,2 ms).

Die Queue hat zwei Prioritäten: Steuer-Frames (Press, Release, Command, Close,
Keepalive) vor Encoder-Flushes. Steuer-Frames werden nie verworfen.
Encoder-Pending wird bei Sättigung weiter akkumuliert, aber pro Ziel auf
`max_pending_delta` gekappt und das Kappen geloggt. Eine Backpressure-Wache
halbiert die globale Rate vorübergehend, wenn die Kontroll-Queue über zwei
Sekunden mehr als 100 Einträge hält oder der WebSocket-Sendepuffer 64 KiB
überschreitet.

### Geräteerkennung und -profile

* Beim Start und danach jede Sekunde werden `evdev.list_devices()` und die
  rohen MIDI-Knoten aus `/proc/asound/cards` + `/dev/snd/midiC*` ausgewertet.
  Es wird kein zusätzliches `pyudev` eingeführt.
* Ein Gerät passt, wenn Backend, Vendor-/Product-ID und optionaler Namensfilter
  zum `[devices.*]`-Eintrag passen. `vendor_id = 0` ist nur mit gesetztem
  `name_contains` erlaubt, damit kein beliebiges Gerät übernommen wird.
* Bei mehreren Interfaces desselben Geräts wird das Interface mit den meisten
  Tastatur-Key-Codes gewählt; die übrigen werden geloggt und ignoriert.
* Das Profil (`[profiles.*]`) bildet je nach Backend evdev-Codes oder
  MIDI-Noten auf logische Controls ab. evdev-Encoder tragen `id`,
  `detents_per_revolution` und `direction`; MIDI-Encoder tragen `id`, `note`,
  `cw_velocity`, `ccw_velocity` und `direction`.
* Der ASL MK2 E4B3 ist ein USB-MIDI-Gerät (`04d8:e817`) und stellt keinen
  evdev-Knoten bereit. Der geführte Mitschnitt vom 2026-11-25 ergab: Noten 1–4
  sind die Encoder (eine Note pro Rastung, Velocity `127` = rechts, `1` =
  links), Noten 5–8 die Encoder-Clicks und Noten 9–11 die drei Tasten. Der
  Parser wertet bei Tastennoten Velocity `1` oder `0` als Release; bei
  Encodernoten ist Velocity `1` dagegen eine Links-Rastung. Da Tasten- und
  Encodernoten disjunkt sind, kollidieren die Interpretationen nicht.
* Fehlt ein Gerät, läuft der Daemon weiter und sucht erneut. Verschwindet ein
  Gerät, werden seine gehaltenen Keys freigegeben.

### Konfigurationsschema

Vollständiges Beispiel (gekürzt um repetitive Number-Block-Einträge):

```toml
schema_version = 1

[ma2]
host = "192.168.0.10"
port = 80
path = "/?ma=1"
username = "ma2pi"
password_file = "/etc/ma2pi/ma2pi.password"  # alternativ password_env
keepalive_interval = 5.0
login_timeout = 10.0
hardkey_transport = "native"                  # native | lua
hardkey_press_value = 1.0
hardkey_release_value = 0.0

[reconnect]
initial_delay = 1.0
max_delay = 30.0
jitter = 0.2

[rate_limit]
messages_per_second = 25
burst = 10
encoder_base_interval = 0.025
encoder_stream_penalty = 0.0024
encoder_idle_base = 0.040
encoder_idle_penalty = 0.0022
max_pending_delta = 1000

[logging]
level = "INFO"

[devices.cherry]
vendor_id = 0x046a
product_id = 0x0000
name_contains = "Cherry"
profile = "cherry-g86"

[devices.asl]
backend = "midi"
vendor_id = 0x04d8
product_id = 0xe817
name_contains = "ASL MK2"
profile = "asl-mk2-e4b3"

[profiles.cherry-g86.keys]
KEY_F1 = "fix"
KEY_F2 = "store"
KEY_F3 = "clear"
KEY_F4 = "clear_all"
KEY_ESC = "ma"
KEY_F5 = "at"
KEY_F6 = "thru"
KEY_ENTER = "please"
KEY_F7 = "go_plus"
KEY_F8 = "go_minus"
KEY_F9 = "pause"
KEY_KP0 = "num_0"
KEY_KP1 = "num_1"
# … num_2 bis num_9 analog

# ASL: Noten 1-4 = Encoder 1-4 (Velocity 127 = rechts, 1 = links),
#       Noten 5-8 = Encoder-Clicks, Noten 9-11 = die drei Tasten.
[profiles.asl-mk2-e4b3.notes]
5 = "asl_click_1"
9 = "fine"
10 = "ultra"
11 = "asl_button_3"

# Jeder Encoder hat genau eine Note; die Richtung steckt in der Velocity.
[[profiles.asl-mk2-e4b3.midi_encoders]]
id = 1
note = 1
cw_velocity = 127
ccw_velocity = 1
direction = 1

# … id = 2..4 mit den Noten 2, 3, 4

[mapping.modifiers]
ma = { hardkey = "MA" }
fine = { local = true }
ultra = { local = true }

[mapping.keys]
fix = { hardkey = "Fix" }
store = { hardkey = "Store" }
clear = { hardkey = "Clear" }
clear_all = { command = "Clear All" }
at = { hardkey = "At" }
thru = { hardkey = "Thru" }
please = { hardkey = "Please" }
go_plus = { hardkey = "Go +" }
go_minus = { hardkey = "Go -" }
pause = { hardkey = "Pause" }
num_0 = { hardkey = "0" }
# … num_1 bis num_9 analog
# x1 = { hardkey = "X1" }   # optional

[[mapping.encoders]]
id = 1
wheel = 1

[[mapping.encoders]]
id = 2
attribute = "Dimmer"

[mapping.encoder_acceleration]
curve = "linear"          # none | linear | exponential
window = 0.10
max_multiplier = 4.0

[mapping.encoder_resolution.wheel]
normal = 1.0
fine = 0.25
ultra = 0.1

[mapping.encoder_resolution.attribute]
normal = 1.0
fine = 0.1
ultra = 0.01

[mapping.encoder_resolution.modifiers]
fine = "fine"
ultra = "ultra"

[encoder]
transport = "cmd"         # cmd | native
```

Validierungsregeln: unbekannte Schlüssel sind Fehler; `schema_version` muss
`1` sein; genau eine Passwortquelle; `wheel` und `attribute` schließen sich aus;
Wheel-Bereich 1–10; Encoder-IDs eindeutig; referenzierte Profile, Keys und
Hardkey-Namen müssen existieren; `keepalive_interval` < 10; Ratenbereich 5–40.

### Deployment

* `/opt/ma2pi/app` – Anwendungscode, Eigentümer `ma2pi`.
* `/opt/ma2pi/.venv` – venv, erzeugt mit `/usr/bin/python3 -m venv`.
* `/etc/ma2pi/config.toml` – Konfiguration, `0640 root:ma2pi`.
* `/etc/ma2pi/ma2pi.password` – Passwort, `0640 root:ma2pi`.
* `deploy/99-ma2pi.rules` – `GROUP="ma2pi"`, `MODE="0660"` für Cherry und ASL.
* `deploy/ma2pi.service` – startet `/opt/ma2pi/.venv/bin/python -m ma2pi`,
  `Restart=always`, `After=network-online.target`, `User=ma2pi`,
  `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`,
  `PrivateDevices=false`, `DeviceAllow=/dev/input/event* r`,
  `NoNewPrivileges=true`, `Environment=PYTHONDONTWRITEBYTECODE=1`.
* Keine `ReadWritePaths`: Logs gehen ins Journal, Python schreibt keine
  Bytecode-Dateien. Optionales `LoadCredential` für das Passwort.
* `deploy/install.sh` ist idempotent: User anlegen, Verzeichnisse, venv,
  `pip install`, Unit und udev-Regel installieren, `daemon-reload`,
  `udevadm control --reload`, Dienst aktivieren. Bestehende Config und
  Passwortdatei werden nie überschrieben.

### Teststrategie

* **Unit:** Config-Validierung, Hardkey-State-Machine, Modifier-Cleanup,
  Encoder-Akkumulation/Beschleunigung/Auflösung, Rate-Limiter, Frame-Builder.
* **Integration:** `tests/mock_ma2.py` ist ein `websockets`-Server, der
  `serverStatus`, `sessionInformation`, Login und Keepalive beantwortet und
  alle Frames als JSONL protokolliert. Ein Fake-Input-Iterator speist
  Key-/Encoder-Events ein; die Tests prüfen Reihenfolge, Raten und Reconnect.
* **Capture-Fixture:** Sobald ein Wheel-Capture vorliegt, wird es als JSONL-
  Fixture abgelegt und im nativen Modus gegen die Builder geprüft.
* **Hardware-Smoke:** MA+Fix → Desk Lock, Store halten → Store Options, Clear
  halten → ClearAll, Encoder-Richtung, Wheel-Zuordnung, onPC-Neustart.
* **Abnahme:** `openspec validate --strict` und `pytest` sind grün; der
  Dry-Run erzeugt für jede Aktion genau die erwarteten Frames.

## Risks / Trade-offs

* **onPC blockiert trotz Limiter** → Default 25/s, Burst 10, Per-Encoder-
  Mindestabstand, Backpressure-Wache, Stresstest über zehn Minuten; bei Bedarf
  Default auf 20/s senken.
* **Native Hardkey-Frames werden von der onPC-Version nicht akzeptiert** →
  `hardkey_transport = "lua"` als verifizierter Fallback; Umschaltung ohne
  Codeänderung.
* **Wheel-Capture liefert kein stabiles Format** → CMD-Wrapper bleibt final;
  ADR-0002 wird mit dem Capture-Ergebnis aktualisiert.
* **ASL MK2 E4B3 ist kein evdev-Gerät** → MIDI-Reader hinter derselben
  normalisierten Schnittstelle; USB-IDs, Notenbelegung und Richtungs-Velocities
  sind per geführtem Mitschnitt verifiziert. Abweichungen bei einzelnen
  Rastungen werden nur im Profil korrigiert.
* **Mehrere Cherry-Interfaces liefern Doppel-Events** → Interface-Scoring nach
  Key-Capabilities, nur ein Keyboard-Interface wird geöffnet.
* **Reconnect-Sturm nach onPC-Neustart** → exponentieller Backoff mit Jitter und
  Obergrenze; Login-Fehler erhalten einen längeren Backoff als Verbindungsfehler.
* **Hängende Taste nach hartem Prozessabbruch** → systemd startet neu, die neue
  Session startet sauber; die Engine spielt keine alten Presses nach.
* **MD5 ist kryptografisch schwach** → vom Protokoll vorgegeben; Hash nur im
  Speicher, keine Logs, LAN-Annahme. Kein Klartextpasswort in der Config.

## Migration Plan

Das Projekt startet greenfield; es gibt keine Bestandsdaten. Deployment:

1. Trixie-System vorbereiten, Repository nach `/opt/ma2pi/app` bringen.
2. `deploy/install.sh` ausführen (User, venv, Dependencies, Unit, udev).
3. `config.toml` nach `/etc/ma2pi/config.toml` kopieren und Host, Benutzer,
   Geräte-IDs sowie Passwortdatei anpassen.
4. `--check-config` und `--dry-run` ausführen; Frames gegen die Erwartung prüfen.
5. Dienst starten, Login im onPC-Log prüfen, Hardware-Smoke-Test durchführen.
6. Wheel-Capture durchführen und ADR-0002 aktualisieren.

Rollback: Dienst stoppen und deaktivieren, Unit und udev-Regel entfernen,
`udevadm control --reload`, optional User und `/opt/ma2pi` entfernen. Die
Konfiguration bleibt für einen erneuten Versuch erhalten.

## ADR-Übersicht

| ADR | Thema | Status |
| --- | --- | --- |
| 0001 | Web-Remote-WebSocket als Transportweg | Proposed |
| 0002 | Wheel-/Encoder-Strategie inkl. Capture | Proposed |
| 0003 | Python 3.13 + asyncio + evdev | Proposed |
| 0004 | Deployment als venv-Dienst | Proposed |
| 0005 | Rate-Limiting gegen onPC-Lockup | Proposed |
| 0006 | Konfigurationsschema in TOML | Proposed |
| 0007 | Hardkey-Transport und Press/Release-Sicherheit | Proposed |
| 0014 | ASL MK2 E4B3 als MIDI-Gerät hinter der Input-Schnittstelle | Accepted |
