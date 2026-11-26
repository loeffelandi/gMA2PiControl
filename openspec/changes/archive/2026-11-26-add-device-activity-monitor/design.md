# Design

## Context

Der Status wird heute aus `Ma2Client`-Zählern gebaut
(`_status_snapshot` in `ma2pi/__main__.py`) und einmal pro Sekunde über den
`EventBus` als `{"type": "status"}` an alle Clients gesendet. Es gibt weder
Zeitstempel noch Gerätebezug; `last_frame_types` ist eine Liste von Strings.
Eingaben laufen über eine einzige `asyncio.Queue` in `_process_input`, Ausgaben
an Geräte über `MidiManager.send(device, data)` bzw. `LedOutput._write`, Ausgaben
an onPC über `Ma2Client._send_raw`.

Für ein sichtbares Blinken ist 1 Hz zu träge, für ein Ereignis pro Tastendruck
ist der Event-Bus zu empfindlich (`QUEUE_SIZE = 200`, langsame Clients werden
verworfen). Deshalb: schneller, gebündelter Delta-Event plus vollständiger
Resync im bestehenden Status.

## Goals / Non-Goals

**Goals:**

- Pro Gerät sofort erkennbar, ob RX und TX aktiv sind.
- Ein lesbares Terminal-Log mit Zeitstempel, Richtung, Gerät und Kurztext.
- Keine spürbare Last für Eingabeverarbeitung oder WebSocket.
- UI nutzt die bestehende Token-Schicht und bleibt offline-fähig.

**Non-Goals:**

- Persistenz, Historie über Neustarts, Diagramme, Export.
- Payload-Inhalte von MA-Befehlen oder Passwörtern im Log.
- Änderungen an Geräte-, Mapping- oder Feedback-Konfiguration.
- Feinzähler wie Bytes/s oder Latenz.

## Decisions

### 1. Ein Tracker, zwei Auslieferungswege

`ma2pi/activity.py` hält den gesamten Zustand:

```python
@dataclass(frozen=True)
class LogEntry:
    seq: int          # monoton, prozessweit
    ts: float         # time.time()
    direction: str    # "rx" | "tx"
    device: str       # Konfigurationsname oder "ma2"
    kind: str         # "note", "hardkey", "playbacksRequest", "led", ...
    summary: str      # kurzer, quotefreier Text

class ActivityTracker:
    def record(self, direction: str, device: str, kind: str, summary: str) -> None
    def snapshot(self) -> dict          # devices + kompletter Log-Ring
    def take_pending(self) -> list[LogEntry]
```

- **Ring:** `deque(maxlen=100)` für `snapshot()`.
- **Pending:** `deque(maxlen=500)` für den Delta-Versand; wird je Flush geleert,
  maximal 100 Einträge pro WebSocket-Event. Reste folgen im nächsten Tick.
- **Zähler:** je Gerät `rx`, `tx`, `last_rx`, `last_tx`; Gesamtzahlen seit
  Prozessstart, keine Raten. Die UI berechnet die Rate nicht, sie blinkt nur.
- **Reihenfolge:** `seq` wird unter einem `threading.Lock` vergeben, weil Hooks
  aus dem Event-Loop und aus MIDI-Threads kommen können.

### 2. Status = Resync, `activity` = Delta

`_status_snapshot` bekommt ein Feld `activity`:

```json
"activity": {
  "devices": {
    "cherry": {"rx": 120, "tx": 0, "last_rx": 1790000000.12, "last_tx": null},
    "midicraft": {"rx": 34, "tx": 12, "last_rx": 1790000000.9, "last_tx": 1790000000.88}
  },
  "log": [{"seq": 210, "ts": 1790000000.91, "direction": "tx",
           "device": "ma2", "kind": "keyname",
           "summary": "keyname · GO"}]
}
```

Neuer WebSocket-Event, alle 250 ms und nur bei neuen Einträgen:

```json
{"type": "activity", "data": {
  "devices": {"cherry": {"rx": 121, ...}},
  "entries": [{"seq": 211, ...}]
}}
```

- Der Status (1 Hz) liefert den vollständigen Ring; das Frontend ersetzt damit
  seinen Log-Stand (Resync nach Reconnect).
- `activity`-Events werden **nicht** pro Client gefiltert; alle bekommen dieselbe
  Delta-Liste. Ein Client, der kurz weg war, holt sich den Ring über den
  nächsten Status.
- Ein Flush-Task schläft 250 ms, prüft `bus.subscriber_count` und publiziert nur,
  wenn `take_pending()` etwas liefert. Das hält den Bus ruhig, wenn niemand
  zusieht.

Alternative: nur den 1-Hz-Status erweitern. Verworfen, weil die LED dann bis zu
einer Sekunde verzögert reagiert und Tastendrücke nicht als Aktivität erkennbar
sind.

Alternative: ein Event pro Eingabe. Verworfen, weil Halte-Tasten und schnelle
Encoder den Bus fluten und langsame Clients verlieren.

### 3. Hooks bleiben einzeilig

- **RX:** in `_process_input` direkt nach `queue.get()`:
  `activity.record("rx", item.device, item.kind, _describe(item))`.
- **TX onPC:** `Ma2Client` erhält einen optionalen Callback
  `on_frame: Callable[[str, dict], None] | None`, aufgerufen am Ende von
  `_send_raw` mit `kind` und Frame. In `__main__` wird er auf
  `record_ma2_frame` gesetzt: echte Frames erscheinen im Log unter `ma2`, ohne
  Gerätezähler; Polling-Frames (`playbacksRequest`) werden verworfen.
- **TX Gerät (MIDI):** `MidiManager` erhält `on_send: Callable[[str, bytes], None]`
  und ruft ihn nur bei erfolgreichem `write` auf. Summary: `LED note 12 = 255`
  bzw. `MIDI 3 Byte`.
- **TX Gerät (ASL-LED):** `LedOutput` erhält `on_write: Callable[[str], None]`;
  der Gerätename wird beim Öffnen aus `[led].device` bzw. dem erkannten
  MIDI-Gerät aufgelöst (`led.device_name`).

Die Callbacks dürfen nicht blockieren: sie schreiben nur in Deques und Zähler,
kein I/O, kein Logging.

### 4. Log-Format

Eine Zeile, maximal ~110 Zeichen, Monospace:

```
19:42:03.118  midicraft   rx  note 70 · velocity 127 · bank 1
19:42:03.121  ma2         tx  playbacksRequest
19:42:03.240  asl         tx  LED fine 1
```

- Zeit lokal, `HH:MM:SS.mmm` aus `ts`.
- Richtung als Badge `rx` (grün) / `tx` (amber).
- Gerät linksbündig, feste Spaltenbreite; auf schmalen Screens bricht die Zeile
  um statt horizontal zu scrollen.
- `summary` wird im Backend gebaut und enthält **keine** Kommandotexte,
  Passwörter oder Login-Daten. Nur Art, Note/Wert, Bank, Executor/Button/Seite.
- Leere Gerätekennung (z. B. bei `DeviceLost`) wird als `system` geführt.

### 5. UI: Gerätezeilen und Terminal

Bestehende Token bleiben; neu ist `--font-mono: ui-monospace, SFMono-Regular,
Menlo, Consolas, monospace` (Systemschrift, kein externer Download).

**Gerätezeile:**

```
●  ●   cherry        evdev · 046a:0000 · cherry-g86        erkannt
RX TX
```

- Zwei LEDs, `aria-hidden`, mit `title="RX – Daten vom Gerät"` bzw.
  `"TX – Daten zum Gerät"`; zusätzlich eine Legende über der Liste, damit die
  Bedeutung nicht nur über Farbe transportiert wird.
- RX nutzt `--success`, TX `--warning` (Richtungsfarbe, keine Warnsemantik).
- Blinken: Die Komponente merkt sich den letzten Zähler je Gerät/Richtung. Steigt
  er, wird für 400 ms die Klasse `pulse` gesetzt (CSS-Keyframes, Opazität und
  Glow). Bei `prefers-reduced-motion: reduce` entfällt die Animation, die LED
  bleibt statisch hell.
- Geräte, die keine TX-Quelle haben (Cherry), zeigen eine dauerhaft gedimmte
  TX-LED statt eines Fehlers.

**Terminal:**

- `<section class="terminal">` mit Kopfzeile `LOG · RX/TX · letzte 100`.
- `<ol>` mit neuesten Einträgen unten; Auto-Scroll ans Ende bei neuen Einträgen.
- Max-Höhe ca. 22 rem, `overflow-y: auto`, eigener Scrollbalken.
- Leerer Zustand: `Noch keine Aktivität.`
- Der Status-Snapshot ersetzt den Log-Stand; `activity`-Deltas werden über `seq`
  dedupliziert und auf 100 Einträge begrenzt.

### 6. Bestehende Kacheln bleiben, werden aber ruhiger

Die acht Kennzahlen bleiben als Grid erhalten (Verbindung, onPC, Generation,
Rate, Warteschlange, Frames gesamt, Encoder-Modus, Reconnects). Die Geräteliste
wandert aus der `<ul>` in die neue Zeilendarstellung; die Frame-Liste wird durch
das Terminal ersetzt.

## Risks / Trade-offs

- **Vier Hooks in fremden Lebenszyklen:** RX und onPC-Frame laufen im Event-Loop,
  MIDI-Sends und ASL-LED können aus Threads kommen. Der Tracker muss
  thread-sicher sein (ein Lock, keine `await`s).
- **Konflikt mit laufender Session:** `__main__.py`, `feedback.py` und
  `events.py` sind uncommitted; die Hooks müssen nach dem Commit der anderen
  Änderungen neu eingespielt werden.
- **Log-Rauschen:** Halte-Tasten und Playback-Polling erzeugen viele
  `playbacksRequest`-Zeilen. Gegenmaßnahme: Ring auf 100, Anzeige gedämpft;
  optional später ein Filter.
- **Delta-Lücke:** Ein Client, der genau während eines Flushs verbindet, kann
  einen Delta-Block verpassen; der nächste 1-Hz-Status repariert den Stand.
- **Datenschutz:** Summary-Texte werden bewusst auf Zähler und Ziele begrenzt.

## Migration

Keine Datenmigration. Ohne Aktivität bleiben die neuen Felder leer (`{}` bzw.
`[]`), ältere Clients ignorieren sie.
