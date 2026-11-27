# 0027. MIDI-Remote-Abgleich einmal je Connect und Retrigger

* Datum: 2026-11-27
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Related to [24. Executor-Tasten über MA-MIDI-Remotes per RTP-MIDI](0024-executor-tasten-ueber-ma-midi-remotes-per-rtp-midi.md)

## Kontext und Problemstellung

ADR-0024 gleicht die MIDI-Remote-Tabelle per Telnet ab. Ein erster Entwurf dieses
ADR ergänzte eine periodische Prüfung alle 30 s und einen Dauer-Backoff bei
unvollständigem Schreiben. Das hieß: `ma2pi` meldete sich ständig per Telnet an
und schrieb die Remotes erneut, ohne dass etwas passiert war. Im Betrieb
führte das zu Dropouts bei den Executor-Tasten. Der Abgleich soll deshalb
einmal beim Connect laufen.

## Entscheidungstreiber

* Der Abgleich läuft einmal je Verbindung zur MA, nicht auf einem Timer.
* Ein zu früher Versuch, bevor die MA Telnet annimmt, darf nicht der letzte sein.
* Derselbe Lauf soll von der Statusseite auslösbar sein (z. B. nach Showwechsel
  ohne Reconnect).
* Bestätigte Tasten dürfen während eines Abgleichs nicht tot sein.

## Betrachtete Optionen

* Periodische Telnet-Prüfung alle 30 s
* Abgleich einmal je Connect, bei Config-Apply und per Knopf
* Showfile-Event über den Web Remote erkennen

## Entscheidung

Gewählt: Abgleich einmal je Connect, bei Config-Apply und per Knopf.

* `MidiRemoteService.request_sync` ist der einzige Einstieg. `Ma2Client`
  benachrichtigt nach erfolgreichem Login (jeder Aufbau der Web-Remote-Sitzung,
  auch der erste); nur dieser Callback löst den Connect-Abgleich aus. `start()`
  öffnet nur die RTP-MIDI-Sitzung, der Daemon stößt den Abgleich an, wenn der
  Login bereits vor dem Start des Dienstes stattfand.
* Zusätzlich läuft der Abgleich nach jeder Konfigurationsaktivierung, weil sich
  die Zieltabelle geändert hat.
* `POST /api/midi-remote/sync` weckt denselben Weg und antwortet **202** mit dem
  Status (409 bei `enabled = false` oder `sync = "off"`, 503 ohne Dienst). Die
  Statusseite bietet **Remotes ausrollen**, solange der Abgleich nicht aus und
  die Sitzung kein Dry-Run ist.
* Kein Timer nach einem Lauf. Nur ein Telnet-Fehler (MA noch nicht bereit) wird
  mit Backoff 1 s … 10 s wiederholt. Ein Lauf, der schreibt und beim Rücklesen
  Einträge vermisst, wird gemeldet (Warnung, Status `failed`), aber nicht von
  allein wiederholt.
* Bestätigte Ziele bleiben nutzbar bis zum Rücklesen: Ein Retrigger setzt sie
  nicht vorsorglich auf unsynchron.

### Konsequenzen

* Gut, weil Telnet nur beim Connect, bei Config-Apply und auf Knopfdruck läuft.
* Gut, weil Tasten während eines Abgleichs weitersenden, solange die Tabelle
  noch stimmt.
* Schlecht, weil ein Showwechsel ohne Reconnect erst nach Knopfdruck
  (**Remotes ausrollen**) auffällt.
* Schlecht, weil ein unvollständiger Lauf bis zum nächsten Connect oder Knopf
  unvollständig bleibt.

### Bestätigung

Proposed. Gilt als Accepted, wenn nach einem Lauf ohne Fehler kein weiterer
Telnet-Zugriff erfolgt, bis die Sitzung neu aufgebaut, die Konfiguration
aktiviert oder der Knopf gedrückt wird.

## Vor- und Nachteile der Optionen

### Periodische Telnet-Prüfung alle 30 s

* Gut, weil ein Showwechsel ohne Reconnect automatisch repariert wird.
* Schlecht, weil `ma2pi` dauernd per Telnet anmeldet und Tabellen liest.

### Abgleich einmal je Connect, bei Config-Apply und per Knopf

* Gut, weil jeder Lauf einen Anlass hat.
* Schlecht, weil ein Showwechsel ohne Reconnect manuell angestoßen wird.

### Showfile-Event über den Web Remote

* Gut, weil der Sync sofort nach dem Laden startet.
* Schlecht, weil der Web Remote kein solches Event liefert.

## Weitere Informationen

* Verwandt: ADR-0024 (Transport und Telnet-Abgleich)
* Change: `ensure-midi-remote-rollout`
* API: `POST /api/midi-remote/sync`
