# 0014. ASL MK2 E4B3 als MIDI-Gerät hinter der Input-Schnittstelle

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

Ergänzt [0003. Python 3.13 mit asyncio und evdev statt Node.js](0003-python-3-13-mit-asyncio-und-evdev-statt-node-js.md)

Ergänzt [0002. Wheel- und Encoder-Strategie](0002-wheel-und-encoder-strategie.md)

Related to [0019. Absolute MIDI-Werte und Executor-Ziele über den Web Remote](0019-absolute-midi-werte-und-executor-ziele-ueber-den-web-remote.md)

Related to [0021. Executor-Feedback über Playback-Polling und MIDI-Duplex-Ausgabe](0021-executor-feedback-ueber-playback-polling-und-midi-duplex-ausgabe.md)

Referenced by [22. Geraete-Baenke als MIDI-Kanaele und Bank-Offset](0022-geraete-baenke-als-midi-kanaele-und-bank-offset.md)

## Kontext und Problemstellung

Der ASL MK2 E4B3 wurde auf der Zielhardware mit `lsusb`, `--list-devices` und
`--dump-input` untersucht. Er meldet sich als USB-Audiogerät mit
MIDI-Schnittstelle (`04d8:e817`, ALSA-Karte 3, `/dev/snd/midiC3D0`) und legt
**kein** `/dev/input/event*`-Gerät an. Ein zusätzlicher CDC-Seriell-Knoten
(`/dev/ttyACM0`) liefert bei Tastendrücken keine Daten.

Damit kann der bisherige evdev-only-Ansatz aus ADR-0003 den ASL nicht lesen.
Gleichzeitig soll die Mapping-Engine unverändert mit derselben normalisierten
`InputEvent`-Schnittstelle arbeiten und der Event-Loop ohne zusätzliche Threads
auskommen.

## Entscheidungstreiber

* Beide Geräte in einem asyncio-Event-Loop ohne Threading
* Keine neue Laufzeit und möglichst keine zusätzliche Abhängigkeit
* Dieselbe `InputEvent`-Schnittstelle für Mapping, Hotplug und Freigabe
* Testbarkeit des Protokollparsers ohne Hardware
* Betrieb ohne Root-Rechte über udev-Regel bzw. `audio`-Gruppe
* Klare Fehlermeldung bei fehlenden Leserechten auf dem MIDI-Knoten

## Betrachtete Optionen

* Roh-ALSA-MIDI-Knoten mit `os.open` und `loop.add_reader`
* ALSA-Sequencer über `python-rtmidi` oder `mido`
* hidraw-Reader auf dem USB-Interface
* Serial-Protokoll über `/dev/ttyACM0`
* Externe Brücke (z. B. `aseqdump`) und Einlesen deren Ausgabe

## Entscheidung

Der Daemon liest den rohen ALSA-MIDI-Knoten direkt. `midi_input.py` enumeriert
`/dev/snd/midiC*`, ermittelt die USB-IDs aus `/sys/class/sound/card*/device/`
und öffnet den Knoten mit `os.open(..., O_RDONLY | O_NONBLOCK)`. Ein
`loop.add_reader`-Callback schiebt die Bytes in einen inkrementellen
3-Byte-Parser, der Note-On und Note-Off erkennt und alle anderen Nachrichten
ignoriert.

Der geführte Mitschnitt vom 2026-11-25 (je fünf Rastungen links und rechts pro
Encoder) ergab diese Belegung:

* Noten 1–4: Encoder 1–4 (links nach rechts), genau eine Note pro Rastung.
  Die Velocity trägt die Richtung: `127` = rechts, `1` = links. Ein Note-Off
  entsteht bei Drehung nicht.
* Noten 5–8: die Push-Tasten der Encoder 1–4 (Note-On `127`, Release `0`).
* Noten 9–11: die drei eigenständigen Tasten (Note-On `127`, Release `0`;
  Velocity `1` wird ebenfalls als Release akzeptiert).

Das Profil erhält dafür `notes` (Note → logisches Control) und
`midi_encoders` (`note`, `cw_velocity`, `ccw_velocity`, `direction`). Die
Gerätekonfiguration erhält `backend = "evdev" | "midi"`; `--list-devices`
zeigt beide Backends.

Der Zugriff erfolgt ohne Root über eine udev-Regel für `SUBSYSTEM=="sound",
KERNEL=="midiC*"` mit `GROUP="ma2pi"`; zusätzlich tritt der Dienst der
`audio`-Gruppe bei. Die systemd-Unit erlaubt `/dev/snd/midiC*` explizit, weil
`DeviceAllow` sonst nur die gelisteten Geräte freigibt.

### Konsequenzen

* Gut, weil der ASL ohne zusätzliche Abhängigkeit im selben Event-Loop läuft.
* Gut, weil der Parser klein, deterministisch und ohne Hardware testbar ist.
* Gut, weil Hotplug, Freigabe und Fehlerbehandlung dieselben Pfade wie bei
  evdev nutzen.
* Schlecht, weil ein eigener MIDI-Parser gepflegt werden muss.
* Schlecht, weil die Rohbelegung der Noten gerätespezifisch ist und im Profil
  gepflegt werden muss.
* Gut, weil die Richtung ohne zusätzliche Noten nur über die Velocity
  transportiert wird und dadurch acht Noten für vier Encoder genügen.
* Schlecht, weil ein falsch konfiguriertes Backend das Gerät still ungeöffnet
  lässt; deshalb nennt die Warnung Backend, Vendor-ID und Product-ID.

### Bestätigung

Bestätigt am 2026-11-25 auf der Zielhardware: Der geführte Capture ordnete
jede Taste und jede Encoder-Richtung genau einer Note zu, der Daemon öffnete
Cherry und ASL ohne Root, und `--dump-input` lieferte für jede Rastung genau
ein `encoder.N`-Delta (`+1` rechts, `-1` links).

## Vor- und Nachteile der Optionen

### Roh-ALSA-MIDI mit `add_reader`

* Gut, weil keine zusätzliche Abhängigkeit und kein Thread nötig ist.
* Gut, weil der Parser unabhängig von ALSA-Versionen testbar bleibt.
* Schlecht, weil Geräte-Enumeration und Fehlerfälle selbst implementiert
  werden müssen.

### ALSA-Sequencer über `python-rtmidi`/`mido`

* Gut, weil etablierte Bibliotheken Ports und Nachrichten kapseln.
* Schlecht, weil eine zusätzliche Abhängigkeit und ein eigener Thread oder
  Callback-Bridge in den Event-Loop nötig wären.
* Schlecht, weil die Sequencer-Ports zusätzliche Konfiguration und
  Berechtigungen benötigen.

### hidraw-Reader

* Gut, weil rohe USB-Reports ohne ALSA gelesen werden könnten.
* Schlecht, weil das Gerät kein hidraw-Interface mit nutzbaren Reports
  anbietet und die Report-Struktur nicht dokumentiert ist.
* Schlecht, weil die ALSA-Schicht die MIDI-Nachrichten bereits korrekt
  zusammensetzt.

### Serial über `/dev/ttyACM0`

* Gut, weil ein einfaches Zeilenprotokoll leicht zu parsen wäre.
* Schlecht, weil der Mitschnitt bei Tastendrücken keine Daten lieferte.
* Schlecht, weil die CDC-Schnittstelle offenbar nur Konfiguration transportiert.

### Externe Brücke wie `aseqdump`

* Gut, weil schnell erprobt.
* Schlecht, weil ein weiterer Prozess, dessen Ausgabeformat und dessen
  Fehlerbehandlung im Wirkpfad liegen.

## Weitere Informationen

* Hardware: `04d8:e817`, ALSA-Karte 3, `/dev/snd/midiC3D0`, Gruppe `audio`
* Roh-Mitschnitt vom 2026-11-25: Noten 1–4 mit Velocity `0x7f` (rechts) bzw.
  `0x01` (links), Noten 5–8 mit `0x7f`/`0x00`, Noten 9–11 mit `0x7f`/`0x00`
* Verwandt: ADR-0002, ADR-0003, ADR-0004, ADR-0005
