# Tasks

## 1. Activity-Tracker

- [x] 1.1 `ma2pi/activity.py` anlegen: `LogEntry` (seq, ts, direction, device, kind, summary) und `ActivityTracker` mit thread-sicherem `record()`, `snapshot()` (Gerätezähler + kompletter Ring) und `take_pending()` (Delta-Puffer); Ring auf 100, Pending auf 500 begrenzen. Tests in `tests/test_activity.py` für Zähler, Zeitstempel, Ringgrenze, monotone Sequenz und Pending-Leerung.
- [x] 1.2 Kurztext-Builder ergänzen: `InputEvent` (Taste/Encoder/Wert mit Note, Bank, Control), onPC-Frame (Art plus Executor/Button/Page, sofern vorhanden), MIDI/LED-Schreibzugriff (Note und Wert, keine Rohbytes); Tests stellen sicher, dass weder Kommandotext noch Passwort im Summary landen.

## 2. Hooks

- [x] 2.1 RX in `ma2pi/__main__.py` (`_process_input`, direkt nach `queue.get()`): `record("rx", item.device or "system", item.kind, summary)`; `DeviceLost` als `system`/`device-lost` erfassen.
- [x] 2.2 `ma2pi/ma2_client.py`: optionalen Callback `on_frame` am `Ma2Client` ergänzen und am Ende von `_send_raw` mit `kind` und Frame aufrufen; in `__main__` auf `record("tx", "ma2", kind, summary)` verdrahten.
- [x] 2.3 `ma2pi/midi_input.py`: optionalen Callback `on_send(device, data)` im `MidiManager` ergänzen und nur bei erfolgreichem `write` aufrufen; in `__main__` auf `record("tx", device, "midi", …)` verdrahten.
- [x] 2.4 `ma2pi/led_output.py`: optionalen Callback `on_write(label)` ergänzen und in `_write` nach Erfolg aufrufen; Gerätename aus `LedSettings.device`, in `__main__` auf `record("tx", device, "led", label)` verdrahten.

## 3. Transport und API

- [x] 3.1 `_status_snapshot` in `ma2pi/__main__.py` um `activity` (`devices` plus `log`) erweitern.
- [x] 3.2 Flush-Task für `activity`-Events ergänzen: alle 250 ms, nur bei `bus.subscriber_count` und nicht-leerem `take_pending()`, Payload `{"type": "activity", "data": {"devices": …, "entries": […]}}`; Task beim Start anlegen und beim Shutdown sauber abbrechen.
- [x] 3.3 Web-Tests: Status enthält `activity`; ein gefüllter Pending-Puffer erzeugt genau ein gebündeltes Event; ohne Pending kein Event; langsamer Client bleibt durch den begrenzten Puffer geschützt (`tests/test_web.py`).
- [x] 3.4 `docs/api.md`: `/api/status` um `activity` und die Event-Tabelle um `activity` mit Payload-Beispiel ergänzen; Hinweis auf 250-ms-Bündelung und 100-Einträge-Ring.

## 4. Frontend

- [x] 4.1 `web/src/lib/api.ts`: Typen `ActivityDevice`, `ActivityEntry`, `ActivityInfo` ergänzen und `StatusInfo` um `activity` erweitern.
- [x] 4.2 `web/src/lib/status.ts`: `activity`-Event verarbeiten, Einträge über `seq` deduplizieren, Ring auf 100 begrenzen, Status-Snapshot als Resync übernehmen; Zählerstände je Gerät im State führen. Tests für Merge, Dedupe und Resync.
- [x] 4.3 `web/src/lib/StatusPage.svelte`: Geräteliste durch Zeilen mit RX-/TX-LEDs ersetzen; pro Gerät und Richtung letzten Zähler merken, bei Anstieg `pulse` für 400 ms setzen; Legende „RX vom Gerät / TX zum Gerät“; Zustand „erkannt/nicht erkannt“ und Transport/VID:PID/Profil beibehalten.
- [x] 4.4 Terminal-Log in `StatusPage.svelte` (oder eigene `ActivityLog.svelte`): Zeit `HH:MM:SS.mmm`, Richtungs-Badge, Gerätekennung, Kurztext; neueste unten, Auto-Scroll ans Ende, Max-Höhe, leerer Zustand „Noch keine Aktivität.“
- [x] 4.5 `web/src/app.css`: Token `--font-mono`, Styles für `.device-row`, `.activity-leds`, `.terminal`, `.log-line`, Richtungs-Badges und `@keyframes led-pulse`; `prefers-reduced-motion: reduce` schaltet die Animation ab; responsive Umbruch ohne horizontales Scrollen.
- [x] 4.6 `web/src/lib/StatusPage.test.ts` an das neue Markup anpassen und Fälle für RX-Puls, TX-Puls, Log-Merge, Resync und leeren Zustand ergänzen.

## 5. Verifikation

- [x] 5.1 `cd web && npm run check` ohne Fehler.
- [x] 5.2 `cd web && npm test` grün.
- [x] 5.3 `cd web && npm run build` und `npm run check:offline` grün; `web/dist` aktualisieren.
- [x] 5.4 `pytest -q` grün.
- [x] 5.5 Sichtprüfung: Statusseite mit simulierter Aktivität (z. B. Test-Provider oder kurzzeitiges Einspielen von Events), RX/TX-Puls, Terminal-Auto-Scroll, Mobile und `prefers-reduced-motion`.

## 6. Konflikt mit laufender Session

- [x] 6.1 Nutzer hat die Umsetzung vor dem Commit der anderen Session freigegeben; die Hooks sind additiv eingepflegt, kein Deploy. Nach deren Commit den Diff erneut prüfen.
