# Tasks

## 1. Sync-Schleife

- [x] 1.1 `MidiRemoteService`: kein Timer; nach einem Lauf ohne Fehler wartet
  die Schleife auf den nächsten Anlass, `start()` gleicht nicht selbst ab.
  Verifikation: `tests/test_midi_remote_service.py` — nach einem sauberen Sync
  folgt ohne `request_sync` kein zweiter Lauf.
- [x] 1.2 `MidiRemoteService`: Backoff nur bei Telnet-Fehler; unvollständige
  Läufe werden gemeldet und nicht wiederholt. Verifikation: Incomplete-Result
  bleibt bei einem Lauf, ein Retrigger holt ihn nach.
- [x] 1.3 Bestätigte Ziele während eines Retriggers nicht
  vorsorglich unsynchron setzen. Verifikation: bestehender Test, dass
  unveränderte Ziele während eines laufenden Syncs weiter senden.

## 2. Sitzungs-Wiederaufbau

- [x] 2.1 `Ma2Client`: Callback nach erfolgreichem Login; in `__main__.py`
  `midi_remote.request_sync` nur an den Wiederaufbau hängen (und nach dem
  Start, falls der Login schon lief). Verifikation:
  `tests/test_ma2_client.py` — Callback läuft nach `connect_once`.

## 3. API

- [x] 3.1 `POST /api/midi-remote/sync` verdrahten: `request_sync()`, 202 mit
  Status, 409 wenn disabled oder `sync = "off"`, 503 ohne Dienst.
  Verifikation: `tests/test_midi_remote_service.py` (oder eigenes API-Modul)
  für 202/409/503.
- [x] 3.2 `docs/api.md` um den Endpunkt und die Fehlercodes ergänzen.
  Verifikation: Status, Körper und Fehlercodes stehen wie implementiert.

## 4. Statusseite

- [x] 4.1 Knopf „Remotes ausrollen“ auf der Statusseite, deaktiviert während
  `running`, ausgeblendet bei `sync = "off"` und Dry-Run; unvollständige Läufe
  als Fehlerzeile. Verifikation: `web/src/lib/StatusPage.test.ts`.
- [x] 4.2 `ApiClient.retriggerMidiSync()` und Anbindung in `App.svelte`.
  Verifikation: `web/src/lib/api.test.ts`.

## 5. Doku

- [x] 5.1 README-Abschnitt `[midi_remote]` um Abgleich einmal je Connect, Telnet-Retry
  und den Status-Knopf ergänzen. Verifikation: der beschriebene Ablauf entspricht
  1–4.
- [x] 5.2 ADR-0027 (Abgleich einmal je Connect, Retrigger) anlegen und in
  ADR-0024 sowie `docs/adr/README.md` verlinken. Verifikation: ADR nennt D1–D5.

## Workflow follow-up

- Nach Review `/opsx-apply` bzw. die Umsetzung anstoßen.
- Nach der Umsetzung den Change archivieren.
