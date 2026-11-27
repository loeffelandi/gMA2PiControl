# Design

## Context

Motivation und Messung stehen in `proposal.md`. Der Ist-Stand:

- `PlaybackRouter._resolve` (`ma2pi/playback.py`) berechnet aus Control, Bank
  und Offset ein festes Ziel `(page, executor, kind, button)` und sendet es
  über `playback_button` oder `playback_fader`. Er kennt die Show nicht.
- `ExecutorFeedback` (`ma2pi/feedback.py`) pollt `playbacks`, parst Antworten
  mit `parse_playbacks` und schreibt LEDs. Er ist der **einzige Leser** der
  Queue `client.playback_responses`, läuft nur bei aktivem Feedback und nur für
  LED-Button-Ziele. `combinedItems` wird nicht ausgewertet (archivierter
  Change `add-midicraft-led-feedback`, D5/Risiken: "Ziele auf Zweitspalten
  bleiben dunkel").
- Die Eingabe ist synchron und darf nicht auf Netzwerk warten.

Live-Messung am 2026-11-26, onPC `192.168.178.72`, Web Remote, Page 2:

- Klick auf die **rechte** Hälfte der breiten Kachel von Exec 114 (Button-
  Ansicht) sendet
  `{"requestType":"playbacks_userInput","execIndex":113,"pageIndex":1,"buttonId":0,"pressed":true,"released":false,"type":0}`
  — identisch zur linken Hälfte.
- Antwort (`itemsType 3`, `iExecOff 100`): Item `iExec 113` trägt
  `"combinedItems": 2`; die Item-Folge springt von `iExec 113` auf `iExec 115`.
  `iExec 114` fehlt. Alle anderen Items haben `combinedItems = 1`.
- Bei einem (vorübergehend angelegten) breiten **Fader**-Executor (Page 3,
  `itemsType 2`) meldet die Antwort ebenfalls `combinedItems = 2` und lässt das
  Item des überdeckten Slots weg, liefert aber zwei `executorBlocks` mit je
  `button1..3`. Die Oberfläche sendet für Buttons des zweiten Blocks den
  **eigenen** `execIndex` des überdeckten Slots mit normaler `buttonId`
  (`verification.md`, 1.3). Nur die Floating-Kachel (eine einzige Taste) wird
  auf den führenden Executor umgeleitet.
- Antworten tragen `iPage = pageIndex + 1` (`pageIndex 0` → `iPage 1`
  "SERVICE", `pageIndex 1` → `iPage 2` "SHOW"). `_belongs_to_block` und
  `_apply` rechnen mit `iPage + 1` und verwerfen damit Antworten für feste
  Pages.
- Bei `pageIndex = -1` liefert die MA die Daten der aktuellen Master-Page, aber
  mit `iPage = 0` und ohne Seitennamen (`verification.md`, 1.2). Die
  tatsächliche Master-Page steht **nicht** in der Antwort; die archivierte
  Aussage "0-basiert, tatsächliche Page" galt nur, solange die Master-Page 1
  war. `_known_current_page = iPage + 1` ist damit immer 1 und wertlos.

## Goals / Non-Goals

**Goals:**

- Ein Mapping-Ziel auf einen überdeckten Slot funktioniert ohne manuellen
  Override.
- Ein Mapping-Ziel, das ins Leere zeigt, erzeugt eine Log-Warnung statt
  Schweigen.
- Eine Quelle der Wahrheit (die Antwort der MA), keine Breite in der
  Konfiguration.
- Die Eingabe bleibt latenzfrei und fällt ohne Topologie auf das heutige
  Verhalten zurück.

**Non-Goals:**

- Anzeige der Diagnose in der Web-Oberfläche oder im Status.
- Schreiben oder Reparieren der Konfiguration.
- Ein eigenes Datenmodell für Executor-Namen, Cues oder Farben jenseits dessen,
  was LEDs brauchen.
- Umleiten von Zielen in der Fader-Ansicht: Dort bleibt der überdeckte Slot
  unter seiner eigenen Nummer adressierbar.

## Decisions

### D1: Topologie aus der Antwort, nicht aus der Konfiguration

`parse_playbacks` liefert zusätzlich `combined: dict[int, int]` (führender
Executor 1-basiert → `combinedItems`, nur Werte > 1). Überdeckt sind die Slots
`lead + 1 … lead + n - 1`. Als Plausibilitätsprüfung gilt: Fehlt das Item für
einen vermeintlich überdeckten Slot **nicht**, bleibt er ein eigener Executor
und wird nicht umgeleitet (Warnung im Debug-Log).

Alternative: Breite pro Show in der Konfiguration pflegen — verworfen, weil sie
bei jeder Showänderung auseinanderläuft und genau den stillen Fehler erzeugt,
den diese Änderung beseitigen soll.

### D2: Neues Modul `ma2pi/topology.py`

Reine Datenklasse ohne I/O:

- `ExecutorTopology.update(page, items_type, snapshot)` ersetzt den Eintrag des
  Bereichs.
- `ExecutorTopology.resolve(page, executor) -> Resolution` mit
  `lead: int`, `covered: bool`, `known: bool`.
- `invalidate(page=None)` für Page-Wechsel, Konfigurationstausch und
  Verbindungsverlust.
- Schlüssel `(seite, bereich)` mit Bereich `0` (Executor ≤ 100) und `100`
  (Floating), identisch zu `_block_key` in `feedback.py`. Für `"current"` ist
  der Schlüssel `("current", bereich)`: Die MA verrät die Master-Page nicht
  (siehe Context), also gibt es keine Seitenerkennung. Jede neue Antwort für
  `current` ersetzt den Eintrag; nach einem Seitenwechsel gilt die alte
  Topologie höchstens bis zur nächsten Antwort (ein Poll-Intervall).

Alternative: Topologie im Router halten — verworfen, weil Feedback sie ebenfalls
braucht und der Router sonst Antworten parsen müsste.

### D3: Ein Poller, zwei Verbraucher

Heute konsumiert `ExecutorFeedback._request_block` die Queue. Ein zweiter
Konsument würde Antworten stehlen. Deshalb wird die Request-Schleife
(`step`, `_request_block`, `_belongs_to_block`, Backpressure, Timeouts) als
`PlaybackPoller` herausgelöst. Er führt zwei Arten von Anfragen mit eigenem
Takt:

- LED-Blöcke (`build_feedback_targets`, nur bei aktivem Feedback) im Takt
  `feedback.interval_ms`; die Antworten gehen an `feedback.apply(snapshot, block)`.
- Topologie-Blöcke aus allen Floating-Button-Zielen (Executor ab 101), wenn
  `combined_executors = "auto"`, im Takt `topology_interval_ms` (Default 2000);
  die Antworten gehen an `topology.update(...)` und die Diagnose.

`ExecutorFeedback` behält LED-Logik, Outbox und Pump unverändert. Die Breite
einer Show ändert sich nur beim Editieren; 2 s bei einem Block je Bereich ist
für die onPC vernachlässigbar.

Live-Befund nach dem ersten Deploy: Die ursprüngliche Vereinigung beider
Blockarten lief im LED-Takt von 250 ms und erzeugte mit der Live-Config Blöcke
über 85 Fader- und 80 Floating-Executoren, sechs bis acht Anfragen pro Sekunde.
Fader-Ziele werden nie umgeleitet, die Topologie braucht sie nicht; deshalb
fragt sie nur noch Floating-Buttons ab und hat ihren eigenen Takt.

Alternative: Antwort bei Bedarf einmal pro Tastendruck abfragen (lazy) —
verworfen, weil der erste Druck dann 50–200 ms warten müsste oder wirkungslos
bliebe; D5 verlangt latenzfreie Eingabe.

Alternative: Topologie nur bei aktivem Feedback — verworfen, weil gerade
Installationen ohne LEDs (wie die aktuelle `config.toml`, `led_feedback.enabled =
false`) den Fehler haben.

### D4: Auflösung im Router, synchron und mit Cache

`PlaybackRouter` bekommt eine Referenz auf `ExecutorTopology`. Nach `_resolve`:

- `known = False` → Ziel unverändert, Debug-Log.
- Button, Executor im **Floating-Bereich** (> 100), `covered = True` →
  `Target(page, lead, kind, button=1)`: Die Floating-Kachel hat genau eine Taste,
  der überdeckte Slot hat keine eigene (gemessen: `execIndex` des Führenden,
  `buttonId 0`). Die Bindung für den Release (`self._pressed[...]`) speichert
  das **aufgelöste** Ziel, damit ein Topologiewechsel zwischen Press und
  Release nichts verwaist.
- Alles im **Fader-Bereich** (≤ 100), Button wie Fader, `covered = True` →
  unverändert senden: Die Konsole stellt den überdeckten Slot dort mit eigenen
  Buttons und eigenem Fader bereit (gemessen: Slot-`execIndex`, `buttonId 0–2`).

Die Regel hängt am Bereich, weil beide Fälle gemessen sind und sich
unterscheiden. Ein Ziel im Floating-Bereich mit `button > 1` wird auf dem
überdeckten Slot auf `button = 1` des Führenden gesetzt, da dort nur eine Taste
existiert.

Ein breiter Fader-Executor besteht aus mehreren vollwertigen Slots mit eigenen
Tasten und eigenem Fader samt Funktion (gemessen an Page 3, Exec 6: Slot 1 `XF`,
Slot 2 `LTP`). `ma2pi` adressiert den Slot, den der Benutzer mappt; dafür muss
nichts erkannt werden.

Alternative: überall auf den Führenden umleiten — verworfen, weil die Messung
zeigt, dass es im Fader-Bereich nicht nötig ist und die zweite Taste/der zweite
Fader sonst unbedienbar würden.

### D5: LED überdeckter Slots spiegeln den Führenden

`_apply` sucht für ein Ziel zuerst `snapshot.executors[target.executor]`; fehlt
es und `topology` nennt einen Führenden, wird dessen Zustand verwendet. Bleibt
auch der unbekannt, wird kein Frame gesendet (heutiges Verhalten für
unbekannte Executoren).

### D6: Diagnose nicht vorhandener Ziele

Beim Anwenden einer Antwort wird je Playback-Ziel geprüft: liegt der Executor im
abgefragten Bereich, ist er weder in `seen_executors` noch überdeckt → eine
Warnung je `(control, page, executor)`, bis zum nächsten Konfigurationstausch.
Leere Executoren stehen mit Item in der Antwort (`seen_executors`) und lösen
keine Warnung aus. Die Prüfung läuft im Poller und gilt für Button und Fader.

Abgrenzung: Executoren **außerhalb** des abgefragten Bereichs (zum Beispiel
Exec 400 bei `itemsCount 90` ab 100) lassen sich nur beurteilen, wenn der
Request-Zuschnitt sie einschließt. Der Zuschnitt (`build_feedback_targets`:
5er-Blöcke) wird für Topologie-Ziele wiederverwendet; ein Ziel ohne passenden
Block wird nicht geprüft.

### D7: Page-Basis der Antwort

Die Zuordnung Antwort ↔ Anfrage wird an einer Stelle gekapselt, gestützt auf die
Messung: Ein Block für feste Page `N` erwartet `iPage = N`; ein Block für
`"current"` erwartet den Platzhalter `iPage = 0`. Da die beiden Wertebereiche
(`0` gegen `≥ 1`) disjunkt sind, trennt der Vergleich Antworten für `current` und
feste Pages sicher, und `_known_current_page` samt `fixed_pages`-Heuristik in
`_belongs_to_block` entfällt. `_belongs_to_block` und `_apply` benutzen nur diese
Funktion. Ein Ziel mit `page = "current"` wird nur aus Antworten des
`current`-Blocks bedient.

Alternative: Antworten ohne Seitenvergleich annehmen — verworfen, weil sich
Antworten verschiedener Pages sonst vermischen.
Alternative: die Master-Page aus einer anderen MA-Quelle ableiten — nicht
belegt und für diese Änderung nicht nötig.

### D8: Konfiguration

`[mapping] combined_executors = "auto"|"off"` (Default `auto`) und
`topology_interval_ms` (500–10000, Default 2000), validiert in
`ma2pi/config.py` mit Feldnamen in den Fehlermeldungen. Kein Eintrag in der
Web-Oberfläche in dieser Änderung (nur `config.toml` und
Hinweis in `README.md`).

## Risks / Trade-offs

- **Default `auto` erhöht die Last auf der onPC auch ohne Feedback** → ein
  Block je Bereich, 2 s Intervall, `off` stellt das alte Verhalten her.
- **Erster Druck nach Page-Wechsel nutzt noch die alte Topologie** → die
  Master-Page ist nicht erkennbar, die nächste Antwort ersetzt die Topologie;
  Fenster ist höchstens ein Poll-Intervall. Akzeptiert und dokumentiert.
- **Fader-Bereich: Wirkung der Slot-Frames nur aus der Oberfläche abgeleitet** →
  Die Web-Remote-Oberfläche sendet dort den Slot-`execIndex`; wir ändern nichts
  und übernehmen damit genau das bekannte Verhalten. Ein ausgelöster Cue wurde
  nicht geprüft (Messung ohne Senden, um die Sequenz nicht zu starten).
- **LED überdeckter Fader-Slots ist eine Näherung** → der überdeckte Block hat
  eigene Button-Zustände (`executorBlocks[1]`); wir spiegeln `isRun` und Farbe
  des Führenden. Reicht für die LED-Logik, die nur `isRun` und Farbe kennt.
- **Bestehende Feedback-Tests nehmen `iPage` 0-basiert an** → sie werden auf die
  gemessene Basis angepasst (Task 2.3) und die Änderung wird begründet.
- **Warnungen können bei halb gebauten Shows rauschen** → einmalig je Ziel und
  Konfigurationsstand, nur Log.
- **Refactor des Feedback-Pollers berührt laufende Changes** →
  `add-per-device-led-protocols` und `fix-midicraft-led-output` ändern
  `feedback.py`; ihre Spec-Deltas überschneiden sich nicht mit diesem Change
  (geprüft), der Code muss beim Apply mit dem dann aktuellen Stand abgeglichen
  werden.

## Migration Plan

1. Messungen (Gruppe 1) und Fixtures zuerst.
2. Parser und Topologie, dann Poller-Herauslösung ohne Verhaltensänderung
   (bestehende Feedback-Tests müssen unverändert grün bleiben).
3. Router-Auflösung und LED-Spiegelung.
4. Default `auto` aktiv; Rollback über `combined_executors = "off"` in
   `config.toml`, kein Datenformat betroffen.

## Open Questions

- Soll die Diagnose später in `/api/status` und die Mapping-Seite? Bewusst
  außerhalb dieses Changes.
