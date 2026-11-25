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
> capture, live Web Remote login, wheel capture, Raspberry Pi service
> installation and hardware smoke/stress tests) are still open. See
> [Open hardware acceptance](#open-hardware-acceptance).

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration reference](#configuration-reference)
- [Command line](#command-line)
- [Dry-run: expected frame sequence](#dry-run-expected-frame-sequence)
- [Identifying the devices](#identifying-the-devices)
- [Wheel protocol capture](#wheel-protocol-capture)
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
* `ma2pi/wheel_protocol.py` — native wheel builder, gated until a capture is
  documented.

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
* The Cherry keyboard and the ASL panel connected by USB.

Install the OS packages once:

```bash
sudo apt update
sudo apt install python3 python3-venv udev systemd
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
| `hardkey_transport` | string | `"native"` | `native` or `lua`. `lua` is the verified fallback for onPC versions that reject native hardkey frames. |
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
bank in the UI, the physical encoders move with it. `wheel`/`attribute` encoders
are not used by the example config.

### `[mapping.screen_encoders]`

Optional names for the screen-encoder mode (slots 1–4). While the section is
missing, pressing the `screen_mode` key logs a warning and leaves the encoders in
attribute mode.

### `[mapping.encoder_acceleration]`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `curve` | string | `"none"` | `none`, `linear`, `exponential`/`exponentiell`. |
| `window` | float | `0.10` | Rate measurement window in seconds, `> 0`. |
| `max_multiplier` | float | `4.0` | Maximum acceleration, `>= 1`. |

### `[mapping.encoder_resolution.wheel]` and `.attribute`

Each has `normal`, `fine`, `ultra` floats `> 0`. Defaults:

* wheel: `1.0`, `0.25`, `0.1`
* attribute: `1.0`, `0.1`, `0.01`

`[mapping.encoder_resolution.modifiers]` names the local modifiers (`fine`,
`ultra`). Both must exist and be `local = true`. Ultra wins when both are held.

### `[encoder]`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `transport` | string | `"cmd"` | `cmd` or `native`. Native wheel mode is rejected until a wheel capture is documented; native attribute frames are allowed. |

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

## Wheel protocol capture

The native wheel frame format is **not yet documented**. Until a capture exists,
keep `encoder.transport = "cmd"`; the CMD wrapper
(`Feature $feature.<n> At +<delta>`) works unchanged. To capture the native
format:

1. Open onPC on a machine with Chrome/Chromium/Edge and load the show.
2. Open DevTools (`F12`) → **Network** tab, enable **Preserve log**, and filter
   the request list with `?ma=1` (or `WS`).
3. Reload the Web Remote page so the WebSocket connects. Select the `?ma=1`
   entry.
4. Open the **Messages** tab. Clear the message list.
5. In the Web Remote UI, select a fixture and turn one encoder wheel one detent
   forward, then one detent backward. Do not touch the keyboard.
6. Filter the messages for `requestType` or `wheel` and locate the outgoing
   frames. Copy each complete JSON object.
7. Save one JSON object per line as
   `tests/fixtures/wheel-capture.jsonl`. Keep at least one forward and one
   backward frame, with the session value normalised or documented.
8. Update the constants/builder in `ma2pi/wheel_protocol.py`, set
   `NATIVE_WHEEL_CONFIRMED = True`, and add a test that reproduces the captured
   structure from the fixture.
9. Record the result in a successor ADR to ADR-0002 (`adr link` with “Amends” /
   “Amended by”); do not edit the old ADR. Set `encoder.transport = "native"`
   only after the capture test passes.
10. Re-run `--check-config` and the full test suite.

The same procedure can capture hardkey frames if a future onPC version changes
the native hardkey format; the LUA fallback remains available through
`hardkey_transport = "lua"`.

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
`/etc/ma2pi/config.toml` and `/etc/ma2pi/ma2pi.password` untouched.

Rollback:

```bash
sudo systemctl disable --now ma2pi.service
sudo rm -f /etc/systemd/system/ma2pi.service
sudo rm -f /etc/udev/rules.d/99-ma2pi.rules
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
| Frames visible in dry-run but nothing happens | Check `hardkey_transport` (`native` vs `lua`) and that Web Remote accepts commands; inspect `journalctl` at `DEBUG`. |
| Encoder direction reversed | Set `direction = -1` in the profile encoder entry. |
| Wheel moves too far | Use the `fine`/`ultra` modifiers or lower the resolution values. |
| Native wheel config rejected | Expected until a capture is documented; use `encoder.transport = "cmd"`. |

## Open hardware acceptance

These tasks require the physical devices and a Raspberry Pi and are intentionally
still open:

* Controlled Cherry capture: correlate every scancode with the printed key and
  complete the profile — task 3.8.
* Live Web Remote login and hardkey-transport decision (`keyname` vs `lua`) —
  task 7.3 (blocked: onPC rejects the supplied credentials).
* Native wheel capture — task 5.8.
* Pi installation, `systemd-analyze verify`, udev access test — tasks 6.1–6.5.
* Hardware smoke, stress and reconnect acceptance — tasks 7.3–7.5.
* `pytest` on the Pi — task 8.4.
* ADR status promotion based on hardware evidence — task 7.6.

## License

Released under the [MIT License](LICENSE).
