# Proposal

## Why

Ein grandMA2 onPC-Arbeitsplatz ohne Command Wing lässt sich nur über Maus und
Bildschirmtastatur bedienen. Die vorhandene Hardware – ein Cherry POS Keyboard
G86-63400EUADAA und ein ASL MK2 E4B3 mit vier Drehgebern – soll stattdessen als
vollwertiges Programmier-Interface dienen. Der naheliegende Weg über MIDI
Remotes, OSC, Telnet oder Showcockpit scheitert an der fehlenden
Press/Release-Semantik: Modifier-Kombinationen wie MA+Fix (Desk Lock) und
Haltefunktionen wie Store (Store Options) benötigen ein echtes Key-Down und
Key-Up. Die grandMA2 Web-Remote-WebSocket-API bietet diese Semantik und ist als
einziger Transportweg verifiziert.

## What Changes

- Neuer Python-3.13-Daemon `ma2pi` für Raspberry Pi OS Trixie, ein
  asyncio-Event-Loop, kein Threading.
- `hid_input.py`: evdev-Erkennung beider Geräte, Filterung nach Vendor/Product
  und Geräteprofilen, Normalisierung auf logische Controls inklusive
  Hotplug-/Reconnect-Verhalten.
- `ma2_client.py`: WebSocket-Client gegen `ws://<onPC-IP>:80/?ma=1` mit
  MD5-Login, Session-ID, Keepalive, Reconnect mit Backoff, globaler Send-Queue
  und Rate-Limiter.
- `mapping.py`: TOML-basierte Mapping-Engine mit Hardkey-Press/Release,
  Modifier-Stack, CMD-Sequenzen, Encoder-Delta-Akkumulation, Beschleunigung und
  Auflösungsumschaltung Normal/Fine/Ultra.
- `wheel_protocol.py`: zentrale Frame-Builder für das native Wheel-Protokoll,
  Umschaltung CMD-Wrapper ↔ native Frames per Config-Flag.
- `config.toml` mit vollständigem Schema und Beispiel-Mapping für die
  wichtigsten MA2-Hardkeys (MA, Fix, Store, Clear, At, Thru, Please, Enter,
  Go+/Go-, Pause, Number-Block, X1–X20 optional).
- Betriebsartefakte: venv unter `/opt/ma2pi/.venv`, System-User `ma2pi`,
  udev-Regeln, gehärtete systemd-Unit, Setup-Skript.
- `--dry-run`, strukturiertes Logging, `tests/mock_ma2.py` und
  Integrationstests ohne Hardware.
- Dokumentation: README mit manuellem Wheel-Capture-Workflow, ADRs 0001–0007.

Nicht enthalten: Parameter-Unlock, Motor-Feedback, Fader-Wing-Unterstützung,
grafische Oberfläche, MIDI/OSC/Telnet/Showcockpit im Wirkpfad. Die LED-Anzeige
des Encoder-Modus am ASL ist enthalten (Task 5.8).

## Capabilities

### New Capabilities

- `hid-input`: Erkennung, Filterung und Normalisierung der beiden HID-Geräte,
  Geräteprofile, Hotplug und verlustfreie Key-Down/Key-Up-Weitergabe.
- `ma2-connection`: WebSocket-Login, Session-Lifecycle, Keepalive, Reconnect,
  globale Send-Queue, Rate-Limiting, Dry-Run und Graceful Shutdown.
- `mapping-engine`: Konfigurationsvalidierung, Hardkey-/CMD-Mapping,
  Modifier-Stack, Chord-Reihenfolge und Schutz vor hängenden Tasten.
- `encoder-control`: Encoder-Zielmapping, Delta-Akkumulation, Beschleunigung,
  Auflösungsumschaltung und CMD-Wrapper-/Native-Transport.

### Modified Capabilities

Keine – das Projekt ist greenfield, es existieren noch keine Haupt-Specs.

## Impact

- **Code:** neues Python-Paket `ma2pi/`, Tests unter `tests/`, Betriebsdateien
  unter `deploy/`.
- **Abhängigkeiten:** `evdev`, `websockets` (nur im venv); `tomllib` aus der
  Standardbibliothek; keine Cloud-Dienste.
- **System:** System-User `ma2pi`, udev-Regeln für `/dev/input/event*`,
  systemd-Unit mit Hardening, Schreibzugriff nur auf `/opt/ma2pi`.
- **Netzwerk:** ausgehende WebSocket-Verbindung zur onPC auf Port 80; keine
  eingehenden Ports.
- **Risiken:** zu hohe Frame-Raten können onPC blockieren (Rate-Limiter,
  ADR-0005); das native Wheel-Protokoll ist nicht dokumentiert (Capture,
  ADR-0002); die Geräteklasse des ASL MK2 E4B3 ist vor der Implementierung zu
  identifizieren (ADR-0006).
