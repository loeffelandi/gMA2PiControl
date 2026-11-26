# Proposal

## Why

Die Statusseite zeigt heute nur globale Zähler und die letzten Frame-Typen als
nackte Liste (`playbacksRequest`, `keyname`, …). Beim Einrichten ist aber die
entscheidende Frage pro Gerät: **Kommt etwas an, und geht etwas zurück?** Ohne
diese Rückmeldung muss man im Log oder mit `--dump-input` suchen. Die Seite soll
deshalb wie ein kleines Konsolenpanel aussehen: pro Gerät eine RX- und eine
TX-Anzeige, die bei Aktivität blinken, darunter ein Terminal-Log mit Zeitstempel,
Richtung, Geräte-Kennung und Ereignis.

## What Changes

- **Neue Capability `device-activity`:** In-Memory-Tracker mit je Gerät
  RX-/TX-Zähler, Zeitstempeln und einem blickdichten Ringpuffer der letzten
  Ereignisse. Geräte-Kennung ist der Konfigurationsname (`cherry`, `asl`,
  `midicraft`, …); Frames an onPC erscheinen als `ma2`.
- **RX-Hook:** Der zentrale Eingabe-Konsument erfasst jedes `InputEvent` mit
  Gerät, Art und Kurzbeschreibung.
- **TX-Hooks:** Schreibzugriffe an Geräte (`MidiManager.send`, ASL-`LedOutput`)
  und an onPC (`Ma2Client._send_raw`) werden erfasst.
- **Live-Transport:** Der bestehende `status`-Snapshot (1 Hz) enthält Zähler und
  den Log-Puffer als Resync. Ein neuer WebSocket-Event `activity` liefert alle
  250 ms gebündelt nur die neuen Einträge und aktuellen Zähler — schnell genug
  für sichtbares Blinken, ohne den Event-Bus zu fluten.
- **Statusseite neu:** Geräte als Zeilen mit zwei LEDs (RX grün, TX amber),
  Kennung, Transport, VID:PID und Zustand; darunter ein Terminal-Log im
  Monospace-Stil mit Zeitstempel, Richtungs-Badge, Gerät und Kurztext.
  Log-Einträge sind auf 100 begrenzt, automatisches Nachscrollen respektiert
  `prefers-reduced-motion`.
- **Dokumentation:** `docs/api.md` beschreibt die neuen Statusfelder und den
  `activity`-Event.
- **Nicht enthalten:** Persistenz über Neustarts, Diagramme/Historie,
  Bandbreitenmessung, Filter-UI, neue HTTP-Endpunkte, Änderungen an Mapping oder
  Gerätekonfiguration.
- **Konflikt-Hinweis:** `ma2pi/__main__.py`, `ma2pi/feedback.py` und
  `ma2pi/web/events.py` sind aktuell uncommitted von einer anderen Session
  geändert. Die Hooks werden so klein wie möglich gehalten; vor der Umsetzung
  sollte dieser Stand committet oder abgewartet werden.

## Capabilities

### New Capabilities

- `device-activity`: Erfassung, Bündelung und Auslieferung von RX-/TX-Aktivität
  pro Gerät inklusive begrenztem Ereignis-Log.

### Modified Capabilities

- `config-ui`: Statusseite mit Gerätezeilen, RX-/TX-LEDs, Aktivitätsblinken und
  Terminal-Log.

## Impact

- **Code:** neu `ma2pi/activity.py`; Hooks in `ma2pi/__main__.py`
  (`_process_input`, Broadcast/Task), `ma2pi/ma2_client.py` (Frame-Callback),
  `ma2pi/midi_input.py` (`send`-Callback), `ma2pi/led_output.py`
  (Schreib-Callback). Frontend: `web/src/lib/StatusPage.svelte`,
  `web/src/lib/status.ts`, `web/src/lib/api.ts`, `web/src/app.css`,
  `web/src/lib/StatusPage.test.ts`.
- **API:** `StatusInfo` erhält `activity`; neuer WS-Event `activity`.
- **Daten:** keine Konfigurations- oder Persistenzänderung; Puffer nur im RAM.
- **Tests:** Tracker-Einheitstests, Web-Test für Statusfelder und
  `activity`-Event, Vitest für Blinken/Log-Merge und Resync.
- **Risiko:** Bei sehr hohen Ereignisraten muss die Bündelung greifen; ohne
  Deckel auf Pending-Liste und Log-Ring wächst der Speicher. Die Hooks dürfen die
  Eingabeverarbeitung nicht blockieren.
