# Tasks

## 1. Auflösungsziel im Screen-Modus

- [x] 1.1 Im `Ma2Client` einen gemeinsamen Resolver für das aktive Encoder-Ziel einbauen, den `EncoderSlot` und `ToggleFine` nutzen; `pytest tests/test_ma2_client.py` deckt Screen-Name, fehlenden Namen mit Warnung und unveränderten Attribut-Modus ab.

## 2. Screen-Encoder-Editor

- [x] 2.1 `MappingPage.svelte` um eine Screen-Encoder-Auswahl pro physischem Encoder erweitern, die `mapping.screen_encoders` lädt und beim Speichern belegte Slots setzt sowie geleerte Slots auf `null` patcht; `npm test -- MappingPage` prüft gesetzte und entfernte Ziele.
- [x] 2.2 `[mapping.screen_encoders]` in `config.toml` mit der onPC-Nummerierung 5–8 umgekehrt belegen (Slot 1 → 8, Slot 2 → 7, Slot 3 → 6, Slot 4 → 5); `pytest tests/test_config.py::test_screen_encoders_default_order` prüft die Reihenfolge.

## 3. MA + Encoder

- [x] 3.1 `EncoderSlot` um ein `screen`-Flag erweitern, im `Ma2Client` die Zielauflösung dafür öffnen und die Queue nach `slot`/`screen` getrennt coalescieren; `pytest tests/test_ma2_client.py` deckt forcierten Screen-Namen und getrennte Ziele ab.
- [x] 3.2 Im `MappingEngine` MA als temporären Screen-Modus auswerten, den `EncoderState` pro Delta-Block markieren und bei einem Moduswechsel zwischen Detents vorher flushen; `pytest tests/test_mapping.py` prüft MA + Encoder, Loslassen und getrennte Frames.
- [x] 3.3 Die rechte ASL-Taste (`asl_button_3`, Note 11) in `config.toml` auf den `NIPPLE`-Hardkey legen; `tests/test_config.py::test_rightmost_asl_button_is_nipple` und `test_rightmost_asl_button_sends_nipple` prüfen Zuordnung und Frames.

## 4. Dokumentation und Abnahme

- [x] 4.1 README und `config.toml` so aktualisieren, dass Default-Reihenfolge, Editor, MA-Halten und die Anpassbarkeit der Namen dokumentiert sind; Abgleich per Sichtprüfung der genannten Abschnitte.
- [x] 4.2 `pytest`, `npm test`, `npm run check` und `npm run build` ausführen; alle Läufe sind grün und der gebaute Stand liegt in `web/dist`.
- [x] 4.3 `openspec validate --strict` für `complete-screen-encoder-mode` und `add-ma2pi-config-ui` ausführen; keine Fehler oder Warnungen.

## Workflow follow-up

- Change nach Review und Abnahme archivieren und die geänderte `encoder-control`-Spec synchronisieren.
