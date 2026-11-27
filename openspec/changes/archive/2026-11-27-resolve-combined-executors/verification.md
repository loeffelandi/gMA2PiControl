# Verification

## Messung 2026-11-26 (Web Remote, onPC `192.168.178.72`, Benutzer `svt`)

Mitgeschnitten über einen WebSocket-Hook im Browser (`send` und `message`);
eigene Anfragen über denselben Socket mit der Session des Web Remote.
Fixtures liegen in `tests/fixtures/playbacks/` (auf je drei Zeilen gekürzt).

### 1.1 Fixtures

| Datei | Anfrage | `iPage` | `tt` |
|---|---|---|---|
| `page1_fader.json` / `page1_button.json` | `pageIndex 0` | 1 | SERVICE |
| `page2_fader.json` / `page2_button.json` | `pageIndex 1` | 2 | SHOW |
| `current_fader.json` / `current_button.json` | `pageIndex -1` | **0** | fehlt |

`page2_button.json`: Item `iExec 113` (Exec 114) mit `combinedItems = 2`, die
Folge springt von `iExec 113` auf `iExec 115`; `iExec 114` fehlt.

### 1.2 `iPage`-Basis

| `pageIndex` | `iPage` | `tt` | Inhalt |
|---|---|---|---|
| 0 | 1 | SERVICE | Page 1 |
| 1 | 2 | SHOW | Page 2 |
| 2 | 3 | Remotes | Page 3 |
| **-1** | **0** | fehlt | Daten der aktuellen Master-Page (hier Page 2: gleiche Executor-Namen wie `pageIndex 1`) |

Ergebnis:

- Bei explizitem `pageIndex = N` ist `iPage = N + 1` (1-basiert).
- Bei `pageIndex = -1` liefert die MA die Daten der **aktuellen Master-Page**,
  setzt aber `iPage = 0` als Platzhalter (`-1 + 1`) und liefert keinen Seitennamen.
  Die tatsächliche Master-Page ist der `playbacks`-Antwort **nicht** zu
  entnehmen. Die frühere Annahme "0-basiert, tatsächliche Page" stimmt nur
  zufällig, wenn die Master-Page 1 ist.

### 1.3 Breite Fader-Executoren

Die Show enthielt keinen breiten Fader-Executor (Scan der Pages 1–12: einziger
Treffer mit `combinedItems > 1` ist Floating-Exec 114 auf Page 2). Mit
ausdrücklicher Freigabe wurde vorübergehend auf **Page 3, Exec 3** die Sequenz 256
zugewiesen und per `Assign Executor 3.3 /width=2` auf zwei Slots verbreitert;
danach per `Delete Executor 3.3` vollständig zurückgebaut (Exec 3.3 wieder leer,
`combinedItems = 1`, verifiziert über `playbacks`). Die ersten Versuche
(Gruppe 1, auf leerem Executor) ließen keine Breite zu: Breite gibt es nur für
Sequenzen und Effekte.

Antwort für `pageIndex 2`, `itemsType 2` (`page3_fader_wide.json`):

- Item `iExec 2` mit `combinedItems = 2`; **kein** Item für `iExec 3`.
- `executorBlocks` enthält **zwei** Blöcke (je ein Block pro Slot), jeder mit
  `button1..3` (`id` 0, 1, 2) und einem eigenen `fader`-Eintrag.
- `bottomButtons.items` enthält einen Eintrag.

Klicks der Web-Remote-Oberfläche auf die Buttons beider Blöcke (Frames
abgefangen und nicht gesendet, damit die Sequenz nicht ausgelöst wird):

| Klick | `execIndex` | `buttonId` |
|---|---|---|
| Block 1, `button3` (Rate1) | 2 | 2 |
| Block 2, `button3` (Select) | **3** | 2 |
| Block 2, `button2` (>>>) | **3** | 1 |
| Block 2, `button1`/unten (Go) | **3** | 0 |

Hinweis: Eine erste Lesart ("mehrere Fader, aber nur ein Master") war falsch und
ist durch die folgende Messung widerlegt.

Messung am Effekt `P/T FX Profile` (Page 3, Exec 6, vom Benutzer in der Show
angelegt, 2 breit, `page3_fader_wide_exec6.json`): `combinedItems = 2` an
`iExec 5`, kein Item für `iExec 6`, zwei `executorBlocks`. Jeder Slot hat eigene
Tasten **und** einen eigenen Fader mit eigener Funktion:

| Slot | `button1` | `button2` | `button3` | Fader |
|---|---|---|---|---|
| 1 (`iExec 5`) | GoBack | `<<<` | Rate1 | `XF` |
| 2 (überdeckt) | Go | `>>>` | Select | `LTP` |

Ein breiter Fader-Executor ist also mehrere vollwertige Executoren, die nur
gemeinsam konfiguriert werden. Es gibt keinen "Master", den man erkennen oder
bevorzugen müsste.

Ergebnis: Bei breiten **Fader**-Executoren adressiert die Oberfläche den
überdeckten Slot mit dessen **eigenem** `execIndex` und normalen `buttonId`
0–2. Die Konsole stellt den überdeckten Slot also weiterhin unter seiner eigenen
Nummer bereit. Eine Umleitung auf den führenden Executor ist hier nicht nötig
(und wäre falsch). Nur bei der **Floating-Kachel** (Button-Ansicht, genau eine
Taste je Executor) geht ein Klick auf den überdeckten Slot an den führenden
Executor (`execIndex 113`, `buttonId 0`, siehe unten). Dass die Konsole
Frames mit dem Slot-`execIndex` wirksam ausführt, ist für den **Fader**
geprüft: Auf Page 3, Exec 6 (Slot 2 hat `execIndex 6`) setzte
`{"requestType":"playbacks_userInput","execIndex":6,"pageIndex":2,"faderValue":0.5,"type":1}`
den `LTP`-Fader des überdeckten Slots von 0 auf 0.5 (Rücklesen per
`playbacks`-Antwort), der `XF`-Fader des führenden Slots blieb unberührt;
danach wieder auf 0 zurückgesetzt. Für Tasten des überdeckten Fader-Slots ist
die Wirkung nur aus den Oberflächen-Frames abgeleitet.

### Klick auf die breite Kachel

Rechte Hälfte der Kachel von Exec 114 (Button-Ansicht, Page 2) sendet
`{"requestType":"playbacks_userInput","execIndex":113,"pageIndex":1,"buttonId":0,"pressed":true,"released":false,"type":0}`,
identisch zur linken Hälfte.

## 7.2 Abnahme gegen die echte MA (ohne ENC-Gerät)

Die echten Klassen (`Ma2Client`, `ExecutorFeedback` mit `PlaybackPoller`,
`ExecutorTopology`, `PlaybackRouter`) liefen gegen die onPC `192.168.178.72`.
Ziel: `mc_click_1` auf Page 2, Exec 115, Button 1; LED-Feedback aus. Das
MIDICRAFT ENC war nicht angeschlossen, die Eingabe kam als `InputEvent`.

| `combined_executors` | Topologie für Exec 115 nach einem Zyklus | gesendeter Frame (Press) |
|---|---|---|
| `auto` | führend 114, überdeckt, bekannt | `execIndex 113`, `pageIndex 1`, `buttonId 0` |
| `off` | unbekannt (nichts abgefragt) | `execIndex 114`, `pageIndex 1`, `buttonId 0` |

Wirkung an der Konsole (Floating-Exec 114 "Profile Pos", Cue-Liste vorher
`4 X1 / 5 X2 / 6 Center Cross`):

- `auto`: ein Druck schaltet auf `5 X2 / 6 Center Cross / 7 Out` weiter, also Go
  auf Exec 114.
- `off`: der Frame mit `execIndex 114` ändert nichts (Cue-Liste unverändert).

Die Show wurde dabei verändert: Exec 114 steht durch die Abnahmeläufe ein paar
Cues weiter als vorher.

Die Abnahme am ENC selbst (Bank 3, `mc_row3_5`) entfällt (2026-11-27): Die
ENC-Tasten gehen jetzt über MIDI-Remotes (ADR 0024) und werden dabei nicht
umgeleitet; die Umleitung gilt für Ziele mit `transport = "web"`.
