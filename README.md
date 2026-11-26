# ma2pi — Cherry keyboard and ASL encoders for grandMA2 onPC

`ma2pi` is a small Python 3.13 asyncio daemon that maps a Cherry POS Keyboard
G86-63400EUADAA and an ASL MK2 E4B3 encoder panel to grandMA2 onPC. The only
transport to onPC is the **Web Remote WebSocket API** (`ws://<host>:<port>/?ma=1`).
MIDI is used solely as the input transport of the ASL panel; there is no MIDI,
OSC, Telnet or Showcockpit path to onPC, and no parameter unlock.

> Status: the software is implemented and the test suite runs on the
> development machine and on the Pi. The ASL has been identified as a USB-MIDI
> device, its MIDI backend is implemented, and its note/velocity layout has been
> verified on the hardware. Remaining acceptance steps (controlled Cherry
> capture, live Web Remote login, ASL LED protocol, Raspberry Pi service
> installation and hardware smoke/stress tests) are still open. See
> [Open hardware acceptance](#open-hardware-acceptance).

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration reference](#configuration-reference)
- [Web-Oberfläche](#web-oberfläche)
- [JSON-API](docs/api.md)
- [Command line](#command-line)
- [Dry-run: expected frame sequence](#dry-run-expected-frame-sequence)
- [Identifying the devices](#identifying-the-devices)
- [Encoder protocol notes](#encoder-protocol-notes)
- [Tests](#tests)
- [Update and rollback](#update-and-rollback)
- [Troubleshooting](#troubleshooting)
- [Open hardware acceptance](#open-hardware-acceptance)

## How it works

```
Cherry keyboard ─┐
                 ├─ evdev ─┐
                 │         ├─→ normalised InputEvent ─→ MappingEngine ─→ Ma2Client ─→ onPC
ASL encoders ────┘         │                          (held keys,        (queue,      WebSocket
                 └─ MIDI ──┘                           chords, encoders)  rate limit)
```

* `ma2pi/config.py` — strict TOML schema, all references validated before start.
* `ma2pi/hid_input.py` — evdev enumeration, interface scoring, key/axis
  normalisation, hotplug and encoder decoding.
* `ma2pi/midi_input.py` — raw ALSA-MIDI enumeration, incremental note parser,
  button and encoder normalisation for the ASL, hotplug and permission handling.
* `ma2pi/mapping.py` — held-key register, modifier chords, CMD keys, encoder
  accumulation, acceleration and Normal/Fine/Ultra resolution.
* `ma2pi/ma2_client.py` — handshake, login, keepalive, reconnect, one global
  send queue with control priority, token bucket and backpressure guard.
* `ma2pi/frames.py` — exact JSON frame builders.
* `ma2pi/wheel_protocol.py` — historischer Wheel-Builder; die Encoder nutzen
  heute ausschließlich das native Attribut-Format.

Releases and commands are never dropped. Encoder frames are coalesced per
target. On a connection loss the local key state is cleared and no stale
presses are replayed.

## Requirements

* Raspberry Pi OS Trixie / Debian 13 (other Linux distributions work in
  principle; the deployment files target systemd and udev).
* Python **3.13** and `python3-venv`.
* grandMA2 onPC reachable over the network with Web Remote enabled.
* A non-root system user `ma2pi` with read access to `/dev/input/event*` and
  `/dev/snd/midiC*` through the supplied udev rules.
* NetworkManager with `nmcli` and Polkit for the **Netzwerk** page. The
  installer grants `ma2pi` only the two NetworkManager actions needed to change
  and activate a system connection.
* The Cherry keyboard and the ASL panel connected by USB.

Install the OS packages once:

```bash
sudo apt update
sudo apt install python3 python3-venv udev systemd network-manager polkitd
```

## Installation

```bash
git clone <repository> ~/gMA2PiControl
cd ~/gMA2PiControl
sudo deploy/install.sh
```

The script is idempotent. It creates the system user/group `ma2pi`, installs the
application to `/opt/ma2pi/app`, creates `/opt/ma2pi/.venv`, installs the Python
package, installs the systemd unit and udev rule, and enables the service. It
**never overwrites** an existing `/etc/ma2pi/config.toml` or
`/etc/ma2pi/ma2pi.password`.

Then:

1. Edit `/etc/ma2pi/config.toml` (host, username, device filters, mappings).
2. Put the onPC password into `/etc/ma2pi/ma2pi.password` (no trailing text
   needed; surrounding whitespace is stripped).
3. Validate and try a dry run:

   ```bash
   sudo -u ma2pi /opt/ma2pi/.venv/bin/python -m ma2pi \
       --config /etc/ma2pi/config.toml --check-config
   sudo -u ma2pi /opt/ma2pi/.venv/bin/python -m ma2pi \
       --config /etc/ma2pi/config.toml --dry-run
   ```

4. Identify the devices and adjust `[devices.*]` / the udev rule (see below).
5. Start the service and watch the journal:

   ```bash
   sudo systemctl restart ma2pi.service
   journalctl -u ma2pi -f
   ```

`deploy/install.sh` only enables the unit. Start it explicitly after the
configuration is valid.

## Configuration reference

The file is TOML with `schema_version = 1`. Unknown keys are rejected. A
complete example is in [`config.toml`](config.toml).

### `[ma2]`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `host` | string | — | onPC IPv4/hostname. |
| `port` | int | `80` | Web Remote port, 1–65535. |
| `path` | string | `"/?ma=1"` | WebSocket path, must start with `/`. |
| `username` | string | — | onPC user. |
| `password_file` | string | — | File containing the password. Exactly one of `password_file`/`password_env` is required. |
| `password_env` | string | — | Environment variable containing the password. |
| `keepalive_interval` | float | `5.0` | Seconds between keepalives, `0 < x < 10`. |
| `login_timeout` | float | `10.0` | Seconds to wait for each handshake message, `> 0`. |
| `hardkey_press_value` | float | `1.0` | Press value, must be `> 0.9`. |
| `hardkey_release_value` | float | `0.0` | Release value, must be `< 0.9`. |

The password and its MD5 hash are never logged.

### `[reconnect]`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `initial_delay` | float | `1.0` | First retry delay, `> 0`. |
| `max_delay` | float | `30.0` | Upper bound, `>= initial_delay`. |
| `jitter` | float | `0.2` | Random factor, `0…1`. |
| `login_failure_delay` | float | `10.0` | Minimum delay after a rejected login, `> 0`. |

### `[rate_limit]`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `messages_per_second` | int | `25` | Global frame rate, 5–40. |
| `burst` | int | `10` | Token bucket burst, 1–200. |
| `encoder_base_interval` | float | `0.025` | Minimum spacing between encoder frames, `> 0`. |
| `encoder_stream_penalty` | float | `0.0024` | Additional spacing per active encoder, `>= 0`. |
| `encoder_idle_base` | float | `0.040` | Accumulation/flush interval, `> 0`. |
| `encoder_idle_penalty` | float | `0.0022` | Additional idle spacing per active encoder, `>= 0`. |
| `max_pending_delta` | int | `1000` | Maximum accumulated delta per encoder, `> 0`; excess is dropped and logged. |

### `[logging]`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `level` | string | `"INFO"` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. |

### `[web]`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `bind` | string | `"0.0.0.0"` | Listen address; changes need a service restart. |
| `port` | int | `8080` | HTTP/WebSocket port, 1–65535. |
| `pin_enabled` | bool | `false` | PIN gate for the UI and every non-public API path. |
| `pin` | string | `""` | 4–12 digits; empty means no PIN. Set one to protect the UI. |

### Web-Oberfläche und Offline-Betrieb

Die Oberfläche wird als statisches Svelte-Bundle aus `web/dist` vom Daemon
ausgeliefert. Gebaut wird sie auf dem Entwicklungsrechner oder in CI:

```bash
cd web
npm ci
npm run build
npm run check:offline
```

`npm run check:offline` prüft den Build auf externe `src`-/`href`-Ziele,
`url()`-Referenzen, absolute `fetch`-/WebSocket-Adressen sowie CDN-, Font- und
Telemetrie-Hosts. Der Build enthält nur relative Asset-Pfade. Zusätzlich wurde
die gebaute Oberfläche in einem Browser gegen einen reinen Dateiserver geladen:
alle Anfragen gingen an denselben lokalen Host (HTML, JavaScript, CSS); es gab
keine externen Netzwerkaufrufe. Die fehlenden API-Antworten in diesem Aufbau
sind erwartet und betreffen nur die Live-Daten, nicht das Laden der Oberfläche.

### `[led]`

LED feedback for the ASL mode indicator (protocol verified live on the device).

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `enabled` | bool | `false` | Turn LED output on. |
| `device` | string | auto | Raw MIDI node; default is the configured `midi` device. |
| `note` | int | `9` | LED note of the button (9–11 = buttons 1–3). |
| `attribute_color` | name or index | `"red"` | Colour in attribute mode. |
| `screen_color` | name or index | `"green"` | Colour in screen mode. |
| `brightness` | int | `127` | LED brightness, 0–127. |
| `brightness_channel`/`color_channel` | int | `1`/`2` | MIDI channels for brightness and colour index, must differ. |

Each colour update is `9F 7F 7F` (enable MIDI LED mode) followed by two Note On
messages: channel 1 velocity = brightness, channel 2 velocity = colour index.
`9F 7F 7E` releases LED control and is only sent on shutdown — sending it after
a colour update would switch the buttons back to keypress mode. The port stays
open, because opening and closing it per message resets the LEDs.
Verified colour indices: `green` = 8, `red` = 48, `white` = 127; any index
0–127 can be configured directly.

### `[devices.<name>]`

| Key | Type | Meaning |
| --- | --- | --- |
| `backend` | string | `"evdev"` (default) or `"midi"`. |
| `vendor_id` | int | USB vendor ID, `0…0xFFFF`. `0` is only allowed together with `name_contains`. |
| `product_id` | int | USB product ID, `0…0xFFFF`; `0` is a wildcard. |
| `name_contains` | string | Optional case-insensitive substring of the device name. |
| `profile` | string | Required reference to `[profiles.<name>]`. |

For `evdev`, if several interfaces match, the one with the most keyboard key
codes is opened; ties are broken by total input capability and path. For `midi`,
the first matching `/dev/snd/midiC*` node is used.

### `[profiles.<name>]`

`keys` maps raw evdev key names to logical controls:

```toml
[profiles.cherry-g86.keys]
KEY_F1 = "fix"
KEY_ESC = "ma"
```

`encoders` is an array of tables for evdev axes:

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `id` | int | — | Logical encoder ID, `> 0`, unique across all profiles. |
| `control` | string | — | evdev axis name (`ABS_X`, `REL_X`, …), unique per profile. |
| `detents_per_revolution` | int | `24` | Scale for absolute axes, `> 0`. |
| `direction` | int | `1` | `1` or `-1`. |
| `threshold` | float | `0.0` | Ignore smaller raw deltas, `>= 0`. |

A profile that references a control the opened device does not advertise aborts
the daemon with the profile, device and control in the message.

MIDI devices use `notes` and `midi_encoders` instead:

```toml
[profiles.asl-mk2-e4b3.notes]
5 = "asl_click_1"
9 = "fine"
10 = "ultra"

[[profiles.asl-mk2-e4b3.midi_encoders]]
id = 1
note = 1
cw_velocity = 127   # default
ccw_velocity = 1    # default
direction = 1
```

`notes` maps a MIDI note number (`0…127`) to a logical control. A note-on with
velocity greater than `1` is a press; velocity `1` or a note-off is a release.
`midi_encoders` maps exactly one note per encoder; the velocity selects the
direction, so every note-on counts as one detent and the note-off is ignored.
`cw_velocity`/`ccw_velocity` must differ and lie between `1` and `127`.
`direction = -1` swaps the two directions without touching the profile. A note
may not be used as both a button and an encoder, and encoder IDs are unique
across all profiles.

The verified ASL layout is:

| Note | Meaning |
| --- | --- |
| 1–4 | Encoders 1–4, one note per detent; velocity `127` = right, `1` = left |
| 5–8 | Encoder push buttons 1–4 |
| 9–11 | The three standalone buttons |

So `cw_velocity = 127` and `ccw_velocity = 1` are correct for this hardware;
use `direction = -1` if a clockwise turn should decrement.

### `[mapping.modifiers.<control>]`

Either `hardkey = "<name-or-id>"` or `local = true`, never both. A local
modifier is not sent to onPC; it only changes the encoder resolution. `fine` and
`ultra` must be local.

A hardkey modifier is held down in the onPC for as long as the physical control
is held. While the **MA** modifier is held, the four slot encoders target the
screen encoders from `[mapping.screen_encoders]`; releasing MA returns them to
the attribute window. The shipped configuration maps the rightmost ASL button
(`asl_button_3`, note 11) to the **`NIPPLE`** hardkey as a normal key, not as a
second MA modifier.

### `[mapping.keys.<control>]`

One of `hardkey = "<name>"`, `command = "<MA2 command>"`, `screen_mode = true`
or `encoder_fine = <slot>`, never more than one.

* A command is sent exactly once on key-down and never on key-up; the string is
  passed through unchanged, including semicolons.
* `screen_mode = true` toggles the encoders between attribute and screen mode.
* `encoder_fine = <slot>` cycles that encoder Normal → Fine → Ultra → Normal.

### `[[mapping.encoders]]`

| Key | Type | Meaning |
| --- | --- | --- |
| `id` | int | Must exist in a profile and be unique. |
| `slot` | int | Attribute slot 1–4 on the encoder page, exclusive with `attribute`. |
| `attribute` | string | Fixed attribute name, exclusive with `slot`. |

A `slot` encoder follows the window the onPC shows: when you scroll the attribute
bank in the UI, the physical encoders move with it.

In the web UI the Encoder table has a **Screen-Encoder** column per physical
encoder. Choose `Screen 5`…`Screen 8` there to define what that encoder turns in
screen mode; `— keiner —` removes the target for its slot.

### `[mapping.screen_encoders]`

Names for the onPC screen encoders, mapped onto the physical slots 1–4. The
onPC numbers its screen encoders 5–8; the shipped configuration maps them in
reverse order so the physical order stays natural:

| Slot | onPC encoder |
| --- | --- |
| 1 | `"8"` |
| 2 | `"7"` |
| 3 | `"6"` |
| 4 | `"5"` |

While the section is missing, pressing the `screen_mode` key logs a warning and
leaves the encoders in attribute mode. The same targets are edited per physical
encoder in the web UI (Encoder table → *Screen-Encoder*); `— keiner —` removes
that slot from the section. If a specific onPC version names the encoders
differently, adjust the values there.

### `[mapping.encoder_acceleration]`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `curve` | string | `"none"` | `none`, `linear`, `exponential`/`exponentiell`. |
| `window` | float | `0.10` | Rate measurement window in seconds, `> 0`. |
| `max_multiplier` | float | `4.0` | Maximum acceleration, `>= 1`. |

### `[mapping.encoder_resolution.attribute]`

`normal`, `fine`, `ultra` floats `> 0` (defaults `1.0`, `0.1`, `0.01`). Only used
by encoders with a fixed `attribute`, because slot encoders send the resolution
to the onPC instead of scaling the delta. `[mapping.encoder_resolution.modifiers]`
optionally names local `fine`/`ultra` modifier controls.

## Web-Oberfläche

### Zugriff im LAN

Der Daemon liefert die Oberfläche und die JSON-API im selben Prozess aus.
Standard ist `0.0.0.0:8080`; beides steht in der `[web]`-Sektion:

```toml
[web]
bind = "0.0.0.0"
port = 8080
pin_enabled = false
```

Nach dem Start ist die Oberfläche unter `http://<pi-adresse>:8080/` erreichbar.
Änderungen an `bind` oder `port` werden erst nach einem Dienstneustart wirksam;
die Oberfläche weist darauf hin. Die Firewall des Pi wird vom Installer nicht
verändert – der Port muss im LAN erreichbar sein, sollte aber nicht aus dem
Internet weitergeleitet werden.

### Netzwerk

Die Seite **Netzwerk** verwaltet die kabelgebundene IPv4-Schnittstelle über
NetworkManager. Sie zeigt Schnittstelle, Verbindungszustand, Modus, aktuelle
Adresse, Subnetzmaske, Gateway und DNS. **DHCP** und **Statisch** lassen sich
umschalten; im statischen Modus werden Adresse, Subnetzmaske, Gateway und DNS
bearbeitet. Die Subnetzmaske wird in Punktnotation eingegeben (z. B.
`255.255.255.0`). Gateway und DNS dürfen leer bleiben; die Oberfläche warnt
dann, dass keine Standardroute bzw. kein DNS-Server gesetzt ist.

Vor dem Anwenden prüft der Daemon Adresse, Maske, Gateway, DNS und die lokale
Doppelbelegung. Danach wird die neue Konfiguration zunächst **nur temporär**
aktiviert. Die Verbindung kann dabei abbrechen. Die Oberfläche nennt die
Ziel-URL und verlangt, dass du sie öffnest und dich dort erneut mit der PIN
anmeldest; erst diese neue Sitzung bestätigt die Änderung. Wird nicht innerhalb
von 180 Sekunden bestätigt, stellt der Daemon automatisch die vorherige
Konfiguration wieder her. Der Pending-Zustand liegt unter
`/var/lib/ma2pi/network-pending.json` und überlebt einen Dienstneustart.

Unterstützt wird genau eine kabelgebundene IPv4-Schnittstelle. WLAN, IPv6,
VLAN, Bonding und mehrere gleichzeitig verwaltete Schnittstellen sind nicht
enthalten. Die Netzwerkeinstellungen stehen ausschließlich bei NetworkManager
und nicht in `config.toml`.

Die Berechtigung regelt
`/etc/polkit-1/rules.d/50-ma2pi-network.rules`: Der Benutzer `ma2pi` darf
Systemprofile ändern und Verbindungen aktivieren, aber keine WLAN- oder
sonstigen Systemaktionen ausführen. Der Dienst läuft weiterhin unprivilegiert;
`ProtectSystem=strict` und `NoNewPrivileges` bleiben aktiv.

### Sicherheitsmodell (v1)

* Eine einfache PIN-Sperre kann Oberfläche und API schützen. Sie ist
  standardmäßig **aus** und muss in der Konfiguration oder auf der Seite
  **Erweitert** gesetzt werden. Solange keine PIN gesetzt ist, zeigt die
  Oberfläche oben einen Warnbanner. Die PIN ist ein LAN-Schutz, kein Ersatz für
  TLS oder eine Benutzerverwaltung.
* Schreibende API-Aufrufe müssen `Content-Type: application/json` und den
  Header `X-Ma2pi-Request: 1` tragen. Einfache Formular-POSTs werden abgelehnt;
  das ist ein CSRF-Schutz, kein Ersatz für Authentifizierung.
* Das MA2-Passwort ist ausschließlich schreibbar. Antworten, Logs und
  Fehlermeldungen enthalten weder das Passwort noch dessen Hash; die Oberfläche
  zeigt nur, ob ein Passwort gesetzt ist. Die PIN wird ebenfalls nie
  zurückgegeben.
* Keine CORS-Freigabe: Die Oberfläche wird same-origin ausgeliefert.
* Keine externen Assets, Fonts, CDNs oder Telemetrie. Der Build wird mit
  `npm run check:offline` geprüft (siehe oben).
* Die PIN wird als HTTP-Cookie-Session gehalten. Nach einem Neustart des
  Dienstes ist eine erneute Anmeldung nötig.

### Änderungen anwenden

Die Seiten **MA2**, **Geräte/Mapping**, **Backups** und **Erweitert** schreiben
über die API. Die Seite **Netzwerk** schreibt über NetworkManager und nicht in
`config.toml`; ihre Änderung wird erst nach der Bestätigung dauerhaft
gespeichert. Jede Konfigurationsänderung wird serverseitig mit denselben Regeln
wie der Daemon-Start validiert. Bei Erfolg schreibt der Daemon die Konfiguration atomar
nach `/var/lib/ma2pi/config.toml`, gibt gehaltene Tasten in umgekehrter
Reihenfolge frei, verwirft offene Encoder-Deltas und tauscht das Mapping ohne
Dienstneustart. Werden Zugangsdaten geändert, testet der Daemon sie vorher; eine
bestehende Session bleibt bei reinen Mapping-Änderungen verbunden.

### Backups und Wiederherstellung

Backups liegen unter `/var/lib/ma2pi/backups/`:

* `config-<zeitstempel>.toml` – automatisch vor jedem Schreiben und auf Knopf
  in der Oberfläche, Rotation auf die letzten 20 Dateien.
* `last-good.toml` – die zuletzt aktive Konfiguration vor dem aktuellen Stand.

Die Seite **Backups** listet die Dateien, legt neue an und stellt sie nach einem
Bestätigungsschritt wieder her. Eine Wiederherstellung wird zuerst validiert;
ein beschädigtes oder schemawidriges Backup lässt die aktive Konfiguration
unverändert. Nach einer Wiederherstellung mit anderen Zugangsdaten versucht der
Daemon den Reconnect mit den wiederhergestellten Daten.

Die vollständige Endpunkt-, Payload- und Fehlerreferenz steht in
[`docs/api.md`](docs/api.md).

### Migration und Rollback

Bei der Installation wird eine vorhandene `/etc/ma2pi/config.toml` einmalig nach
`/var/lib/ma2pi/config.toml` übernommen und vorher gesichert. Die Datei unter
`/etc/ma2pi` bleibt liegen, wird aber nicht mehr beschrieben. Die systemd-Unit
nutzt `StateDirectory=ma2pi` und `ReadWritePaths=/var/lib/ma2pi`; nur dieser
Pfad ist unter `ProtectSystem=strict` beschreibbar.

Rollback auf die alte Version:

```bash
sudo systemctl stop ma2pi.service
sudo install -m 0640 -o root -g ma2pi /etc/ma2pi/config.toml /var/lib/ma2pi/config.toml
sudo systemctl start ma2pi.service
```

Die Backups unter `/var/lib/ma2pi/backups` bleiben dabei erhalten. Alternativ
kann die vorherige Version der Unit und des Codes eingespielt werden; die
Konfiguration unter `/etc/ma2pi` bleibt als Ausgangspunkt vorhanden.

## Command line

```bash
python -m ma2pi --help
python -m ma2pi --config /etc/ma2pi/config.toml --check-config
python -m ma2pi --config /etc/ma2pi/config.toml --list-devices
python -m ma2pi --config /etc/ma2pi/config.toml --dump-input
python -m ma2pi --config /etc/ma2pi/config.toml --dry-run
python -m ma2pi --config /etc/ma2pi/config.toml --log-level DEBUG
```

* `--check-config` validates and exits 0, or prints `datei:schlüssel: Ursache`
  and exits 2.
* `--list-devices` prints path, name, vendor/product and capabilities for every
  `/dev/input/event*`. It needs Linux and `evdev`.
* `--dump-input` prints normalised `InputEvent` objects live.
* `--dry-run` opens no socket and logs every frame it would send.

## Dry-run: expected frame sequence

`tests/test_dry_run.py` feeds this gesture through the example configuration and
asserts the exact frames below (session `0`, `maxRequests` omitted here):

| Gesture | Frame |
| --- | --- |
| MA down | `{"requestType":"hardkey","hardkey":68,"value":1.0}` |
| Fix down | `{"requestType":"hardkey","hardkey":41,"value":1.0}` |
| Fix up | `{"requestType":"hardkey","hardkey":41,"value":0.0}` |
| MA up | `{"requestType":"hardkey","hardkey":68,"value":0.0}` |
| Store down/up | `{"requestType":"hardkey","hardkey":59,"value":1.0}` / `0.0` |
| Clear down/up | `{"requestType":"hardkey","hardkey":105,"value":1.0}` / `0.0` |
| Go+ down/up | `{"requestType":"hardkey","hardkey":52,"value":1.0}` / `0.0` |
| Number 1 down/up | `{"requestType":"hardkey","hardkey":87,"value":1.0}` / `0.0` |
| Encoder 1, one detent | `{"command":"Feature $feature.1 At +1"}` |
| Encoder 2, one detent | `{"command":"Attribute \"Dimmer\" At +1 Please"}` |

MA + Fix is **Desk Lock**: MA is pressed first and held until its release, so
onPC sees the chord.

## Identifying the devices

```bash
lsusb
sudo -u ma2pi /opt/ma2pi/.venv/bin/python -m ma2pi \
    --config /etc/ma2pi/config.toml --list-devices
```

For the Cherry, keep the entry with vendor `0x046a` and the `name_contains`
filter. If several interfaces appear, the one with the most key codes is used.

The ASL MK2 E4B3 identifies as vendor `0x04d8`, product `0xe817`, and appears
as a raw MIDI node (for example `/dev/snd/midiC3D0`), not as `/dev/input/event*`.
The example config already uses `backend = "midi"` with these IDs and the note
profile. Verify the device with:

```bash
ma2pi --config /etc/ma2pi/config.toml --list-devices
sudo -u ma2pi ma2pi --config /etc/ma2pi/config.toml --dump-input
```

Each ASL button and each encoder detent must produce exactly one event
(`key … 1` / `key … 0` or `encoder encoder.N ±1`). On the verified unit a
clockwise detent yields `+1` and a counter-clockwise detent `-1`.

Reload the rules after editing:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=input --subsystem-match=sound
```

The supplied udev rules set both devices to group `ma2pi`. As a fallback the
service also joins the `audio` group, because ALSA creates MIDI nodes with
group `audio` and mode `0660`.

## Encoder protocol notes

Die Encoder sprechen ausschließlich das native Web-Remote-Format:

```json
{"requestType": "encoder", "name": "PAN", "value": 7.18}
{"requestType": "encoder", "name": "PAN", "resolution": 1}
```

* `name` ist das Attribut, das die onPC gerade anzeigt (`DIM`, `PAN`, `TILT`,
  `SHUTTER`, `COLORRGB1`, …).
* `value` ist ein relatives Delta; `resolution` (0 = Normal, 1 = Fine,
  2 = Ultra) kommt als eigener Frame ohne `value`.
* Die vier Encoder folgen dem Attribut-Fenster der onPC. Blätterst du dort
  weiter, wandern sie mit – ein lokaler Bankzähler existiert nicht.
* Ein Klick auf einen Encoder zyklisiert Normal → Fine → Ultra → Normal.
* Die Taste `screen_mode` schaltet auf die Screen-Encoder aus
  `[mapping.screen_encoders]`. Die onPC nummeriert sie 5–8; die
  Standardbelegung legt sie umgekehrt auf die Slots: Slot 1 → 8, Slot 2 → 7,
  Slot 3 → 6, Slot 4 → 5.
* MA halten (Cherry-Logo) und dabei einen Encoder drehen adressiert
  vorübergehend dieselben Screen-Encoder. Beim Loslassen folgt der nächste
  Detent wieder dem Attribut-Fenster.

### Screen-Encoder-Namen

Die onPC führt ihre Screen-Encoder als 5–8. Die mitgelieferte Konfiguration legt
sie umgekehrt auf die physischen Slots. Eine abweichende onPC-Version kann andere
`name`-Werte erwarten; dann im Web-UI in der Encoder-Tabelle pro physischem
Encoder die Spalte *Screen-Encoder* anpassen. Ein Mitschnitt (DevTools → Network
→ `?ma=1` → Messages, dann am Pult Screen-Encoder drehen) zeigt die tatsächlich
gesendeten Werte.

Die ASL-LEDs werden bereits über das verifizierte MIDI-Protokoll angesteuert
(siehe `[led]`).

Mitschnitt-Vorgehen wie oben: DevTools öffnen, `?ma=1` filtern, Messages
leeren, die Aktion ausführen, die vollständigen JSON-Objekte kopieren und als
Fixture ablegen. Ergebnis in einem Nachfolge-ADR zu ADR-0002/0015 festhalten.

## Tests

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```

The suite covers config validation, hardkey catalogue, frame builders,
handshake/login failure, keepalive, reconnect without replay, rate limiting,
queue priority, backpressure, dry-run, device selection, encoder decoding,
hotplug, permission errors and backoff, mapping/chords/cleanup, encoder
accumulation/acceleration/resolution, MIDI stream parsing and note
normalisation, a mock onPC server, and a 100 detents/s stress run. `evdev` is
imported lazily, so the suite also runs on macOS without input devices.

## Update and rollback

Update:

```bash
cd ~/gMA2PiControl
git pull
sudo deploy/install.sh
sudo systemctl restart ma2pi.service
journalctl -u ma2pi -n 50 --no-pager
```

`install.sh` replaces the code and venv contents but leaves
`/etc/ma2pi/config.toml` and `/etc/ma2pi/ma2pi.password` untouched. It also
installs `/etc/polkit-1/rules.d/50-ma2pi-network.rules` for the **Netzwerk**
page; the rule can be removed independently if the page is not needed.

Rollback:

```bash
sudo systemctl disable --now ma2pi.service
sudo rm -f /etc/systemd/system/ma2pi.service
sudo rm -f /etc/udev/rules.d/99-ma2pi.rules
sudo rm -f /etc/polkit-1/rules.d/50-ma2pi-network.rules
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
# optional, removes code and user but keeps /etc/ma2pi:
sudo rm -rf /opt/ma2pi
sudo userdel ma2pi
sudo groupdel ma2pi
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `Keine Leserechte` / `Permission denied` | udev rules installed, group `ma2pi`, user in that group, `udevadm control --reload-rules`, replug device. For `/dev/snd/midiC*` also check membership in the `audio` group. |
| `Konfiguriertes Gerät … nicht gefunden` | `--list-devices`; compare `backend`, `vendor_id`, `product_id`, `name_contains`; the daemon retries with backoff. |
| `Konfiguriertes MIDI-Gerät … nicht gefunden` | The ASL exposes `/dev/snd/midiC3D0`; check `lsusb` for `04d8:e817` and the udev rule for the `sound` subsystem. |
| `Profil … referenziert nicht unterstützte Controls` | The selected interface lacks a key/axis from the profile; choose the keyboard interface or correct the profile. |
| Login fails | `password_file`/`password_env`, exact onPC user name, Web Remote enabled, `forceLogin`; an empty password is valid and must still be sent as the MD5 of the empty string. |
| onPC not reachable | The daemon stays alive and reconnects with exponential backoff; check `journalctl`. |
| Frames visible in dry-run but nothing happens | Check the exact `keyname` spelling (log at `DEBUG`) and that Web Remote accepts commands. |
| Encoder direction reversed | Set `direction = -1` in the profile encoder entry. |
| Encoder moves too far | Click the encoder to switch to Fine/Ultra, or lower `mapping.encoder_resolution.attribute`. |
| **Netzwerk** zeigt „nicht verfügbar“ | `nmcli` installiert, `systemctl status NetworkManager`, Polkit-Regel unter `/etc/polkit-1/rules.d/` vorhanden; Log mit `journalctl -u ma2pi`. |
| Keine kabelgebundene Schnittstelle | `nmcli device status`; nur `type ethernet` wird verwaltet, WLAN und virtuelle Geräte nicht. |
| Bestätigung nach IP-Wechsel schlägt fehl | Neue Ziel-URL öffnen, dort PIN erneut eingeben; das alte Cookie gilt nur für die alte Adresse. Nach 180 s rollt der Pi automatisch zurück. |
| Netzwerkänderung bleibt hängen | `/var/lib/ma2pi/network-pending.json` prüfen; ein abgelaufener oder unterbrochener Zustand wird beim Dienststart zurückgerollt. |

## Open hardware acceptance

These tasks require the physical devices and a Raspberry Pi and are intentionally
still open:

* Controlled Cherry capture: correlate every scancode with the printed key and
  complete the profile — task 3.8.
* Live Web Remote login and hardkey-transport decision (`keyname` vs `lua`) —
  task 7.3 (blocked: onPC rejects the supplied credentials).
* ASL LED protocol capture (green/red for the screen mode) — task 5.8.
* Pi installation, `systemd-analyze verify`, udev access test — tasks 6.1–6.5.
* Hardware smoke, stress and reconnect acceptance — tasks 7.3–7.5.
* `pytest` on the Pi — task 8.4.
* ADR status promotion based on hardware evidence — task 7.6.

## License

Released under the [MIT License](LICENSE).
