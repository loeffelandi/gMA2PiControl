# gMA2PiControl — Cherry keyboard, ASL encoders and MIDICRAFT controllers for grandMA2 onPC

**gMA2PiControl** is a small Python 3.13 asyncio daemon for the Raspberry Pi
that maps a Cherry POS Keyboard G86-63400EUADAA, an ASL MK2 E4B3 encoder panel
and **MIDICRAFT controllers** (ENC, PUSH², FADE², TURN², MIX², SPOT) to
grandMA2 onPC. Executors, faders, encoders and keys are assigned in a web
interface; executor state is mirrored back onto the controller LEDs.

The main transport to onPC is the **Web Remote WebSocket API**
(`ws://<host>:<port>/?ma=1`). MIDI is used for controller input and LED output.
Optionally, executor buttons can be sent as MIDI notes over RTP-MIDI to MA MIDI
remotes (see [`[midi_remote]`](#midi_remote-executor-buttons-over-ma-midi-remotes))
so that Store, Assign and similar commands work like on a console. There is no
OSC or Showcockpit path to onPC, and no parameter unlock.

## Contents

- [How it works](#how-it-works)
- [MIDICRAFT support](#midicraft-support)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration reference](#configuration-reference)
- [Web interface](#web-interface)
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
Cherry keyboard ──── evdev ─┐
ASL encoders ─────┐         ├─→ normalised InputEvent ─→ MappingEngine ─→ Ma2Client ─→ onPC
MIDICRAFT ────────┴─ MIDI ──┘                          (held keys,        (queue,      WebSocket
                                                        chords, encoders,  rate limit)
                                                        executors, banks)
          ▲                                                                    │
          └──── LED frames (executor state polled from the Web Remote) ◄───────┘
```

* `ma2pi/config.py` — strict TOML schema, all references validated before start.
* `ma2pi/hid_input.py` — evdev enumeration, interface scoring, key/axis
  normalisation, hotplug and encoder decoding.
* `ma2pi/midi_input.py` — raw ALSA-MIDI enumeration, incremental note parser,
  button, fader and encoder normalisation for the ASL and MIDICRAFT devices,
  per-bank note maps, hotplug and permission handling.
* `ma2pi/mapping.py` — held-key register, modifier chords, CMD keys, encoder
  accumulation, acceleration and Normal/Fine/Ultra resolution.
* `ma2pi/ma2_client.py` — handshake, login, keepalive, reconnect, one global
  send queue with control priority, token bucket and backpressure guard.
* `ma2pi/frames.py` — exact JSON frame builders.
* `ma2pi/wheel_protocol.py` — historical wheel builder; the encoders now use
  only the native attribute format.

Releases and commands are never dropped. Encoder frames are coalesced per
target. On a connection loss the local key state is cleared and no stale
presses are replayed.

## MIDICRAFT support

MIDICRAFT controllers are USB-MIDI devices (vendor `04d8`; the ENC is
`04d8:e78c`). They appear as raw MIDI nodes (`/dev/snd/midiC*`) and are read
with `backend = "midi"`. Supported models:

| Model | Controls |
| --- | --- |
| `ENC` | 5 faders, 20 buttons, 5 absolute encoders (verified) |
| `PUSH²` | 30 buttons |
| `FADE²` | 5 faders, 20 buttons |
| `TURN²` | 15 buttons, 15 pots |
| `MIX²` | 5 faders, 15 buttons, 5 pots |
| `SPOT` | 5 faders, 10 buttons, 10 pots |

**How it works**

1. **Input.** Each device sends MIDI notes: buttons as note-on (press) and
   note-off, faders and absolute encoders as note-on with the velocity
   (0–127) as position. `ma2pi` keeps one raw-MIDI handle per device open for
   the daemon lifetime and turns the notes into logical controls such as
   `mc_fader_1` or `mc_row1_3`.
2. **Banks.** A MIDICRAFT page change switches the MIDI channel and the note
   assignment together and is not announced by the device. Each profile
   therefore declares its control inventory and one note map per bank
   (channel = bank number). Bank 1 of the ENC is shipped with measured notes;
   all other banks and the other models are filled by the **learn mode** in the
   web interface (**Devices** tab → *Learn notes*), which asks you to operate
   each still unbound control. The bank in use is selected in the UI.
3. **Mapping.** Controls are assigned to grandMA2 executors in the **Devices**
   or **Mapping** tab: faders and encoders to executor faders, buttons to
   executor buttons 1–3, or to hardkeys and commands. A target with
   `page = "current"` follows the active master page. Higher banks reuse the
   bank 1 assignment shifted by the bank size (for example bank 2 → executors
   6–10), unless a bank has its own override. Absolute encoders can be
   accelerated: slow turns stay 1:1, fast turns cover the whole range.
4. **Output.** Faders and encoders are sent over the Web Remote
   (`playbacks_userInput`), buttons over the Web Remote or, with
   `[midi_remote]`, as MIDI notes to the MA so that Store/Assign work.
5. **LED feedback.** `ma2pi` polls the executor state from the Web Remote and
   lights the 15 RGB buttons of the ENC in the executor's colour: bright when
   running, dark when stopped. Frames use the `midicraft-v2` protocol, are
   rate-limited per device (`frame_interval_ms`) and are re-sent per bank
   (`refresh_interval_ms`), because the ENC drops LED notes of banks it is not
   showing. Several MIDICRAFT devices and an ASL run side by side, each with
   its own protocol.

A device is added to `config.toml` like this (see
[`[devices.<name>]`](#devicesname) and
[`[profiles.<name>.led_feedback]`](#profilesnameled_feedback) for all keys):

```toml
[devices.midicraft-enc]
backend = "midi"
vendor_id = 0x04d8
product_id = 0xe78c
name_contains = "MIDICRAFT ENC"
profile = "midicraft-enc"

[profiles.midicraft-enc.led_feedback]
protocol = "midicraft-v2"
led_notes = [65, 66, 67, 68, 69, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84]
```

The note layout, the shipped executor assignment and the LED protocol are
documented in the configuration reference below. The device must be the only
reader of its `/dev/snd/midiC*` node.

## Requirements

* Raspberry Pi OS Trixie / Debian 13 (other Linux distributions work in
  principle; the deployment files target systemd and udev).
* Python **3.13** and `python3-venv`.
* grandMA2 onPC reachable over the network with Web Remote enabled.
* A non-root system user `ma2pi` with read access to `/dev/input/event*` and
  `/dev/snd/midiC*` through the supplied udev rules.
* NetworkManager with `nmcli` and Polkit for the **Network** page. The
  installer grants `ma2pi` only the NetworkManager actions needed to change and
  activate a system connection and to share WiFi as an access point (recovery hotspot).
* The Cherry keyboard, the ASL panel and/or MIDICRAFT controllers connected by
  USB.

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

### Switching the Pi off, and the SD card

The Pi has no power button. Use **Erweitert → Pi herunterfahren** or the
Cherry chord (see [`[power]`](#power)) and unplug it once the green LED is off.
To survive an occasional plain unplug anyway, `install.sh` also reduces writes
to the SD card:

* the systemd journal is kept in RAM (`/etc/systemd/journald.conf.d/50-ma2pi-volatile.conf`,
  `Storage=volatile`, 64 MB). Logs are lost on reboot or power loss; read them
  with `journalctl -u ma2pi -f` while the daemon runs. An old persistent journal
  stays in `/var/log/journal` until you delete it,
* the root file system is mounted with `noatime` (Raspberry Pi OS does this by
  default; otherwise `install.sh` adds it to `/etc/fstab` and keeps
  `/etc/fstab.ma2pi-backup`),
* an active `dphys-swapfile` is only reported, not changed.

The daemon itself writes only when you save in the web interface, and it does
so atomically (`fsync`, then rename).

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

### `[power]`

Shutting the Pi down cleanly, so it does not have to be unplugged while it is
writing to the SD card. Two ways trigger it: the **Pi herunterfahren** button on
the *Erweitert* page (`POST /api/power/shutdown`) and a key chord on the Cherry.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | Master switch for the button, the API and the chord. |
| `combo` | bool | `true` | Key chord on the keyboard. |
| `hold_controls` | list of strings | `["ma", "off"]` | 2–4 logical controls that must be held together. |
| `confirm_control` | string | `"please_big"` | Control that confirms; must not be in `hold_controls`. |
| `confirm_presses` | int | `2` | Presses of `confirm_control` needed, 1–5. |
| `console_notice` | bool | `true` | Report each step on the onPC with `Echo "…"` (System Monitor). |

With the defaults: **hold MA + Off and press Please twice** while holding both.
There are no time limits; letting go of MA or Off cancels. The key that
completes the chord is withheld from the onPC and every Please while the chord
is held is swallowed, so neither Off nor Please ever executes a command line. If
you let go before the first Please, the withheld key is passed on to the onPC as
an ordinary press (a quick tap of MA + Off therefore arrives when you release).
After one Please, cancelling drops the withheld key instead. Pressing any other
key while holding cancels as well. Learn mode and a lost device reset the chord.

The daemon runs `systemctl poweroff` as the unprivileged `ma2pi` user.
`deploy/50-ma2pi-power.rules` (installed by `install.sh`) grants exactly
`org.freedesktop.login1.power-off` (plus its multiple-sessions variant) and
nothing else. With `--dry-run` the request is logged but never executed, so it
is safe to try on a development machine. The Pi can only be started again by
cutting and restoring its power.

### Web interface and offline operation

The interface is served by the daemon as a static Svelte bundle from
`web/dist`. It is built on the development machine or in CI:

```bash
cd web
npm ci
npm run build
npm run check:offline
```

`npm run check:offline` checks the build for external `src`/`href` targets,
`url()` references, absolute `fetch`/WebSocket addresses and CDN, font and
telemetry hosts. The build contains only relative asset paths. In addition, the
built interface was loaded in a browser against a plain file server: all
requests went to the same local host (HTML, JavaScript, CSS) and there were no
external network calls. The missing API responses in this setup are expected
and only affect the live data, not loading the interface.

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
bank and with the bank's executor offset and overrides. A device like the
MIDICRAFT ENC only accepts LED notes of the bank it is switched to and does not
announce a bank switch, so such a profile sets `refresh_interval_ms` and every
bank is sent again once per interval. A `page =
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
from the console and does the same: a button target with `transport = "web"` on
a covered Floating slot (for example Exec 115 behind the 2-wide Exec 114) presses the leading executor,
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

## Web interface

The web interface is currently in German. This README names its pages and
buttons in English and gives the German label on first use.

### LAN access

The daemon serves the interface and the JSON API from the same process. The
default is `0.0.0.0:8080`; both values are set in the `[web]` section:

```toml
[web]
bind = "0.0.0.0"
port = 8080
pin_enabled = false
```

After startup the interface is available at `http://<pi-address>:8080/`.
Changes to `bind` or `port` only take effect after a service restart; the
interface points this out. The installer does not change the Pi's firewall. The
port must be reachable in the LAN but should not be forwarded to the internet.

### Network

The **Network** page (*Netzwerk*) manages the wired IPv4 interface through
NetworkManager. It shows the interface, connection state, mode, current address,
subnet mask, gateway and DNS. You can switch between **DHCP** and **Static**
(*Statisch*); in static mode you edit address, subnet mask, gateway and DNS. The
subnet mask is entered in dotted notation (for example `255.255.255.0`). Gateway
and DNS may stay empty; the interface then warns that no default route or DNS
server is set.

Before applying, the daemon checks address, mask, gateway, DNS and local
address conflicts. The new configuration is then activated **immediately**; no
service or Pi restart is needed. The connection may drop in the process. The
interface shows the target URL and requires you to open it and log in again with
the PIN; only this new session confirms the change. If it is not confirmed
within 180 seconds, the daemon automatically restores the previous
configuration. Short connection drops or a WebSocket reconnect do not trigger an
immediate rollback. The pending state is stored in
`/var/lib/ma2pi/network-pending.json` and survives a service restart.

If restoring the previous configuration fails as well, the daemon sets the
**emergency address `192.168.178.254/24`** without gateway and DNS. It is valid
in the network `192.168.178.0/24` as long as it is not already in use. A client
needs an address from this subnet to reach it; in any other network the
emergency address is unreachable without reconfiguring the client. There is no
manual emergency button.

Exactly one wired IPv4 interface is supported. WiFi, IPv6, VLAN, bonding and
several simultaneously managed interfaces are not part of the network page. The
network settings live exclusively in NetworkManager and not in `config.toml`.

#### Recovery WiFi

If the wired network fails, the Pi opens its own WiFi hotspot. The settings are
on the network page under **Recovery WiFi** (*Rettungs-WLAN*):

* SSID (default `ma2pi-recovery`) and password (default `ma2pi-recovery`, 8–63
  characters) can be changed. Change the default password in production.
* The hotspot is off by default. It runs with WPA2 on `wlan0`, hands out
  addresses from `192.168.50.0/24` and is reachable at
  `http://192.168.50.1:8080/`. The PIN lock applies there as well.
* **Automatic mode**: if the wired network has had no usable address for more
  than 60 seconds, or the interface is on the emergency address, the Pi turns
  the hotspot on. After 60 seconds of stable wired network it turns it off
  again. A manually enabled hotspot stays on until you turn it off.
* The hotspot disconnects an existing WiFi connection on `wlan0`. This is
  intentional.

Permissions are defined in `/etc/polkit-1/rules.d/50-ma2pi-network.rules`. The
user `ma2pi` may change system profiles, activate connections and share WiFi in
access-point mode only (`wifi.share.open`, `wifi.share.protected`, required for
the recovery hotspot). WiFi scans and other NetworkManager actions remain
blocked. The service still runs unprivileged; `ProtectSystem=strict` and
`NoNewPrivileges` stay active.

### Security model (v1)

* A simple PIN lock can protect the interface and the API. It is **off** by
  default and must be set in the configuration or on the **Advanced** page
  (*Erweitert*). As long as no PIN is set, the interface shows a warning banner
  at the top. The PIN is a LAN protection, not a replacement for TLS or user
  management.
* Writing API calls must carry `Content-Type: application/json` and the header
  `X-Ma2pi-Request: 1`. Plain form POSTs are rejected; this is CSRF protection,
  not a replacement for authentication.
* The MA2 password is write-only. Responses, logs and error messages contain
  neither the password nor its hash; the interface only shows whether a
  password is set. The PIN is never returned either.
* No CORS release: the interface is served same-origin.
* No external assets, fonts, CDNs or telemetry. The build is checked with
  `npm run check:offline` (see above).
* The PIN is held as an HTTP cookie session. After a service restart you have
  to log in again.
* Without a PIN, anyone in the LAN can power the Pi off (`POST /api/power/shutdown`
  needs `{"confirm": true}` and the request header, nothing more). Set a PIN or
  `[power] enabled = false` if that matters.

### Devices and mapping

The **Devices** (*Geräte*) and **Mapping** tabs edit the same assignment model.
Both load configuration and device list through a shared state: a change saved
in one tab is immediately visible in the other, device and bank are kept when
switching tabs, and only currently detected devices are offered. The same action
on the same control and the same scope produces exactly the same configuration
in both tabs.

**Controls.** Both tabs build the control list from the same source: inventory,
notes, absolute values, encoders and the notes of all banks. A control that is
known only to the inventory or to a single bank can therefore be selected in
both tabs.

* The **Devices** tab shows the schematic surface from `[layouts.*]` (a table
  without a layout). One click selects a control, several clicks collect a
  selection in click order; **Assign** (*Zuweisen*) opens the dialog. The
  dialog distributes executor numbers consecutively (start value and step, with
  a preview).
* The **Mapping** tab shows the same controls as a table with the effective
  assignment and its origin; **Edit** (*Bearbeiten*) opens the same dialog for a
  control. Bank size, channel and MA page of the selected bank are read-only
  there and are edited in the **Devices** tab.

**Actions in the dialog.** Hardkey, command, screen mode, select screen, encoder
click, playback target (page, kind `Button`/`Fader`, executor, button 1–3,
transport and, for absolute encoders, **Accelerated** (*Beschleunigt*)),
attribute encoder (slot or attribute name; for slots 1–4 additionally a screen
encoder 5–10 or "none") and modifier (hardkey or local). Unused fields of an
action are removed on save, so switching from hardkey to command leaves no
hardkey field behind. Page and executor are 1-based as in the MA, and `current`
is also allowed as a page. The transport `MIDI-Remote` only applies to buttons
and requires `[midi_remote] enabled = true`; a fader target does not store a
transport.

**Scope and origin.** Every assignment has a scope: **Global (all banks)**
(*Global (alle Bänke)*) or **Only this bank** (*Nur diese Bank*, an override in
`[mapping.device_banks]`). The interface shows the origin of the effective
assignment: *bank entry*, *global*, *inherited (global)* or *inherited with bank
offset* (for example, global executor 1 appears on bank 2 with bank size 5 as
executor 6). The dialog starts where the entry lives: an inherited target is
never silently saved as an explicit bank entry, "Only this bank" is a
deliberate decision and no longer follows the bank offset afterwards. The same
rule applies to bank 1: if a layer entry exists, it is changed, otherwise the
global level. When saving in the global scope, the dialog shows the raw value
that is stored without an offset.

**Removing.** **Remove assignment** (*Belegung entfernen*) deletes the entry in
the selected scope. A removed bank entry makes the inherited global assignment
visible again; a removed global entry disappears in all banks without an
override. Entries whose control no connected device offers are listed in the
**Mapping** tab under "Entries without a connected device" and can be removed
there.

**Precedence.** A **Precedence** badge (*Vorrang*) with an explanation marks
controls whose assignments hide each other, as the daemon resolves them: for
keys a layer key (`device_banks[...].keys`) wins over the playback target, a
playback target over a global key and modifier, a modifier over any key. Value
and encoder controls have no layer-key precedence and show no badge. Everything
is still saved; the badge only prevents an ineffective assignment from being
mistaken for an active one.

**Errors and conflicts.** A value rejected by the daemon (page, executor,
transport, screen encoder …) appears at the affected input field, and the
previous configuration stays active. If the configuration was changed elsewhere
in the meantime, saving reports a conflict and overwrites nothing; **Reload**
(*Neu laden*) adopts the new state, **Discard** (*Verwerfen*) closes the draft.

A control with a playback target does not trigger an additional hardkey or
command. Executor feedback exists for button targets with an LED-capable note
via `[feedback]`; faders have no feedback and no PickUp: after a page change an
executor jumps to the physical position on the next fader value.

**Two learn modes, one status.** Both tabs offer both modes and show the status
of the running session; only one runs at a time.

* **Detect control** (*Taste erkennen* / *Encoder erkennen*) returns the logical
  control of the next input. The result is highlighted in both tabs; **Assign**
  opens the dialog for it. Nothing is saved.
* **Learn notes** (*Noten anlernen*) walks through the still unbound controls of
  the device's selected bank. Operating the control physically supplies the
  note; events on a different channel are reported and not adopted. Only
  **Save** (*Speichern*) writes the learned notes atomically into the profile;
  **Cancel** (*Abbrechen*) discards them. From the **Mapping** tab the session
  can be started for a device and bank; **To Devices tab** (*Zum Geräte-Tab*)
  jumps to the progress.

Timeout and cancellation reset the status in both tabs; the buttons are usable
again afterwards. The status arrives over the WebSocket (`learn` and
`device_learn` events), not by polling.

### Applying changes

The **MA2**, **Devices/Mapping**, **Backups** and **Advanced** pages write
through the API. The **Network** page writes through NetworkManager and not to
`config.toml`; its change only becomes permanent after confirmation. Every
configuration change is validated on the server with the same rules as the
daemon start. On success the daemon writes the configuration atomically to
`/var/lib/ma2pi/config.toml`, releases held keys in reverse order, discards
pending encoder deltas and swaps the mapping without a service restart. If
credentials change, the daemon tests them first; an existing session stays
connected for pure mapping changes.

### Backups and restore

Backups are stored in `/var/lib/ma2pi/backups/`:

* `config-<timestamp>.toml` – created automatically before every write and on
  demand in the interface, rotated to the last 20 files.
* `last-good.toml` – the previously active configuration before the current
  one.

The **Backups** page lists the files, creates new ones and restores them after a
confirmation step. A restore is validated first; a damaged or schema-invalid
backup leaves the active configuration unchanged. After a restore with
different credentials the daemon tries to reconnect with the restored
credentials.

The full endpoint, payload and error reference is in
[`docs/api.md`](docs/api.md).

### Migration and rollback

On installation an existing `/etc/ma2pi/config.toml` is adopted once into
`/var/lib/ma2pi/config.toml` and backed up beforehand. The file in `/etc/ma2pi`
is left in place but is no longer written. The systemd unit uses
`StateDirectory=ma2pi` and `ReadWritePaths=/var/lib/ma2pi`; only this path is
writable under `ProtectSystem=strict`.

Rollback to the old version:

```bash
sudo systemctl stop ma2pi.service
sudo install -m 0640 -o root -g ma2pi /etc/ma2pi/config.toml /var/lib/ma2pi/config.toml
sudo systemctl start ma2pi.service
```

The backups in `/var/lib/ma2pi/backups` are kept. Alternatively, the previous
version of the unit and the code can be restored; the configuration in
`/etc/ma2pi` remains available as a starting point.

## Command line

```bash
python -m ma2pi --help
python -m ma2pi --config /etc/ma2pi/config.toml --check-config
python -m ma2pi --config /etc/ma2pi/config.toml --list-devices
python -m ma2pi --config /etc/ma2pi/config.toml --dump-input
python -m ma2pi --config /etc/ma2pi/config.toml --dry-run
python -m ma2pi --config /etc/ma2pi/config.toml --log-level DEBUG
```

* `--check-config` validates and exits 0, or prints `file:key: cause`
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

Like ShowCockpit, slot encoders address the hardware encoders of the onPC
(verified by capture):

```json
{"requestType": "command", "command": "LUA 'gma.canbus.encoder(0,1,nil)'"}
{"requestType": "command", "command": "LUA 'gma.canbus.encoder(0,0,true)'"}
```

* Index = encoder number − 1: attribute encoders 1–4 → 0–3, screen encoders
  5–10 → 4–9.
* The second number is whole steps; remainders below one step are carried over
  per slot. `(n,0,true)`/`(n,0,false)` is the encoder press.
* The onPC routes encoders 0–3 to the current feature/window itself; there is
  no continuous `presetTypes` polling and no local bank counter; the page is
  only read on connect and shortly after a resolution change.
* A click sends the encoder press to the onPC. While `asl_button_2` is held,
  the click instead cycles the attribute's resolution in the onPC (`encoder`
  frame with `resolution`); screen encoders have no resolution.
* Fixed attribute encoders (`attribute`) keep using the native
  `{"requestType": "encoder", "name": "PAN", "value": …}` request.
* The `screen_mode` key switches to the screen encoders from
  `[mapping.screen_encoders]` (default: slot 1 → 8 … slot 4 → 5).
* Holding MA (Cherry logo) while turning or pressing an encoder temporarily
  addresses the same screen encoders.

The ASL LEDs are already driven through the verified MIDI protocol (see
[`[led]`](#led)).

Capture procedure: open DevTools, filter for `?ma=1`, clear the messages,
perform the action, copy the complete JSON objects and store them as a fixture.
Record the result in a follow-up ADR to ADR-0002/0015.

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
installs `/etc/polkit-1/rules.d/50-ma2pi-network.rules` for the **Network**
page and `/etc/polkit-1/rules.d/50-ma2pi-power.rules` for shutting down; each
rule can be removed independently if the feature is not needed.

Rollback:

```bash
sudo systemctl disable --now ma2pi.service
sudo rm -f /etc/systemd/system/ma2pi.service
sudo rm -f /etc/udev/rules.d/99-ma2pi.rules
sudo rm -f /etc/polkit-1/rules.d/50-ma2pi-network.rules
sudo rm -f /etc/polkit-1/rules.d/50-ma2pi-power.rules
# optional, persistent journal again:
sudo rm -f /etc/systemd/journald.conf.d/50-ma2pi-volatile.conf
sudo systemctl restart systemd-journald.service
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
| Log: `Konfiguriertes Gerät … nicht gefunden` ("configured device not found") | `--list-devices`; compare `backend`, `vendor_id`, `product_id`, `name_contains`; the daemon retries with backoff. |
| Log: `Konfiguriertes MIDI-Gerät … nicht gefunden` ("configured MIDI device not found") | The ASL exposes `/dev/snd/midiC3D0`; check `lsusb` for `04d8:e817` and the udev rule for the `sound` subsystem. |
| Log: `Profil … referenziert nicht unterstützte Controls` ("profile references unsupported controls") | The selected interface lacks a key/axis from the profile; choose the keyboard interface or correct the profile. |
| Login fails | `password_file`/`password_env`, exact onPC user name, Web Remote enabled, `forceLogin`; an empty password is valid and must still be sent as the MD5 of the empty string. |
| onPC not reachable | The daemon stays alive and reconnects with exponential backoff; check `journalctl`. |
| Frames visible in dry-run but nothing happens | Check the exact `keyname` spelling (log at `DEBUG`) and that Web Remote accepts commands. |
| Encoder direction reversed | Set `direction = -1` in the profile encoder entry. |
| Encoder moves too far | Hold ASL button 2 and click the encoder to cycle Fine/Ultra in the onPC, or lower `mapping.encoder_resolution.attribute`. |
| **Network** page shows "not available" | `nmcli` installed, `systemctl status NetworkManager`, Polkit rule present in `/etc/polkit-1/rules.d/`; check the log with `journalctl -u ma2pi`. |
| No wired interface | `nmcli device status`; only `type ethernet` is managed, not WiFi or virtual devices. |
| Confirmation after an IP change fails | Open the new target URL and enter the PIN again there; the old cookie is only valid for the old address. After 180 s the Pi rolls back automatically. |
| The old IP is unreachable too | The daemon sets `192.168.178.254/24` without gateway/DNS. Set the client to `192.168.178.x` and open the address in the browser; the emergency IP must not already be in use. |
| Network change gets stuck | Check `/var/lib/ma2pi/network-pending.json`; an expired or interrupted state is rolled back on service start. |

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
