# Design

## Context

Siehe proposal.md. Heute weckt `MidiRemoteService.request_sync()` den
Telnet-Abgleich nach `set_config` und nach `connection_lost`. Die Schleife
wiederholt nur, wenn `SyncResult.error` gesetzt ist (Telnet/OS-Fehler). Ein
Showwechsel ohne Session-Verlust bleibt unsichtbar. `request_sync` existiert
intern, aber nicht in der API. Ein erster Entwurf mit Timer (30 s) wurde
verworfen: der Abgleich läuft einmal je Connect.

## Goals / Non-Goals

**Goals:**

- Die reservierten MIDI-Remotes werden einmal je Connect ausgerollt, nie
  periodisch.
- Ein zu früher Versuch nach dem Laden bleibt nicht der letzte.
- Derselbe Lauf ist manuell aus der Statusseite anstoßbar.

**Non-Goals:**

- Keine periodische Prüfung, kein `[midi_remote]`-Feld für ein Intervall.
- Keine dauerhafte Telnet-Session.
- Kein Erkennen des Showfiles über den Web Remote (kein solches Event).
- Kein Umschalten auf den Web-Remote-Transport, wenn Remotes fehlen.

## Decisions

### D1: Kein Timer

Nach einem Lauf wartet die Sync-Schleife auf den nächsten Anlass. Alternative:
Prüfung alle 30 s — verworfen, weil `ma2pi` dann dauernd per Telnet anmeldet.

### D2: Backoff nur bei Telnet-Fehler

Die Schleife wiederholt mit Backoff (1 s … 10 s) nur, wenn `error` gesetzt ist
(MA noch nicht bereit). Ein Lauf mit `failed > 0` ohne `error` wird gemeldet
(Warnung, Status) und nicht von allein wiederholt; der Knopf oder der nächste
Connect holt ihn nach.

### D3: Sync einmal je Sitzungsaufbau

`Ma2Client` bekommt einen Callback nach erfolgreichem Login; nur er (und der
Start, falls der Login schon vor dem Dienst lief) löst den Connect-Abgleich
aus. `start()` des Dienstes synchronisiert nicht selbst, ein Verlust-Callback
entfällt, damit ein Reconnect nicht zweimal abgleicht.

### D4: Ein interner Weg für Automatik und Knopf

`POST /api/midi-remote/sync` ruft `request_sync()` auf und antwortet **202**
mit dem aktuellen Status. 409 bei `enabled = false` oder `sync = "off"`, 503
wenn der Dienst fehlt. Kein zweiter Sync-Pfad, keine synchrone Wartezeit auf
das Telnet-Ende.

### D5: Bestätigte Ziele bleiben nutzbar bis zum Rücklesen

Ein Retrigger setzt die bisher bestätigten Ziele nicht vorsorglich auf
unsynchron. Erst das Rücklesen nach dem Lauf aktualisiert `synced`.

## Risks / Trade-offs

- [Showwechsel ohne Reconnect bleibt unbemerkt] → der Knopf „Remotes
  ausrollen“.
- [onPC während Show-Load nicht beschreibbar] → D2 für Telnet-Fehler; sonst der
  Knopf.
- [Ein Telnet-Client in der MA] → bestehende kurze Sessions; kein zusätzlicher
  paralleler Login über den einen Loop hinaus.

## Migration Plan

Kein Schemawechsel. Nach dem Deploy gilt der Abgleich einmal je Connect für bestehende
`[midi_remote] enabled = true`. Rollback: vorherige Version; die Show-Tabelle
bleibt, nur Automatik und Knopf entfallen.

## Open Questions

Keine.
