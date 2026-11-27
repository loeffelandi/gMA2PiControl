# gMA2PiControl — Cherry keyboard and ASL encoders for grandMA2 onPC

`ma2pi` is a small Python 3.13 asyncio daemon that maps a Cherry POS Keyboard
G86-63400EUADAA and an ASL MK2 E4B3 encoder panel to grandMA2 onPC. The only
transport to onPC is the **Web Remote WebSocket API** (`ws://<host>:<port>/?ma=1`).
MIDI is used for controller input and LED output; there is no MIDI,
OSC, Telnet or Showcockpit path to onPC, and no parameter unlock.

> **Name:** the product is called **gMA2PiControl**. The Python package, the
> `ma2pi` command and the systemd unit keep their technical name so existing
> installations keep working.
>
> **Design:** the web interface follows the palette and typography of
> [sustain-vt.de](https://www.sustain-vt.de) — Bebas Neue for headings, DM Sans
> for text, both under the SIL Open Font License and bundled locally in
> `web/public/fonts/`.

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
  installer grants `ma2pi` only the NetworkManager actions needed to change and
  activate a system connection and to share WiFi as an access point (recovery hotspot).
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
Changes to `[led]` (`enabled`, `device`, notes, colours, brightness) take effect
at runtime on config reload without restarting the daemon, sharing the single
non-blocking `MidiManager` output handle.
Executor LEDs of other controllers are configured with `[feedback]` (see below).

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `enabled` | bool | `false` | Turn LED output on. |
| `device` | string | auto | Device name of the raw MIDI node. With more than one `midi` device and LED output enabled this key is required; otherwise validation aborts instead of guessing. |
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

The mode LED on `note` is red in attribute mode and green in screen mode. The
rightmost ASL button (`nipple_note`, 11) glows soft orange while idle
(`nipple_idle_color = 121`, `nipple_idle_brightness = 25`) and brighter while the
`NIPPLE` hardkey is pressed (`nipple_pressed_color = 116`,
`nipple_pressed_brightness = 127`). The middle ASL button (`fine_note`, 10) uses
`fine_color = 123` at `fine_idle_brightness = 25` and `fine_pressed_brightness = 127`
while held. Colours are palette indices (0–127).

### `[feedback]`

Mirrors executor state from the grandMA2 onto controller LEDs. `ma2pi` polls
the Web Remote with `requestType = "playbacks"` for every page that has
LED-capable button targets and sends one Note On per changed LED. Off by
default; the shipped `config.toml` enables it.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `enabled` | bool | `false` | Poll executor state and emit LED frames. |
| `interval_ms` | int | `250` | Poll interval, `100…2000`. |
| `off_state` | `"dark"` or `"off"` | `"dark"` | Stopped executor: dark shade of its colour, or LED off. |
| `fallback_color` | palette name | `"white"` | Used when the console reports no usable appearance colour. |

Only controls with a button target in `[mapping.playbacks]` are polled. A device
with banks gets LEDs for **every** bank at once, each on the MIDI channel of its
bank and with the bank's executor offset and overrides. The device only shows
the channel of the bank it is switched to, so nothing has to be re-sent when the
bank changes. A `page =
"current"` target is requested with `pageIndex = -1`, so the LEDs follow page
changes on the console (the console answers with the placeholder `iPage = 0`;
a fixed page `N` is answered with `iPage = N`). The colour is taken from the `bC`/`bdC` fields of the
response and mapped to the closest of the 15 palette colours. `cto` stands for
warm white (`#ffc882`) and `ctb` for cool white (`#c8e1ff`), so pure white
stays white while warm whites light the LED in CTO. Pure black
counts as "no colour" for that field; if `bdC` is unusable too, the fallback
applies.

An LED note listed in `led_notes` whose control has no button target in its
bank is switched off (velocity 0, or brightness 0 for `asl-mk2`) when feedback
starts, after the device is reopened, after a reconnect and after a
configuration change, so an unassigned button never keeps a stale colour.
Notes owned by `[led]` are left alone.

Polling stops while the Web Remote session is down. After a reconnect and after
a MIDI device is replugged, all LED states are re-sent. `--dry-run` logs the
intended frames instead of writing them. A running executor becomes bright, a
stopped one dark (or off); nothing is interpolated, so faders have no feedback.

### `[profiles.<name>.led_feedback]`

Declares that a profile's controls drive LEDs and how the device encodes them.
Each profile picks its own protocol, so a MIDICRAFT controller and an ASL can
run side by side:

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `protocol` | string | `"midicraft-v2"` | `"midicraft-v2"` or `"asl-mk2"`. |
| `led_notes` | array of ints | all profile notes with a button target | Notes of the first bank that actually have an LED. The controls on these notes are LED-capable in every bank, on that bank's own notes; other controls are never lit. |
| `enabled` | bool | `true` | Per-device switch. `false` leaves this device's LEDs untouched while other devices keep their feedback. |
| `frame_interval_ms` | int (1–500) | `20` | Minimum gap between two LED frames sent to this device. |
| `refresh_interval_ms` | int (`0`, 200–60000) | `0` | Re-sends the LEDs of one bank channel at a time so that every bank is refreshed once per interval; `0` = off. Needed for devices like the MIDICRAFT ENC that drop LED notes of banks they do not show and do not announce a bank switch. |
| `bright_level` | int (0–127) | `127` | `asl-mk2` only: brightness of a running executor. |
| `dark_level` | int (0–127) | `25` | `asl-mk2` only: brightness of a stopped executor with `off_state = "dark"`. |
| `colors` | table | see below | `asl-mk2` only: palette name → ASL colour index (0–127). |

```toml
[profiles.midicraft-enc.led_feedback]
protocol = "midicraft-v2"
led_notes = [65, 66, 67, 68, 69, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84]
enabled = true
frame_interval_ms = 20
```

LED frames are not written in a burst. Each device has its own queue that sends
at most one frame per `frame_interval_ms`; a frame that is still waiting is
replaced when the LED changes again. If the device stops taking bytes from its
output buffer for more than 2 s, output to that device is paused with one
warning and resumes in full once the device has been reopened. Input from the
device is unaffected.

`midicraft-v2` sends note-on on the bank channel with the note of the button
and a velocity that encodes mode and colour. The layout is the one the
official Midicraft plugin uses and was confirmed on the ENC (velocity 15 shows
dark CTB):

| Velocity | Meaning |
| --- | --- |
| `0` | off |
| `1–15` | static dark, palette index added (`1 + index`) |
| `17–31` | static bright, palette index added (`17 + index`) |
| `33–47`, `49–63`, `65–79` | complementary, flashing, device feedback (not used) |

Palette order (index 0–14): white, red, orange, yellow, yellow-green, green,
sea-green, cyan, lavender, blue, violet, magenta, pink, CTO, CTB.
Configuration uses lower-case names without hyphens (`yellowgreen`,
`seagreen`, `cto`, `ctb`) for `fallback_color` and colour tables. The encoder
clicks (notes 55–59) and the faders of the MIDICRAFT.ENC have no LEDs and
therefore stay dark.

`asl-mk2` sends `9F 7F 7F` once after the device was opened, then per LED two
note-ons on the button's note: channel 1 carries the brightness, channel 2 the
ASL colour index. The index is RGB with two bits per channel
(`16·R + 4·G + B`, each 0–3; bit 6 is ignored, so 63 and 127 are both white).
The default table was checked on the device: white 127, red 48, orange 52,
yellow 60, yellowgreen 44, green 12, seagreen 14, cyan 15, lavender 43,
blue 3, violet 35, magenta 51, pink 59, cto 62, ctb 47. `colors` overrides
single entries:

```toml
[profiles.asl-mk2-e4b3.led_feedback]
protocol = "asl-mk2"
led_notes = [9, 10, 11]
colors = { blue = 80 }
```

A button LED belongs to one function. The notes used by `[led]` (`note`,
`fine_note`, `nipple_note` on the `[led]` device) cannot be feedback targets at
the same time; `--check-config` rejects such a configuration and names both
fields. On the ASL MK2-E4B3 only the three buttons (notes 9–11) have LEDs and
`[led]` uses all of them by default, so executor feedback on the ASL needs
`[led] enabled = false` (or the button's playback target removed).

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

MIDI devices use `notes`, `midi_encoders` and `midi_values` instead:

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

[[profiles.midicraft-enc.midi_values]]
control = "mc_fader_1"
note = 70
kind = "fader"
```

`notes` maps a MIDI note number (`0…127`) to a logical control. A note-on with
velocity greater than `1` is a press; velocity `1` or a note-off is a release.
`midi_encoders` maps exactly one note per encoder; the velocity selects the
direction, so every note-on counts as one detent and the note-off is ignored.
`cw_velocity`/`ccw_velocity` must differ and lie between `1` and `127`.
`direction = -1` swaps the two directions without touching the profile.

`midi_values` maps a note to an absolute value (`kind = "fader"` or
`"encoder"`). Every note-on becomes a value between `0.0` (velocity `0`) and
`1.0` (velocity `127`); the note-off is ignored and never produces a key
release. A note may be used in only one of `notes`, `midi_encoders` and
`midi_values`, and encoder IDs are unique across all profiles.

Each configured MIDI device gets its own permanently open raw-MIDI handle.
Opening or closing one device does not affect the others, and the handle is not
reopened per message. A note may not be used as both a button and an encoder.

The verified ASL layout is:

| Note | Meaning |
| --- | --- |
| 1–4 | Encoders 1–4, one note per detent; velocity `127` = right, `1` = left |
| 5–8 | Encoder push buttons 1–4 |
| 9–11 | The three standalone buttons |

So `cw_velocity = 127` and `ccw_velocity = 1` are correct for this hardware;
use `direction = -1` if a clockwise turn should decrement.

The verified MIDICRAFT ENC layout (USB `04d8:e78c`, MIDI channel 1) is:

| Note | Meaning |
| --- | --- |
| 55–59 | Encoder clicks 1–5 (flash) |
| 60–64 | Absolute encoders 1–5 (`midi_values`, `kind = "encoder"`) |
| 65–69 | Button row below the encoders (flash) |
| 70–74 | Faders 1–5 (`midi_values`, `kind = "fader"`) |
| 75–79 | Middle button row (flash) |
| 80–84 | Bottom button row (flash) |

Both faders and encoders send their absolute position, not a relative delta.
The device must be the only reader of `/dev/snd/midiC*`; repeatedly opening and
closing the raw-MIDI node can leave it silent until the next USB enumeration.
`ma2pi` keeps the handle open for the daemon lifetime.

The shipped `config.toml` assigns the ENC to executors like this (all `page =
"current"`):

| Control | Note | Target |
| --- | --- | --- |
| `mc_fader_1…5` | 70–74 | Exec 1–5, `fader` |
| `mc_encoder_1…5` | 60–64 | Exec 6–10, `fader` |
| `mc_click_1…5` | 55–59 | Exec 6–10, `button = 1` |
| `mc_row1_1…5` | 65–69 | Exec 1–5, `button = 2` |
| `mc_row2_1…5` | 75–79 | Exec 1–5, `button = 3` |
| `mc_row3_1…5` | 80–84 | Floating execs 101–105, `button = 1` |

A page change on the MIDICRAFT changes the MIDI channel and the note assignment
together. Page 2 was measured as channel 2 with a different map (encoder click 1
= note 0, fader 1 = note 15). The shipped profile therefore only contains the
measured bank 1 notes; all other banks are empty and are filled by the learn
mode. The bank is selected in the UI; it is not inferred from a device event.

| Model | Controls | Bank default |
| --- | --- | --- |
| `PUSH²` | 30 buttons | channel = bank number |
| `FADE²` | 5 faders, 20 buttons | channel = bank number |
| `TURN²` | 15 buttons, 15 pots | channel = bank number |
| `MIX²` | 5 faders, 15 buttons, 5 pots | channel = bank number |
| `ENC` | 5 faders, 20 buttons, 5 absolute encoders | channel = bank number |
| `SPOT` | 5 faders, 10 buttons, 10 pots | channel = bank number |

#### Control inventory and banks

Devices with freely assignable notes declare their physical controls first and
bind notes per bank later. This keeps the surface and the learn mode usable
before the first note is learned:

```toml
[[profiles.midicraft-enc.controls]]
id = "mc_fader_1"
kind = "fader"          # button | fader | poti | encoder | relative-encoder
label = "Fader 1"       # optional

[[profiles.midicraft-enc.banks]]
number = 1
channel = 1             # optional, defaults to number
[profiles.midicraft-enc.banks.notes]
55 = "mc_click_1"
70 = "mc_fader_1"

[[profiles.midicraft-enc.banks]]
number = 2
channel = 2
[profiles.midicraft-enc.banks.notes]
0 = "mc_click_1"
15 = "mc_fader_1"
```

Up to 16 banks are allowed. Banks and channels are unique per profile; notes
must be unique within a bank and may repeat on another bank channel. A bank
entry requires the control inventory. Flat `notes`/`midi_encoders`/
`midi_values` cannot be combined with `banks`; they are treated as bank 1 on
channel 1. Without an inventory, controls are derived from the legacy
sections.

### `[layouts.<name>]`

A schematic surface for a profile. Cells reference controls from the profile:

```toml
[layouts.cherry]
profile = "cherry-g86"
columns = 18

[[layouts.cherry.rows]]
cells = [
  { label = "Ch Pg+", control = "ch_pg_plus", color = "blue", row_span = 2 },
  { label = "Pause", control = "pause_big", color = "green", col_span = 4, row_span = 2 },
  { label = "", col_span = 1 },
]
```

`color` is one of `green`, `blue`, `red`, `yellow`, `grey`, `black`, `white`.
`col_span`/`row_span` must be at least 1; a control may appear only once per
layout. A layout is optional; without one the table view stays available.

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
or `encoder_press = <slot>`, never more than one.

* A command is sent exactly once on key-down and never on key-up; the string is
  passed through unchanged, including semicolons.
* `screen_mode = true` toggles the encoders between attribute and screen mode.
* `encoder_press = <slot>` sends the real hardware encoder press (`gma.canbus.encoder(<index>, 0, true/false)`); the onPC applies its own resolution handling. Holding MA targets the screen encoder of that slot.

### `[mapping.playbacks.<control>]`

Maps a logical control to a grandMA2 executor through the Web Remote:

```toml
[mapping.playbacks."mc_fader_1"]
page = "current"  # or a 1-based page number
executor = 1      # 1-based, like the MA UI
kind = "fader"

[mapping.playbacks."mc_click_1"]
page = 1
executor = 1
kind = "button"
button = 1        # 1..3

[mapping.playbacks."mc_encoder_1"]
page = "current"
executor = 2
kind = "fader"
accelerated = true  # optional, only for absolute encoders
```

`executor` is 1-based in the configuration and is converted to the 0-based
`execIndex` of `playbacks_userInput` in the frame builder. A numeric `page` is
converted to `pageIndex = page - 1`; `page = "current"` is sent as
`pageIndex = -1`, which addresses the executor on the currently active master
page (like the MA remote-input setting *Current Page on Master*). For input,
`ma2pi` does not need to know the page, so a page change on the MA takes effect
immediately; the optional executor feedback requests the current page the same
way. Button events send `pressed`/`released` and preserve their order.
Absolute values send `faderValue` between `0.0` and `1.0`; while several updates
are still queued for the same executor, only the last value is sent. A control
with a playback target is not additionally processed as a hardkey or command.

`accelerated = true` is optional and only allowed on a fader target whose
control is an absolute encoder in the profile. It keeps slow turns at 1:1 and
amplifies fast turns; see `[mapping.value_acceleration]`. Physical faders and
relative encoders are never accelerated.

Executor feedback for LED-capable button targets is described in
`[feedback]`; a fader target still has no feedback and no PickUp.

`transport = "midi"` or `"web"` is optional. Without it, a button target goes
over MIDI remotes when `[midi_remote].enabled = true` and over the Web Remote
otherwise; fader targets always use the Web Remote. See `[midi_remote]`.

### `[midi_remote]`: executor buttons over MA MIDI remotes

The Web Remote always fires an executor. A console key, and a MIDI remote of the
MA, react to the command line instead: after `Store` (or Assign, Edit, Copy …)
from the Cherry, an ENC button stores into its executor. With `[midi_remote]`
enabled, `ma2pi` sends executor **buttons** as MIDI notes over RTP-MIDI to MIDI
remotes of the MA and keeps that remote table in sync over Telnet. Faders,
encoders, colours and executor states stay on the Web Remote (ADR-0024).

```toml
[midi_remote]
enabled = true
# host = "192.168.178.72"  # rtpMIDI computer, default: [ma2].host
port = 5004                # rtpMIDI session port (data port = port + 1)
channels = [15, 16]        # reserved for ma2pi, 128 targets per channel
sync = "auto"              # "auto" writes, "check" only compares, "off" trusts the show
telnet_port = 30000
```

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `enabled` | bool | `false` | Turns the MIDI path on; button targets without `transport` then use it. |
| `host` | string | `[ma2].host` | Computer running rtpMIDI. |
| `port` | int | `5004` | rtpMIDI session port; `port + 1` must be free too. |
| `channels` | list of 1–16 | `[16]` | MIDI channels owned by `ma2pi`. Entries on these channels are created, changed and **deleted** by the sync; entries on other channels are never touched. |
| `sync` | `"auto"`, `"check"`, `"off"` | `"auto"` | `auto` writes the difference and reads it back; `check` only reports deviations and sends nothing for missing remotes; `off` opens no Telnet and sends to every target. |
| `telnet_port` | int | `30000` | Telnet port of the MA. |

Every button target `(page, executor, button)` that any device and bank can
reach gets one note on the reserved channels, in sorted order, so the same
configuration always yields the same table. Banks with an executor offset
multiply the targets: the current MIDICRAFT configuration has 245 button
targets and needs two channels (`channels = [15, 16]`); `--check-config`
rejects a configuration that does not fit.

Setup on the onPC computer:

1. Install rtpMIDI (Tobias Erichsen), create a session (port 5004) and allow
   *Anyone* to connect. UDP 5004 and 5005 must be free; the screen helper
   therefore listens on UDP 5010.
2. In the onPC, set the MIDI input to the rtpMIDI session. The onPC has a
   single MIDI input: a directly connected MIDI device stops working unless it
   is routed into the session with rtpMIDI *Live routings*. This setting is
   local to the onPC and not stored in the show.
3. Enable Telnet: `Setup → Console → Global Settings → Telnet = Login Enabled`.
   `ma2pi` logs in with `[ma2].username` and its password. In
   `Setup → Console → Remote Inputs`, tab *MIDI Remotes*, `Enabled` and *CLI*
   must be on (Telnet: `cd 36`, `cd 2` shows `MidiRemotes 2 Enabled=On CLI=On`).
4. Save the show after the first sync; otherwise a show reload drops the
   remotes and `ma2pi` recreates them on the next sync.

The Status page shows the RTP-MIDI session (state, latency) and the last sync
(synced/targets, created, changed, removed, failed, time, error). A button is
only sent while the session is up and its remote is confirmed; otherwise it is
dropped and logged once per outage and target. `ma2pi` does not fall back to
the Web Remote, because that would fire the executor instead of feeding the
command line. Every Note-Off is repeated once after 20 ms, as RTP-MIDI runs
without recovery journal. A MIDI target on a covered slot of a wide executor is
not redirected: the MA treats it like the console key of that column.

### `[mapping]`: wide executors

A wide (combined) executor covers several slots; the console then has no
separate executor for the covered slots. On the Floating tile (executors from
101) the covered slot has no button either: the Web Remote sends the leading
`execIndex` with `buttonId 0` when you click the right half. `ma2pi` reads this
from the console and does the same: a button target on a covered Floating slot
(for example Exec 115 behind the 2-wide Exec 114) presses the leading executor,
button 1. In the fader view (executors up to 100) every slot of a wide executor
keeps its own executor, buttons and fader, so nothing is redirected there.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `combined_executors` | `"auto"` or `"off"` | `"auto"` | `auto` polls the executors of all playback targets and resolves covered Floating slots; `off` sends every target unchanged and polls nothing. |
| `topology_interval_ms` | int | `2000` | Poll interval, `500…10000`, while `[feedback]` is off. With feedback on, `[feedback] interval_ms` applies and the same answers serve LEDs and topology. |

Until the first answer has arrived, targets are sent unchanged. The LED of a
covered slot mirrors the leading executor. A playback target whose executor does
not exist on the polled page is logged once as a warning (control, page,
executor).

### `[mapping.device_banks.<device>]`

Bank layers override the global mapping for one device bank:

```toml
[mapping.device_banks.midicraft]
bank_size = 5          # default: number of fader controls, else buttons

[mapping.device_banks.midicraft.2]
ma_page = 2            # optional; disables the bank offset for this bank

[mapping.device_banks.midicraft.2.playbacks."mc_fader_1"]
page = "current"
executor = 20          # explicit, no offset
kind = "fader"

[mapping.device_banks.midicraft.2.keys."mc_row1_1"]
hardkey = "Goto"
```

Resolution per event: explicit bank entry, then the global target shifted by
`(bank - 1) * bank_size`, then nothing. Only executor targets are shifted;
button numbers and the MA page stay unchanged. A bank with `ma_page` sends
`Page <n>` once when the first event of a different bank arrives and applies no
offset. Playback overrides may be partial and inherit missing fields from the
global target. `accelerated` follows the same rules as in
`[mapping.playbacks]`.
Without PickUp, a page change can make an executor jump to the physical fader
position on the next movement. Park the faders before changing pages; button
LEDs follow the executor state through `[feedback]`, the faders themselves have
no feedback.

### `[[mapping.encoders]]`

| Key | Type | Meaning |
| --- | --- | --- |
| `id` | int | Must exist in a profile and be unique. |
| `slot` | int | Attribute slot 1–4 on the encoder page, exclusive with `attribute`. |
| `attribute` | string | Fixed attribute name, exclusive with `slot`. |

A `slot` encoder drives hardware encoder 1–4 of the onPC (`gma.canbus.encoder(0..3, …)`);
the onPC itself routes it to the current feature, so no page polling is needed.

In the web UI the Encoder table has a **Screen-Encoder** column per physical
encoder. Choose `Screen-Encoder 5`…`10` there to define what that encoder turns in
screen mode; `— keiner —` removes the target for its slot.

### `[mapping.screen_encoders]`

Numbers (5–10) of the onPC screen encoders, mapped onto the physical slots
1–4. They are sent as `gma.canbus.encoder(<number − 1>, …)`, exactly like
ShowCockpit. The shipped configuration maps them in reverse order to match the
wiring:

| Slot | onPC encoder |
| --- | --- |
| 1 | `8` |
| 2 | `7` |
| 3 | `6` |
| 4 | `5` |

While the section is missing, pressing the `screen_mode` key logs a warning and
leaves the encoders in attribute mode. The same targets are edited per physical
encoder in the web UI (Encoder table → *Screen-Encoder*); `— keiner —` removes
that slot from the section.

### `[mapping.encoder_acceleration]`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `curve` | string | `"none"` | `none`, `linear`, `exponential`/`exponentiell`. |
| `window` | float | `0.10` | Rate measurement window in seconds, `> 0`. |
| `max_multiplier` | float | `4.0` | Maximum acceleration, `>= 1`. |

### `[mapping.value_acceleration]`

Rate-based acceleration for absolute encoders on fader playback targets:

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `curve` | string | `"linear"` | `none`, `linear`, `exponential`/`exponentiell`. |
| `window` | float | `0.12` | Rate measurement window in seconds, `> 0`. |
| `slow_rate` | int | `2` | Up to this many changes per window stay 1:1, `>= 1`. |
| `fast_rate` | int | `10` | At this rate the maximum is reached, `> slow_rate`. |
| `max_multiplier` | float | `8.0` | Maximum acceleration, `>= 1`. |

Only controls with `accelerated = true` on their fader playback target use this
section; everything else is unaffected. The router keeps a virtual value per
control: the first event adopts the raw value, later events add the raw change
multiplied by the rate factor and clamp to `0.0`–`1.0`. Slow turns therefore
stay fine, while a fast turn covers the full executor range. Because the value
is virtual, the knob position and the executor can diverge after a fast turn;
without PickUp the next movement may jump after a restart or page change.

### `[mapping.encoder_resolution.attribute]`

`normal`, `fine`, `ultra` floats `> 0` (defaults `1.0`, `0.1`, `0.01`). Used by
encoders with a fixed `attribute` and by slot encoders. For slot encoders the
level is switched in the onPC: while the local modifier named in
`[mapping.encoder_resolution.modifiers] cycle` (shipped: `asl_button_2`) is held,
an encoder click cycles the attribute behind that slot Normal → Fine → Ultra →
Normal (native `encoder` frame with `resolution`) instead of sending the encoder
press. The daemon reads the attribute model once on connect and shortly after
each change; screen encoders have no resolution and only log a warning.

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
Doppelbelegung. Danach wird die neue Konfiguration **sofort** aktiviert – ein
Dienst- oder Pi-Neustart ist dafür nicht nötig. Die Verbindung kann dabei
abbrechen. Die Oberfläche nennt die Ziel-URL und verlangt, dass du sie öffnest
und dich dort erneut mit der PIN anmeldest; erst diese neue Sitzung bestätigt
die Änderung. Wird nicht innerhalb von 180 Sekunden bestätigt, stellt der Daemon
automatisch die vorherige Konfiguration wieder her. Kurze
Verbindungsabbrüche oder ein WebSocket-Reconnect lösen keinen sofortigen
Rollback aus. Der Pending-Zustand liegt unter
`/var/lib/ma2pi/network-pending.json` und überlebt einen Dienstneustart.

Schlägt auch die Wiederherstellung der vorherigen Konfiguration fehl, setzt der
Daemon die **Notfall-Adresse `192.168.178.254/24`** ohne Gateway und DNS. Sie
ist im Netz `192.168.178.0/24` gültig, sofern sie nicht bereits belegt ist. Ein
Client braucht für den Zugriff eine Adresse aus diesem Subnetz; in einem
anderen Netz ist die Notfall-Adresse ohne Client-Umkonfiguration nicht
erreichbar. Einen manuellen Notfall-Knopf gibt es nicht.

Unterstützt wird genau eine kabelgebundene IPv4-Schnittstelle. WLAN, IPv6,
VLAN, Bonding und mehrere gleichzeitig verwaltete Schnittstellen sind für die
Netzwerkseite nicht enthalten. Die Netzwerkeinstellungen stehen ausschließlich
bei NetworkManager und nicht in `config.toml`.

#### Rettungs-WLAN

Für den Fall, dass das Kabelnetz ausfällt, spannt der Pi einen eigenen WLAN-
Hotspot auf. Die Einstellungen liegen auf der Netzwerkseite unter
**Rettungs-WLAN**:

* SSID (Standard `ma2pi-recovery`) und Passwort (Standard `ma2pi-recovery`,
  8–63 Zeichen) sind änderbar. Das Standardpasswort sollte im Betrieb geändert
  werden.
* Der Hotspot ist standardmäßig aus. Er läuft mit WPA2 auf `wlan0`, vergibt
  Adressen aus `192.168.50.0/24` und ist unter `http://192.168.50.1:8080/`
  erreichbar. Die PIN-Sperre gilt auch dort.
* **Automatik**: Ist das Kabelnetz länger als 60 Sekunden ohne nutzbare
  Adresse oder liegt die Schnittstelle auf der Notfall-Adresse, schaltet der
  Pi den Hotspot ein. Nach 60 Sekunden stabilem Kabelnetz schaltet er ihn
  wieder aus. Ein manuell eingeschalteter Hotspot bleibt, bis du ihn ausschaltest.
* Der Hotspot trennt eine bestehende WLAN-Verbindung auf `wlan0`. Das ist
  beabsichtigt.

Unterstützt wird genau eine kabelgebundene IPv4-Schnittstelle. WLAN, IPv6,
VLAN, Bonding und mehrere gleichzeitig verwaltete Schnittstellen sind nicht
enthalten. Die Netzwerkeinstellungen stehen ausschließlich bei NetworkManager
und nicht in `config.toml`.

Die Berechtigung regelt `/etc/polkit-1/rules.d/50-ma2pi-network.rules`. Der
Benutzer `ma2pi` darf Systemprofile ändern, Verbindungen aktivieren und WLAN
nur im Access-Point-Modus freigeben (`wifi.share.open`, `wifi.share.protected`,
nötig für den Rettungs-Hotspot). WLAN-Scan und andere NetworkManager-Aktionen
bleiben gesperrt. Der Dienst läuft weiterhin unprivilegiert;
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

### Geräte und Mapping

Die Seite **Geräte/Mapping** zeigt alle konfigurierten Geräte mit ihren
logischen Controls; bei MIDI-Geräten erscheinen absolute Fader und Encoder mit
Note und Art. Die Tabellen bearbeiten:

* **Tasten** – Control, Aktion (Hardkey, Command, Screen-Modus, Screen,
  Encoder-Druck) und Wert.
* **Encoder** – Ziel-Slot oder festes Attribut sowie der Screen-Encoder 5–10.
* **Modifier** – Hardkey, der beim Halten mitgesendet wird.
* **Playback-Ziele** – Control, Art (`Button` oder `Fader`), Page, Executor und
  bei Buttons die Nummer 1–3. Page und Executor sind wie in der MA 1-basiert;
  als Page ist auch `current` erlaubt, dann folgt das Ziel der aktiven
  Master-Page.
  Ein Fader-Ziel hat keinen Button. Absolute Controls sind bereits als
  deaktivierte Zeile vorhanden; „Aktiv“ setzt das Ziel, „Deaktivieren“ entfernt
  es wieder.

Die Oberfläche prüft Page, Executor und Button vor dem Speichern und markiert
ungültige Felder. Serverseitig gelten dieselben Regeln. Ein Control mit
Playback-Ziel löst keinen zusätzlichen Hardkey oder Command aus. Ein
Executor-Feedback gibt es für Button-Ziele mit LED-fähiger Note über
`[feedback]`; Fader bleiben ohne Rückmeldung und ohne PickUp: Nach einem
Seitenwechsel springt ein Executor beim nächsten Faderwert auf die physische
Position.

Die Seite **Geräte** zeigt die schematische Fläche aus `[layouts.*]`, sofern für
das Profil eine hinterlegt ist; sonst bleibt die Tabelle sichtbar. Über die
Bankauswahl oben rechts wird die bearbeitete Bank gewählt. Ein Klick auf ein
Control öffnet die Zuweisung; mehrere Klicks sammeln eine Auswahl in
Klick-Reihenfolge. Der Dialog verteilt Executor-Nummern fortlaufend (Startwert
und Schrittweite, Vorschau vor dem Speichern) und schreibt bei Bank 1 in
`[mapping.keys]`/`[mapping.playbacks]`, bei höheren Bänken in die jeweilige
`[mapping.device_banks]`-Ebene. Der Schalter **Beschleunigt** erscheint nur für
absolute Encoder mit Fader-Ziel und nutzt dasselbe `accelerated`-Feld wie der
Mapping-Editor.

Der Learn-Modus auf der Geräte-Seite führt durch die noch ungebundenen Controls
der gewählten Bank. Das physische Bedienen liefert die Note; Ereignisse auf einem
anderen Kanal werden gemeldet und nicht übernommen. Erst **Speichern** schreibt
die gelernten Noten atomar in das Profil, **Abbrechen** verwirft sie. Bankgröße,
Kanal und optionale MA-Page der gewählten Bank lassen sich darunter bearbeiten.

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
* `--dump-input` prints normalised events live as `kind control value=… device=… bank=… note=…`; the note is shown for MIDI inputs so a bank binding can be verified directly.
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

Slot-Encoder sprechen wie ShowCockpit die Hardware-Encoder der onPC an
(per Mitschnitt verifiziert):

```json
{"requestType": "command", "command": "LUA 'gma.canbus.encoder(0,1,nil)'"}
{"requestType": "command", "command": "LUA 'gma.canbus.encoder(0,0,true)'"}
```

* Index = Encoder-Nummer − 1: Attribut-Encoder 1–4 → 0–3, Screen-Encoder 5–10 → 4–9.
* Die zweite Zahl sind ganzzahlige Schritte; Reste unter einem Schritt werden
  pro Slot vorgetragen. `(n,0,true)`/`(n,0,false)` ist der Encoder-Druck.
* Die onPC routet die Encoder 0–3 selbst auf das aktuelle Feature/Fenster; es
  gibt kein `presetTypes`-Dauer-Polling und keinen lokalen Bankzähler; die Seite wird
  nur beim Verbinden und kurz nach einem Auflösungswechsel gelesen.
* Ein Klick sendet den Encoder-Druck der onPC. Ist `asl_button_2` gehalten,
  schaltet der Klick stattdessen die Auflösung des Attributs in der onPC um
  (`encoder`-Frame mit `resolution`); Screen-Encoder haben keine Auflösung.
* Feste Attribut-Encoder (`attribute`) nutzen weiter den nativen
  `{"requestType": "encoder", "name": "PAN", "value": …}`-Request.
* Die Taste `screen_mode` schaltet auf die Screen-Encoder aus
  `[mapping.screen_encoders]` (Standard: Slot 1 → 8 … Slot 4 → 5).
* MA halten (Cherry-Logo) und dabei einen Encoder drehen oder drücken
  adressiert vorübergehend dieselben Screen-Encoder.

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
| Encoder moves too far | Hold ASL button 2 and click the encoder to cycle Fine/Ultra in the onPC, or lower `mapping.encoder_resolution.attribute`. |
| **Netzwerk** zeigt „nicht verfügbar“ | `nmcli` installiert, `systemctl status NetworkManager`, Polkit-Regel unter `/etc/polkit-1/rules.d/` vorhanden; Log mit `journalctl -u ma2pi`. |
| Keine kabelgebundene Schnittstelle | `nmcli device status`; nur `type ethernet` wird verwaltet, WLAN und virtuelle Geräte nicht. |
| Bestätigung nach IP-Wechsel schlägt fehl | Neue Ziel-URL öffnen, dort PIN erneut eingeben; das alte Cookie gilt nur für die alte Adresse. Nach 180 s rollt der Pi automatisch zurück. |
| Auch die alte IP ist nicht erreichbar | Der Daemon setzt `192.168.178.254/24` ohne Gateway/DNS. Client auf `192.168.178.x` stellen und die Adresse im Browser öffnen; die Notfall-IP darf nicht bereits belegt sein. |
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
