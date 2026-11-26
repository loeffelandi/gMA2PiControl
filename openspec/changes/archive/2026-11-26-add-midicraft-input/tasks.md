# Tasks

## 1. Vorbereitung und Architekturentscheidung

- [x] 1.1 Obsoletes Change `openspec/changes/add-midicraft-remote-import/`
  entfernen und prüfen, dass `openspec list` das obsolete Change nicht mehr
  führt und `openspec validate add-midicraft-input` keine Fehler meldet.
- [x] 1.2 ADR mit Status `Proposed` für absolute MIDI-Werte und Executor-Ziele
  über den Web Remote anlegen (`adr new`), Kontext/Entscheidung/Konsequenzen/
  Alternativen eintragen und prüfen, dass die Datei unter `docs/adr/` mit
  fortlaufender Nummer und Status `Proposed` existiert.

## 2. Konfiguration und Validierung

- [x] 2.1 `MidiValueProfile` (`control`, `note`, `kind`), `ProfileConfig.midi_values`,
  `PlaybackMapping` (`page`, `executor`, `kind`, `button`) und
  `MappingSettings.playbacks` in `ma2pi/config.py` ergänzen, inklusive
  `_reject_unknown` und TOML-Parsern; verifizieren mit
  `pytest tests/test_config.py`.
- [x] 2.2 Validierung ergänzen: Notes dürfen nicht gleichzeitig in `notes`,
  `midi_encoders` und `midi_values` stehen; Page/Executor mindestens 1; Button
  nur bei `kind = "button"` und 1–3; bei aktivierter LED-Ausgabe und mehr als
  einem MIDI-Gerät ist `[led].device` Pflicht. Jede Regel mit einem ablehnenden
  Testfall in `tests/test_config.py` abdecken.
- [x] 2.3 Beispielkonfiguration um `[devices.midicraft]`, `[profiles.midicraft-enc]`
  mit dem gemessenen Notenlayout, `[led].device = "asl"` und eine
  auskommentierte `[mapping.playbacks]`-Vorlage ergänzen; den Test
  `test_example_config_is_valid` auf die neue Geräteliste anpassen und
  `pytest tests/test_config.py` ausführen.

## 3. MIDI-Eingang

- [x] 3.1 `_normalise` in `ma2pi/midi_input.py` um absoluter Controls erweitern:
  Note-On erzeugt `InputEvent("value", control, velocity / 127, device)`,
  Note-Off wird ignoriert, unbekannte Noten werden einmalig protokolliert;
  Tests für Wert 0, 64, 127, Note-Off und unbekannte Note in
  `tests/test_midi_input.py` ergänzen und `pytest tests/test_midi_input.py`
  ausführen.
- [x] 3.2 Test für zwei gleichzeitig konfigurierte MIDI-Geräte mit
  `FakeMidiSource` ergänzen: getrennte Ereignisse, Verlust des zweiten Geräts
  ohne Unterbrechung des ersten, erneutes Öffnen nach Wiederanschluss;
  `pytest tests/test_midi_input.py` ausführen.
- [x] 3.3 README um das ENC-Layout (Notes 55–59, 60–64, 65–69, 70–74, 75–79,
  80–84; Kanal 1; absolut vs. Flash), den dauerhaft geöffneten Zugriff und die
  Pflicht zu `[led].device` bei zwei MIDI-Geräten ergänzen; prüfen, dass die
  Tabelle mit `design.md` übereinstimmt.

## 4. Playback-Aktionen und Transport

- [x] 4.1 `PlaybackButton` und `PlaybackFader` in `ma2pi/actions.py` sowie
  `playbacks_user_input_button` und `playbacks_user_input_fader` in
  `ma2pi/frames.py` ergänzen; exakte JSON-Frames inklusive 0-basierter
  Umrechnung und `session` in `tests/test_ma2_client.py` prüfen.
- [x] 4.2 Dispatch in `ma2pi/ma2_client.py` ergänzen, Buttons in der geordneten
  Control-Queue halten und Fader pro `(page, executor)` zusammenfassen (letzter
  Wert gewinnt); Tests für Reihenfolge, Coalescing und unveränderte Werte in
  `tests/test_ma2_client.py` ausführen.
- [x] 4.3 `PlaybackRouter` implementieren und in `__main__._process_input` vor
  dem `MappingEngine` aufrufen: Playback-Ziel hat Vorrang, Controls ohne Ziel
  bleiben unverändert; Tests für Vorrang, Fallback und unbekannte Ziele
  ergänzen und die betroffenen Tests ausführen.

## 5. Web-API und Oberfläche

- [x] 5.1 `ma2pi/web/devices.py` um `values` (Control, Note, Art) je Gerät
  erweitern; `tests/test_web_devices.py` um die ENC-Controls ergänzen und
  ausführen.
- [x] 5.2 `web/src/lib/api.ts` und `web/src/lib/MappingPage.svelte` um die
  Playback-Sektion erweitern: absolute Controls anzeigen, Page/Executor/Art/
  Button bearbeiten, Feldvalidierung, Patch auf `mapping.playbacks`;
  `npm run check` und `npm run test` im Verzeichnis `web/` ausführen.
- [x] 5.3 README-Abschnitt zum Mapping-Editor ergänzen (Control auswählen,
  Playback-Ziel setzen, Fader ohne PickUp) und prüfen, dass die beschriebenen
  Schritte zur Oberfläche passen.

## 6. Integration und Hardware-Abnahme

- [x] 6.1 Vollständige Suite ausführen: `pytest` und in `web/` `npm run check`,
  `npm run test` und `npm run build`; alle Fehler beheben.
- [x] 6.2 Hardware-Abnahme am Pi mit erreichbarer MA: je einen Button mit
  Button 1, 2 und 3 drücken, mehrere Fader und absolute Encoder bewegen und im
  Frame-Log `playbacks_userInput` mit korrekten `execIndex`, `pageIndex`,
  `buttonId` und `faderValue` prüfen; Ergebnis in
  `openspec/changes/add-midicraft-input/verification.md` festhalten.
- [x] 6.3 Sicherstellen, dass die Pi-Adresse die konfigurierte MA erreicht
  (Netzwerkroute oder Konfigurationshost), bevor 6.2 ausgeführt wird; die
  Abweichung im Abnahmebericht dokumentieren, falls sie bestehen bleibt.

## 7. Aktuelle Master-Page und Beispiel-Mapping

- [x] 7.1 `page = "current"` in Konfiguration, Frame-Builder, Router und
  Web-UI ergänzen; `pageIndex = -1` für die aktive Master-Page senden und mit
  Tests in `tests/test_config.py`, `tests/test_ma2_client.py` und
  `web/src/lib/MappingPage.test.ts` abdecken.
- [x] 7.2 Beispiel-Mapping für den ENC in `config.toml` und im
  Deploy-Merge anlegen (`mc_click_1..3`, `mc_fader_1`, `mc_encoder_1` auf
  `page = "current"`); `pytest tests/test_config.py` und
  `openspec validate --strict` ausführen.

## Workflow follow-up

- Change nach bestandener Abnahme archivieren und die Delta-Specs in die
  Haupt-Specs übernehmen.
- Danach LED-Feedback und PickUp als eigenes Change bewerten.
