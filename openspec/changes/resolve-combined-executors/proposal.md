# Proposal

## Why

Die grandMA2 kennt kombinierte (breite) Executoren: Ein Executor belegt mehrere
Slots, die überdeckten Slots existieren als eigene Executoren nicht mehr. Auf
dem MIDICRAFT ENC ist Bank 3 / `mc_row3_5` über den Bank-Offset auf Exec 115
gemappt, Exec 114 ist in der Show aber zwei breit. Live gemessen am
2026-11-26 (Web Remote, Page 2): Ein Klick auf die rechte Hälfte der breiten
Kachel sendet `execIndex = 113`, `buttonId = 0`; die `playbacks`-Antwort enthält
für Exec 114 `combinedItems = 2` und **kein** Item für Exec 115. `ma2pi` sendet
dagegen `execIndex = 114`, trifft damit nichts, und der Knopf bleibt wirkungslos.
Niemand merkt das: kein Fehler, keine Warnung, keine LED.

Das Muster ist allgemein. Die Zuordnung Control → Executor ist heute statisch
und blind gegenüber der Show. Jede Abweichung zwischen Mapping und tatsächlicher
Executor-Topologie (breite Executoren, nicht existierende Executoren, falscher
Bank-Offset) endet in einem stillen Nichtstun. Diese Klasse von Fehlern soll
`ma2pi` automatisch auffangen: breite Executoren korrekt auflösen und
Ziele, die ins Leere zeigen, sichtbar melden.

Beim Messen fiel außerdem auf: Bei expliziter Page-Anfrage (`pageIndex = N`)
antwortet die MA mit `iPage = N + 1`. Der Feedback-Code nimmt `iPage` als
0-basiert und würde Antworten für feste Pages verwerfen. Das gehört zur selben
Topologie-Auswertung und wird hier mit geklärt.

## What Changes

- Neues Modul `ma2pi/topology.py` hält pro Page und Bereich (Fader, Floating)
  die aus der `playbacks`-Antwort gelesene Breite der Executoren
  (`combinedItems`, fehlende Items) und löst einen Executor zu
  (führender Executor, überdeckt ja/nein) auf.
- Der Playback-Router löst Ziele vor dem Senden über die Topologie auf: Ein
  Button-Ziel auf einem von einer breiten **Floating-Kachel** (Exec ab 101)
  überdeckten Slot geht an den führenden Executor (`execIndex` des Führenden,
  `buttonId 0`), weil die Kachel nur eine Taste hat. In der **Fader-Ansicht**
  (Exec bis 100) bleibt der überdeckte Slot mit eigenen Buttons und eigenem
  Fader unter seiner Nummer adressierbar; dort wird nichts umgeleitet
  (gemessen, `verification.md`).
- Ein einziger Poller besitzt die `playbacks`-Antwortschlange und verteilt
  jeden Snapshot an Topologie und LED-Feedback. Er fragt auch dann ab, wenn das
  LED-Feedback aus ist, damit die Eingabe die Topologie kennt. Der Poller
  deckt alle Playback-Ziele ab (Button und Fader), nicht nur LED-Buttons.
- LED-Feedback übernimmt für einen überdeckten Slot Farbe und Laufzustand des
  führenden Executors.
- Ziele, die ein beantworteter Block weder als Executor noch als überdeckten
  Slot kennt, werden einmalig pro Ziel im Log gemeldet ("Ziel ... existiert auf
  Page ... nicht").
- Page-Zuordnung von `playbacks`-Antworten wird auf die gemessene Basis
  korrigiert: explizit `iPage = pageIndex + 1`; für `pageIndex = -1` liefert die
  MA die Daten der aktuellen Master-Page mit dem Platzhalter `iPage = 0`. Die
  Master-Page selbst ist der Antwort nicht zu entnehmen; die bisherige
  Ableitung `iPage + 1` entfällt.
- Neuer Schalter `[mapping] combined_executors = "auto" | "off"` (Default
  `"auto"`) und `[mapping] topology_interval_ms` (Default 2000) für die
  Abfrage ohne LED-Feedback.

## Capabilities

### New Capabilities
- `executor-topology`: Lesen, Zwischenspeichern und Auflösen der
  Executor-Topologie (Breite, überdeckte Slots, nicht vorhandene Executoren)
  aus den `playbacks`-Antworten sowie die Diagnose von Zielen ohne Executor.

### Modified Capabilities
- `executor-playback`: Button-Ziele auf von einer Floating-Kachel überdeckten
  Slots werden vor dem Senden auf den führenden Executor aufgelöst; Ziele in der
  Fader-Ansicht bleiben unverändert; die Aussage zur tatsächlichen Page bei
  `"current"` wird korrigiert.
- `executor-feedback`: Ein einziger Poller bedient Topologie und LEDs; LEDs
  überdeckter Slots spiegeln den führenden Executor; die Page-Zuordnung der
  Antworten folgt der gemessenen Basis.

## Impact

- Code: `ma2pi/feedback.py` (Poller herauslösen, `parse_playbacks`
  erweitern, `_apply`, `_belongs_to_block`), neu `ma2pi/topology.py`,
  `ma2pi/playback.py` (Auflösung vor `_client.playback_button` und
  `playback_fader`), `ma2pi/config.py` (zwei neue `[mapping]`-Schlüssel),
  `ma2pi/__main__.py` (Verdrahtung).
- Tests: `tests/test_feedback.py`, `tests/test_playback.py`, neu
  `tests/test_topology.py`, Fixtures aus der Live-Messung.
- Last auf der onPC: ein zusätzlicher `playbacks`-Poll alle 2 s je benötigtem
  Block, auch bei ausgeschaltetem Feedback. Abschaltbar über
  `combined_executors = "off"`.
- Abhängigkeit: keine neuen Pakete. Keine Änderung der Web-API.
- Nicht Teil dieser Änderung: Anzeige der Diagnose in der Web-Oberfläche,
  automatisches Umschreiben der Konfiguration, Umleiten von Zielen in der
  Fader-Ansicht.
