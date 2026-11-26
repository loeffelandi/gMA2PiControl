# Tasks

## 1. Vorab-Verifikation

- [x] 1.1 Gegen eine echte onPC `playbacks`-Anfragen mit `pageIndex = -1` für
  einen Block `≤ 100` und einen Block `> 100` senden und die Rohantwort
  protokollieren; prüfen, ob `iPage`, `isRun`, `bC`, `itemGroups`,
  `executorBlocks`, `bottomButtons` und `combinedItems` wie erwartet
  erscheinen. Zusätzlich klären: sind `iPage` (Seite) und `iExec` (Executor)
  0- oder 1-basiert (die Config ist 1-basiert), und liefert `executorBlocks`
  den Executor 100? Ergebnis im Design unter „Risiken" ergänzen. Verifikation:
  Rohantwort im Debug-Log, Feldliste dokumentiert.
  Ergebnis 2026-11-26: `iPage` und `iExec` sind 0-basiert, `isRun` ist `0/1`,
  `combinedItems = 1`, Typ 3 mit `iExecOff = 100`. Executor 100 kommt in der
  Live-Config nicht vor und bleibt unbestätigt; die Grenze bleibt `> 100`.
- [ ] 1.2 Am .ENC die 15 RGB-Noten prüfen: 65–69, 75–79 und 80–84 mit
  Velocity 1, 15 und 21 bespielen und das sichtbare Verhalten notieren.
  Ergebnis als `led_notes`-Liste (`[65,66,67,68,69,75,76,77,78,79,80,81,82,83,84]`)
  im Design/Config-Kommentar festhalten. Encoder-Klick-Noten 55–59 bleiben
  ausdrücklich außen vor (keine LED, am Gerät bestätigt).
  Verifikation: sichtbares Verhalten am Gerät, Liste dokumentiert.

## 2. MIDI-Ausgabepfad

- [x] 2.1 `RealMidiHandle` auf `O_RDWR` umstellen und `write_frame(data: bytes)`
  ergänzen, das `OSError` abfängt und höchstens einmal pro Gerät protokolliert.
  Verifikation: `tests/test_midi_input.py` deckt Schreiben auf Fake-FD und
  Fehlerfall ab; bestehende Lesetests bleiben grün.
- [x] 2.2 `MidiManager` um `send(device: str, data: bytes) -> bool` erweitern, das
  den Handle des konfigurierten Geräts nutzt und bei fehlendem Gerät `False`
  liefert. Verifikation: Unit-Test mit Fake-Handle prüft Zielauflösung und
  Rückgabewert.
- [x] 2.3 Schreibversuche im Dry-Run unterbinden und stattdessen loggen.
  Verifikation: Test mit `dry_run=True` zeigt Logeintrag und keinen Schreibaufruf.

## 3. Web-Remote-Playbacks

- [x] 3.1 `frames.playbacks_request(start, count, page, items_type, view,
  session)` ergänzen, inklusive `pageIndex = -1` für `"current"`.
  Verifikation: `tests/test_ma2_client.py` prüft alle Felder und die
  1-basiert → 0-basiert-Umrechnung.
- [x] 3.2 `Ma2Client` um `request_playbacks(...)` und eine Antwort-Queue für
  `responseType == "playbacks"` erweitern, ohne den Session-Loop zu blockieren.
  Verifikation: Test mit Fake-Transport liefert die Antwort über die Queue und
  der Login-Pfad bleibt unverändert.
- [x] 3.3 Timeout und Backpressure: höchstens eine offene Anfrage pro Page,
  erneute Anfrage nach `max(2 × interval_ms, 1000 ms)`. Verifikation: Test mit
  ausbleibender Antwort zählt gesendete Frames.
- [x] 3.4 `tests/mock_ma2.py` um konfigurierbare Playback-Antworten erweitern.
  Verifikation: bestehende Integrationstests laufen weiter, neuer Test nutzt
  die Antwort.

## 4. Konfiguration

- [x] 4.1 `[feedback]` parsen und validieren (`enabled`, `interval_ms` 100–2000,
  `off_state`, `fallback_color`). Verifikation: `tests/test_config.py` deckt
  Defaults, Grenzwerte und unbekannte Schlüssel ab; `--check-config` meldet
  Feldnamen.
- [x] 4.2 `[profiles.<id>.led_feedback]` parsen und validieren
  (`protocol = "midicraft-v2"`, optionale `led_notes`). Verifikation: Tests für
  gültiges Profil, unbekanntes Protokoll und Note außerhalb des Profils.
- [x] 4.3 `config.toml` und README um `[feedback]`, `led_feedback` und die
  Velocity-Tabelle ergänzen. Verifikation: `--check-config` läuft mit der
  ausgelieferten Konfiguration durch; README-Beispiel ist gültig.
- [x] 4.4 Playback-Ziele gemäß der Tabelle in Design D9 setzen
  (Fader 1–5 → Exec 1–5, Encoder 1–5 → Exec 6–10, Encoder-Klick → Button 1,
  Reihe 65–69 → Button 2, Reihe 75–79 → Button 3, Reihe 80–84 → Exec 101–105).
  Verifikation: `--check-config` ist grün und die Mapping-Seite zeigt alle
  Ziele mit Page `current` an.

## 5. Feedback-Engine

- [x] 5.1 In `ma2pi/feedback.py` die 13 Palettenfarben und
  `nearest_color(hex) -> int | None` implementieren. Verifikation:
  `tests/test_feedback.py` prüft exakte Treffer, Näherungen, `None` und
  ungültige Werte.
- [x] 5.2 `ExecutorState` und `led_velocity(state, off_state, fallback_color)`
  gemäß Velocity-Tabelle implementieren. Verifikation: Tabellentest für alle 13
  Farben in hell/dunkel sowie aus.
- [x] 5.3 `ExecutorFeedback`-Task: Ziele aus der Config gruppieren, Requests
  planen, Antworten über `itemsType`/Executor-Bereich dem Block zuordnen und
  nur Differenzen senden.
  Verifikation: Unit-Tests mit synthetischen Antworten prüfen Mapping,
  Seitenwechsel über `iPage`, gemischte feste/`current`-Pages, verworfene
  Fremdantworten und „nur Änderungen".
- [x] 5.4 Feedback-Task in `run_daemon()` verdrahten, bei fehlender
  MA-Verbindung pausieren und nach Reconnect den Zustand neu aufbauen.
  Verifikation: Integrationstest mit `mock_ma2` (Verbindungsabbruch, Reconnect)
  und Log-Ausgabe.

## 6. Integration

- [x] 6.1 Gesamte Testsuite und Web-Build ausführen. Verifikation:
  `.venv/bin/pytest -q` und `npm run build` in `web/` laufen fehlerfrei.
- [ ] 6.2 Live-Test mit onPC und .ENC: Exec 1–5 und Floating-Exec 101–105
  starten/stoppen, Buttons 2/3 der Exec 1–5 auslösen und Appearance-Farben
  ändern; LEDs müssen innerhalb von zwei Intervallen folgen, inklusive
  Seitenwechsel. Verifikation: beobachtetes Verhalten protokolliert,
  Abweichungen im Design nachgetragen.

## Workflow follow-up

- Change nach Review archivieren und die Deltas in die Haupt-Specs übernehmen.
