# Proposal

## Why

MIDI-Remotes leben in der Show. Nach einem Showwechsel fehlen die Einträge von
`ma2pi`, die Executor-Tasten tun dann nichts. Der Abgleich läuft heute nur nach
Konfigurationsaktivierung und nach Verlust der Web-Remote-Sitzung; schlägt das
Ausrollen fehl, weil die onPC noch nicht bereit ist, bleibt der Fehler stehen.
Der Betreiber braucht einen manuellen Retrigger; der Abgleich selbst läuft
einmal je Connect und nie periodisch.

## What Changes

- Der Abgleich läuft einmal je Aufbau der Web-Remote-Sitzung (auch der erste),
  nach Konfigurationsaktivierung und nach einem Knopf auf der Statusseite;
  kein Timer, kein Nachprüfen alle paar Sekunden.
- Nur ein Telnet-Fehler wird mit Backoff wiederholt; ein unvollständiges
  Ausrollen wird gemeldet und wartet auf den nächsten Anlass.
- Neue API `POST /api/midi-remote/sync` stößt denselben Lauf an wie die
  Automatik; die Statusseite zeigt den Knopf „Remotes ausrollen“.
- Unvollständige Läufe sind im Status als fehlende Ziele erkennbar.

## Capabilities

### New Capabilities

- (keine)

### Modified Capabilities

- `midi-remote-sync`: Anlässe des Abgleichs (einmal je Connect), Retry nur bei
  Telnet-Fehler, manueller Retrigger.
- `config-ui`: manueller Retrigger über Statusseite und JSON-API.

## Impact

- Code: `MidiRemoteService`-Sync-Schleife, Web-Remote-Reconnect-Hooks,
  `POST /api/midi-remote/sync`, Statusseite.
- API: neuer Schreibpfad hinter PIN und `X-Ma2pi-Request`.
- Doku: `docs/api.md`, README, ADR ergänzend zu ADR-0024.
- Keine neuen Konfigurationsschlüssel; `sync = "off"` bleibt ohne Telnet.
- Nicht Teil dieses Changes: rtpMIDI-Sitzung, Adressvergabe, fremde Remotes
  auf nicht reservierten Kanälen.
