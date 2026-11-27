# Tasks

## 1. Messung und Fixtures

- [x] 1.1 Live-Antworten der onPC (`192.168.178.72`, Web Remote) per
  WebSocket-Hook mitschneiden und als Fixtures unter `tests/fixtures/playbacks/`
  ablegen: Page 2 Button-Ansicht (`itemsType 3`, Exec 114 mit
  `combinedItems = 2`, ohne `iExec 114`) und Page 2 Fader-Ansicht
  (`itemsType 2`), dazu `current_*` (`pageIndex -1`), Page 1 und der breite
  Fader-Executor (`page3_fader_wide.json`). Verifizieren: Dateien sind gültiges
  JSON, ein Test lädt sie (Test folgt in 2.1).
- [x] 1.2 Messen, welche `iPage`-Basis die MA bei `pageIndex = -1` liefert
  (Master-Page auf bekannter Page, Antwort vergleichen) und in
  `design.md` D7 sowie `verification.md` des Changes festhalten. Ergebnis:
  `iPage = 0` als Platzhalter, Daten der aktuellen Master-Page, die echte Page
  steht nicht in der Antwort. Verifizieren: Messprotokoll in `verification.md`.
- [x] 1.3 Messen, ob ein breiter **Fader**-Executor `combinedItems > 1` in
  `itemsType 2` meldet und welche `buttonId` ein Klick auf die Buttons des
  überdeckten Slots sendet. Show vorübergehend verändert (Page 3, Exec 3, danach
  zurückgebaut). Ergebnis: Slot-`execIndex` mit normaler `buttonId`, keine
  Umleitung nötig; `design.md` D4 nachgezogen. Verifizieren: Messprotokoll in
  `verification.md`.

## 2. Parser und Topologie

- [x] 2.1 `parse_playbacks` in `ma2pi/feedback.py` um `combined`
  (`combinedItems > 1`) erweitern, ohne bestehende Felder zu ändern.
  Verifizieren: neuer Test gegen das Fixture aus 1.1 liefert `combined = {114: 2}`;
  alle bisherigen Tests in `tests/test_feedback.py` bleiben grün.
- [x] 2.2 `ma2pi/topology.py` mit `ExecutorTopology` (`update`, `resolve`,
  `invalidate`) anlegen, Schlüssel `(Seite, Bereich)` wie `_block_key`.
  Verifizieren: `tests/test_topology.py` deckt Zwei- und Drei-Breite,
  `combinedItems = 1`, unbekannten Bereich, Page-Wechsel und `invalidate` ab.
- [x] 2.3 Page-Zuordnung der Antwort in einer Funktion kapseln und
  `_belongs_to_block` sowie `_apply` darauf umstellen, gemäß Messung 1.2
  (fest `N` ↔ `iPage = N`, `current` ↔ `iPage = 0`); `_known_current_page` und
  die `fixed_pages`-Heuristik entfallen. Verifizieren: Tests mit den Fixtures:
  `iPage = 2` für Block Page 2 wird zugeordnet, `iPage = 1` nicht, `iPage = 0`
  nur dem `current`-Block; die bisherigen Feedback-Tests werden auf die gemessene
  Basis angepasst und die Änderung begründet.

## 3. Konfiguration

- [x] 3.1 `[mapping] combined_executors` (`auto`|`off`) und
  `topology_interval_ms` (500–10000) in `ma2pi/config.py` validieren,
  Fehlermeldungen nennen `mapping.combined_executors` beziehungsweise
  `mapping.topology_interval_ms`. Verifizieren: Tests in `tests/test_config.py`
  für Default, gültige Werte, `"maybe"` und `100`.
- [x] 3.2 Beide Schlüssel mit Kommentar in `config.toml` und im Abschnitt
  Executor in `README.md` dokumentieren. Verifizieren: `ma2pi --check-config`
  akzeptiert die ausgelieferte `config.toml`.

## 4. Poller

- [x] 4.1 Request-Schleife aus `ExecutorFeedback` in `PlaybackPoller`
  herauslösen (Backpressure, Timeout, Block-Zuordnung), `ExecutorFeedback` behält
  LED-Logik, Outbox und Pump. Verifizieren: alle Tests in
  `tests/test_feedback.py` laufen unverändert grün.
- [x] 4.2 LED-Blöcke und Topologie-Blöcke (nur Floating-Buttons, nur bei
  `combined_executors = "auto"`) als getrennte Anfragen mit eigenem Takt führen,
  Antworten an die LED-Anwendung bzw. an `topology.update` geben. Verifizieren:
  Tests prüfen (a) Feedback aus + `auto` pollt mit `topology_interval_ms`,
  (b) `off` pollt gar nicht, (c) Feedback an + `auto` fragt den Topologie-Block
  nur im Topologie-Takt ab, (d) Fader und Executoren unter 101 werden nicht
  abgefragt.
- [x] 4.3 Topologie bei Konfigurationstausch und `on_connection_lost` verwerfen,
  jede neue Antwort ersetzt den Eintrag (auch für `current`), und in
  `ma2pi/__main__.py` verdrahten. Verifizieren: Tests für beide Auslöser und für
  das Ersetzen durch eine neue Antwort; `tests/test_integration.py` bleibt grün.

## 5. Eingabe

- [x] 5.1 `PlaybackRouter` löst Button-Ziele im Floating-Bereich über
  `topology.resolve` auf (überdeckt → führender Executor, `buttonId 0`), bindet
  das aufgelöste Ziel für den Release und sendet bei unbekannter Topologie
  unverändert. Verifizieren: `tests/test_playback.py` mit Exec 115 →
  `execIndex = 113`, `buttonId = 0`, Release am selben Ziel, unbekannt →
  `execIndex = 114`, `combined_executors = "off"` → `execIndex = 114`.
- [x] 5.2 Ziele im Fader-Bereich auf überdeckten Slots (Button und Fader) bleiben
  unverändert. Verifizieren: Test mit dem Fixture `page3_fader_wide.json`: Button
  auf Exec 4 → `execIndex = 3`, `buttonId` unverändert; Fader auf Exec 4 →
  `execIndex = 3`.
- [x] 5.3 Ende-zu-Ende gegen `tests/mock_ma2.py`: Mock liefert die Fixture-
  Antwort, MIDI-Event für Bank 3 `mc_row3_5` erzeugt `execIndex = 113`.
  Verifizieren: neuer Test in `tests/test_integration.py` ist grün.

## 6. LED und Diagnose

- [x] 6.1 `_apply` übernimmt für Ziele auf überdeckten Slots den Zustand des
  Führenden; unbekannter Zustand sendet nichts. Verifizieren: Tests in
  `tests/test_feedback.py` für läuft, gestoppt (`dark` und `off`) und
  unbekannt.
- [x] 6.2 Diagnose nicht vorhandener Ziele im Poller (einmalig je
  `(control, page, executor)` bis zum Konfigurationstausch; leere Executoren
  ausgenommen). Verifizieren: Tests für fehlend, leer, Wiederholung und
  Konfigurationstausch; Warnung nennt Control, Page und Executor.

## 7. Abnahme

- [x] 7.1 `pytest` komplett ausführen. Verifizieren: grün, keine neuen Warnungen.
- [x] 7.2 Abnahme: Bank 3 `mc_row3_5` löst Exec 114 (Page 2) aus, Frame mit
  `execIndex = 113`, `buttonId = 0`; mit `combined_executors = "off"` wieder
  `execIndex = 114`. Erledigt gegen die echte MA mit den echten Klassen (siehe
  `verification.md`, 7.2). Der Lauf am ENC-Gerät entfällt (2026-11-27,
  Entscheidung des Betreibers): ENC-Tasten laufen jetzt über MIDI-Remotes und
  werden nicht umgeleitet; die Umleitung betrifft nur Ziele mit
  `transport = "web"`. Der Daemon loggt dazu `execIndex`, `pageIndex` und
  `buttonId` der Playback-Frames.

## Workflow follow-up

- Nach Review die Delta-Specs mit `openspec sync` in die Haupt-Specs übernehmen
  und den Change archivieren.
