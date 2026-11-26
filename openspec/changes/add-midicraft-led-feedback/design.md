# Design

## Context

Siehe `proposal.md` für Motivation und `specs/executor-feedback/spec.md` für das
Verhalten. Ausgangslage im Code:

- `MidiManager`/`RealMidiHandle` (`ma2pi/midi_input.py`) öffnen je Gerät **einen**
  ALSA-Node mit `O_RDONLY` und lesen über `loop.add_reader`.
- `led_output.py` ist ein separater, fest auf das ASL-Protokoll verdrahteter
  Schreibpfad (`O_WRONLY` auf einem eigenen Gerät).
- `Ma2Client` (Web Remote) sendet über eine globale Queue mit Rate-Limiter und
  kennt bisher nur `login`, `command`, `keyname`, `encoder`, `presetTypes`,
  `playbacks_userInput` und `close`.
- Playback-Ziele liegen in `config.mapping.playbacks`; die Page kann
  `"current"` sein und wird für Eingaben als `pageIndex = -1` gesendet.
- Das MIDICraft-LED-Protokoll ist Note-On mit kodierter Velocity
  (Manual §8, verifiziert gegen den offiziellen gMA2-LUA-Script).

Die Web-Remote-Playback-Antwort ist nicht von MA Lighting dokumentiert; die
Feldnamen unten stammen aus zwei unabhängigen Implementierungen
(midimonster `backends/maweb.c`, locimation „MA2 Remote" Q-SYS-Plugin) und sind
live zu verifizieren.

## Goals / Non-Goals

**Goals:**

- Ein generischer Feedback-Task, der Executor-Zustand in LED-Zustand übersetzt
  und nur Differenzen ausgibt.
- Ein wiederverwendbarer MIDI-Schreibpfad auf demselben Gerät, ohne zweiten
  ALSA-Open.
- Farbwiedergabe aus der Web Remote ohne Showfile-Export.

**Non-Goals:**

- Kein Fader-Pickup, keine Fader-LEDs, kein Blinken außer hell/dunkel.
- Keine Änderung am ASL-LED-Pfad und an der Eingabeverarbeitung.
- Keine MA3-Unterstützung.

## Decisions

### D1: Feedback-Quelle ist Playback-Polling, nicht lokaler Schattenzustand

`ma2pi` fragt den Executor-Zustand über `requestType = "playbacks"` ab.
Alternativen:

- *Lokaler Schattenzustand* (merken, was wir per `playbacks_userInput` gesendet
  haben): kostenlos, aber falsch, sobald jemand an der Konsole oder im
  Command-Fenster schaltet — genau der Fall, für den Feedback da ist.
- *Showfile-XML per `getdata`* (wie der LUA-Script): liefert Farben exakt, aber
  erfordert Export, Dateipfad-Kenntnis und Aktualisierung nach jeder Änderung.

Polling ist erprobt und liefert Zustand **und** Farbe (`bC`/`bdC`).

### D2: Ein Duplex-Handle pro Gerät

`RealMidiHandle` öffnet den Node mit `O_RDWR` und bekommt `write_frame(bytes)`
mit `os.write` in einem `try/except OSError`. Alternativen:

- *Zweiter Handle nur zum Schreiben* (analog `LedOutput`): ALSA-Rawmidi erlaubt
  je Substream typischerweise nur einen offenen Handle; zwei FDs auf demselben
  Node riskieren `EBUSY` und uneinheitliches Hotplug-Verhalten.
- *ALSA-Sequencer (`python-rtmidi`/`alsaseq`)*: neue Abhängigkeit, evdev-freier
  Stack würde gesprengt.

Schreibfehler (Gerät weg, Puffer voll) werden geschluckt und gedrosselt
protokolliert; Eingabe läuft unabhängig weiter.

### D3: LED-Zustand als `(mode, color_index)` und zentrale Velocity-Tabelle

Intern `ExecutorState(running: bool, color: int | None)`. Ein neues Modul
`ma2pi/feedback.py` hält die Tabelle `MODE_BASE = {off: 0, dark: 1, bright: 15}`
und die 13 Palettennamen in fester Reihenfolge. `led_velocity()` liefert
Base + Color-Index.
Alternative: nur 124–127 (Gerätefarbe) senden — verworfen, weil die
Appearance-Farbe gewünscht ist; bleibt aber als möglicher späterer Modus
offen, ohne die Tabelle zu ändern.

### D4: `ExecutorFeedback` als eigener Task, gespeist über den Client

Neue Klasse `ExecutorFeedback`, gestartet in `run_daemon()` neben dem LED-Task.
Sie bekommt:

- eine Zielbeschreibung aus `config`: Menge von `(page, executor, control, note)`
  für Button-Ziele mit LED-fähiger Note, gruppiert nach Page,
- `Ma2Client.request_playbacks(...)`,
- `MidiManager.write(device, frame)`.

Der Client erhält eine Methode `request_playbacks(pages)` und leitet Frames mit
`responseType == "playbacks"` über eine `asyncio.Queue` an den Feedback-Task,
statt sie im Session-Loop zu verwerfen. Der Task ist zuständig für
Scheduling, Zustandsvergleich und Ausgabe; der Client bleibt transport-only.
Alternative: Polling im `MappingEngine` — vermischt Eingabe- und
Ausgabepfad und macht den Engine-Test aufwendig.

### D5: Request-Zuschnitt

Je Page eine Anfrage:

```json
{"requestType":"playbacks","startIndex":[<min>],"itemsCount":[<n>],
 "pageIndex":<page-1|-1>,"itemsType":[2|3],"view":2|3,
 "execButtonViewMode":2,"buttonsViewMode":0,"session":<id>}
```

- Executoren `< 100` sowie Executor `100` → `itemsType`/`view` 2,
  `itemsCount` auf den 5er-Block aufgerundet (MA gruppiert Executoren zu fünf).
- Floating-Executoren `> 100` → `itemsType`/`view` 3.
- `pageIndex = -1` für `"current"`; `iPage` der Antwort ist dann die
  tatsächliche Page und 0-basiert (Config-Page = `iPage + 1`). `iExec` ist
  ebenfalls 0-basiert (Executor = `iExec + 1`). Beides am 2026-11-26 live gegen
  die onPC verifiziert.
- Live-Format (2026-11-26): `isRun` kommt als `0`/`1`-Integer, nicht als
  Boolean; der Parser akzeptiert beides. Typ 2 liefert `executorBlocks`, Typ 3
  `bottomButtons` mit `iExecOff = 100`; die Items liegen verschachtelt in
  `itemGroups[*].items[*][*]`. `combinedItems` ist vorhanden (im Live-Test
  `1`).
- Enthält eine Page Ziele aus beiden Bereichen (`≤ 100` und `> 100`), werden
  **zwei** Anfragen pro Zyklus gesendet (Fader- und Button-View); die
  Backpressure gilt je Anfrage.
- **Backpressure**: pro Page höchstens eine offene Anfrage; nach Timeout
  (2 × Intervall, mindestens 1 s) wird erneut gefragt. Kein Polling, wenn keine
  LED-fähigen Button-Ziele existieren.
- Antwort: `itemGroups[*].items[*][*]` → je Item `iExec`, `isRun`, `bC`.
  `combinedItems` wird derzeit nicht ausgewertet; ob und in welcher Form es
  auftritt, klärt Task 1.1. Ziele auf Zweitspalten kombinierter Executoren
  bleiben bis dahin ohne Feedback. Antworten werden über `itemsType` und den
  angefragten Executor-Bereich dem Block zugeordnet; nicht passende Antworten
  werden verworfen. Antworten eines festen Page-Blocks treiben nie
  `page = "current"`-Ziele.

Alternative: MA-Subscriptions — nicht dokumentiert und in keiner der
Referenzimplementierungen genutzt.

### D6: Farbabbildung über RGB-Abstand

Hex (`#rrggbb`) → RGB → euklidischer Abstand zu den 13 Palettenfarben, kleinster
gewinnt. `bC` zuerst, sonst `bdC`, sonst `fallback_color`. Alternative:
HSV-Hue-Vergleich — bei sehr dunklen/entsättigten Farben instabiler und
schwerer testbar; die Palette ist klein genug für RGB-Abstand.

### D7: Fähigkeit explizit im Profil, nicht aus dem Gerätenamen geraten

`[profiles.<id>.led_feedback]` mit `protocol = "midicraft-v2"` und optional
`led_notes`. Damit kann später ein zweites Gerät ein anderes Protokoll
bekommen, ohne den Feedback-Task zu ändern.

### D8: Konfiguration global plus profil-lokal

`[feedback]` steuert Aktivierung/Timing/Fallback; das Profil steuert
Hardware-Fähigkeit. Alternative: alles unter `[led]` — `[led]` ist heute
ASL-spezifisch (Farbindizes, Nipple/Fine-Noten) und würde zwei Semantiken
mischen.

### D9: Ausgelieferte Belegung folgt dem Floating-Executor-Layout

`config.toml` bekommt eine vollständige Belegung des .ENC, damit Feedback ohne
Zusatzarbeit sichtbar ist:

| Control | Note | Ziel |
|---|---|---|
| `mc_fader_1..5` | 70–74 | Exec `1..5`, `kind = "fader"` |
| `mc_encoder_1..5` | 60–64 | Exec `6..10`, `kind = "fader"` |
| `mc_click_1..5` | 55–59 | Exec `6..10`, `kind = "button"`, `button = 1` |
| `mc_row1_1..5` | 65–69 | Exec `1..5`, `kind = "button"`, `button = 2` |
| `mc_row2_1..5` | 75–79 | Exec `1..5`, `kind = "button"`, `button = 3` |
| `mc_row3_1..5` | 80–84 | Exec `101..105`, `kind = "button"`, `button = 1` |

Alle Ziele nutzen `page = "current"`. Damit liegen die drei LED-Reihen auf
genau den Executoren, deren Zustand sie zeigen: die beiden Reihen um die Fader
auf den Buttons 2/3 von Exec 1–5, die untere Reihe auf den Floating-Executoren
101–105. Die Encoder (6–10) und ihr Klick bleiben ohne LED (bestätigt), sind
aber vollständig bedienbar. Belegung und Floating-Executoren sind
Show-Konvention, keine Spec — deshalb Konfiguration, nicht Code.

Alternative: Belegung nur dokumentieren — verworfen, weil der Change sonst ohne
sichtbare Wirkung ausgeliefert würde und der Live-Test kein Ziel hätte.

## Risks / Trade-offs

- **`pageIndex = -1`** → am 2026-11-26 live verifiziert: die Antwort enthält
  `iPage` 0-basiert und den Zustand der aktiven Master-Page.
- **Feldnamen `isRun`/`bC`/`itemGroups` können je MA-Version abweichen** →
  Parser tolerant halten (fehlende Felder = unbekannt, kein Absturz) und
  Rohantwort im Debug-Log ausgeben. Live: `isRun` als `0/1`-Integer.
- **Kombinierte Executoren** (`combinedItems`) haben ein `isRun` für mehrere
  Spalten → im Live-Test nur `combinedItems = 1` beobachtet; Werte > 1 werden
  nicht ausgewertet, Ziele auf Zweitspalten bleiben dann dunkel.
- **Floating-Executoren 101–105** kommen über `view = 3`/`bottomButtons` statt
  `executorBlocks` → Parser muss beide Formen kennen; ob `isRun` dort gesetzt
  ist, wird in Task 1.1 geprüft.
- **Polling-Last auf der onPC** → Intervall ≥ 100 ms, Default 250 ms, nur
  benötigte 5er-Blöcke, nur Button-Ziele, eine Anfrage je Page gleichzeitig.
- **Grau/Weiß erscheint als „weiß"** (MA-Default-Appearance) → bewusst
  akzeptiert; `fallback_color` und `off_state` erlauben Gegensteuern.
- **Encoder-Klick-Noten (55–59) haben keine LED** (am Gerät bestätigt) → sie
  stehen nicht in `led_notes`; ein Playback-Ziel auf einer Klick-Note bleibt
  ohne Feedback.
- **`O_RDWR` schlägt bei einzelnen Adaptern fehl** → dann bleibt Feedback für
  dieses Gerät aus (Warnung), Eingabe funktioniert weiter.

## Migration Plan

1. Der Parser-Default ist `enabled = false`; die ausgelieferte `config.toml`
   aktiviert das Feedback, weil Gerät, Ziele und `led_feedback` vorhanden sind.
2. `[profiles.midicraft-enc.led_feedback]` steht in der Beispielkonfiguration
   und bildet die 15 RGB-Noten ab; Encoder-Klicks bleiben ausgenommen.
3. Rollback durch `enabled = false` oder Entfernen des Blocks — kein
   Datenmodell, keine Persistenz.

## Open Questions

- Ob ein zweiter ALSA-Open nötig wird, falls `O_RDWR` auf dem Node scheitert
  (Fallback-Implementierung, gleiche Schnittstelle).
