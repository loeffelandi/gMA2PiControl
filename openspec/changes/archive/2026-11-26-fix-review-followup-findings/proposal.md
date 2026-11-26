# Proposal

## Why

Das Nach-Review des Commits `5ea80e2` durch die Python- und Svelte-Prüfläufe hat
konkrete Randfälle offengelegt, die im Show- und Konfigurationsbetrieb noch zu
Fehlverhalten führen können: `"current"`-LEDs frieren ein, wenn auf eine Seite
mit festem Ziel gewechselt wird; verwaiste Key-Ups im `PlaybackRouter` senden
ungewollte Button-Releases; `rawmidi_drop_output` verwirft beim Stopp das
ASL-`DISABLE`-Frame; `MappingPage` verwirft ein zweites Lernen durch veraltete
Store-Werte; `AssignDialog`, `DevicesPage`, `LearnPanel`, `NetworkPage` und
`StatusPage` haben Validierungs-, Vererbungs- und Replug-Lücken, und `put_config`
trennt andere PIN-Sessions auch ohne PIN-Änderung.

## What Changes

- **Feedback & Playback**: `ExecutorFeedback` blockiert `"current"`-Antworten
  nicht mehr beim Wechsel auf eine Seite mit festem Ziel; `PlaybackRouter`
  verwirft ungepaarte Key-Up-Events ohne verwaistes Release.
- **MIDI-Close, ASL-LED-Log & Deploy**: Beim Schließen wartet das Handle kurz
  auf reguläres Abfließen (z. B. `DISABLE` an die ASL), bevor `rawmidi_drop_output`
  greift; `describe_midi` wertet zusammengesetzte ASL-LED-Frames aus;
  `deploy/install.sh` normiert Leserechte (`u+rwX,go+rX`) unter `/opt/ma2pi/app`.
- **Encoder-IDs & Geräteabgleich**: Zweiphasige Vergabe automatischer
  `encoder_id`s in `config.py`, verlustfreie Serialisierung in `serialize.py`,
  `encoder_id` und konsistente Knotenauswahl in `/api/devices` sowie volle
  UI-Unterstützung frei benannter `relative-encoder`.
- **Learn-Modi, Helper & Netzwerk/Recovery**: Globale Tastenfreigabe bei
  `LearnManager`-Start; Entprellung gleicher Folge-Velocities und Hot-Reload-
  Schutz im `DeviceLearnManager`; gecancelte DNS-Tasks im `ScreenHelper`;
  gedeckelte `resume()`-Frist im `NetworkService`, Live-Rollback bei
  Schreibfehler im `RecoveryService` sowie Timeout-/Escape-Härtung in EventBus
  und Log-Redaction.
- **Svelte-5-UI & PIN-Sessions**: Deduplizierte Learn-Events und Modifier-
  Pflichtfeldprüfung in `MappingPage`; durchgereichter `StatusStore`, sauberes
  `startedSession`-/Gerätewechsel-Verhalten in `DevicesPage`/`LearnPanel`;
  strikte Feldprüfung (`Attributname`, `Page`, `step`), Modifier-Berücksichtigung
  und korrigierte Vererbung in `AssignDialog`/`DevicesPage`; Formular-Resync in
  `NetworkPage`; `seq`-basiertes Scrollen und Replug-Erkennung in `StatusPage`;
  Session-Widerruf in `put_config` nur bei echter PIN-Änderung.
- **BREAKING**: keine.

## Capabilities

### New Capabilities

Keine.

### Modified Capabilities

- `executor-feedback`: gültige `"current"`-Antworten auf Seiten mit festem Ziel.
- `executor-playback`: Verwerfen ungepaarter Button-Releases.
- `hid-input`: kurzes Abfließen vor `rawmidi_drop_output` und Leserechte im
  Installationsskript.
- `mapping-engine`: zweiphasige `encoder_id`-Auflösung und konsistente
  Darstellung in Config- und Geräte-API.
- `device-learn`: globale Tastenfreigabe beim Tasten-/Encoder-Learn sowie
  Rasten-Entprellung und Hot-Reload-Schutz beim Bank-Learn.
- `device-activity`: lesbare Zusammenfassung zusammengesetzter ASL-LED-Pakete.
- `runtime-config`: Task-Lebenszyklus im `ScreenHelper`, Sende-Timeout im
  Event-Stream und Escaping in der Log-Redaction.
- `network-config`: Fristdeckel bei `resume()` und Formular-Resync nach Rollback.
- `recovery-access`: Rückrollen des Live-Hotspots bei `recovery.json`-Schreibfehler.
- `config-ui`: Learn-Deduplizierung, Dialog-/Modifier-/Vererbungs-Validierung,
  `StatusStore`-Durchreichung, `StatusPage`-Scroll/Replug und gezielter
  PIN-Session-Widerruf.

## Impact

- **Backend**: `ma2pi/feedback.py`, `playback.py`, `midi_input.py`,
  `led_output.py`, `config.py`, `web/serialize.py`, `web/devices.py`,
  `web/__init__.py`, `web/events.py`, `__main__.py`, `device_learn.py`,
  `activity.py`, `screen_helper.py`, `network.py`, `recovery.py`,
  `logging_setup.py`, `deploy/install.sh`.
- **Frontend**: `web/src/App.svelte`, `MappingPage.svelte`, `DevicesPage.svelte`,
  `AssignDialog.svelte`, `LearnPanel.svelte`, `NetworkPage.svelte`,
  `StatusPage.svelte`, `status.ts` + zugehörige Vitest- und Pytest-Dateien.
