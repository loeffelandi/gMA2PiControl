# 0010. Hot Reload der Konfiguration

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

Amends [0006. Konfigurationsschema in TOML](0006-konfigurationsschema-in-toml.md)

## Kontext und Problemstellung

ADR-0006 legt fest, dass Konfigurationsänderungen in v1 einen Dienstneustart
erfordern. Die Web-Oberfläche soll Änderungen aber unmittelbar anwenden. Ein
Neustart über `systemctl` würde dem Daemon zusätzliche Rechte oder einen
privilegierten Helper erfordern und unterbricht die MA2-Session. Gleichzeitig
darf ein Apply keine gehaltenen Modifier, offenen Encoder-Deltas oder halben
Chords hinterlassen.

## Entscheidungstreiber

* Änderungen ohne Dienstneustart und ohne Session-Verlust bei reinem Mapping
* Keine hängenden Tasten oder Modifier während des Umschaltens
* Fehler dürfen die aktive Konfiguration nicht beschädigen
* Klare, testbare Zustandsübergänge
* Keine zusätzlichen Privilegien für den Daemon

## Betrachtete Optionen

* Dienstneustart über systemd
* SIGHUP mit vollständigem Reload
* In-Process-Apply mit Lock und Zustandsübergabe
* Datei-Watcher, der Änderungen automatisch übernimmt

## Entscheidung

Die Konfiguration wird in-process und atomar angewendet:

1. Kandidat laden und mit demselben Validator prüfen.
2. Bei geänderten MA2-Zugangsdaten einen Verbindungstest durchführen; bei Fehler abbrechen.
3. Kandidat atomar speichern (Backup, temporäre Datei, `os.replace`).
4. Alle gehaltenen Tasten in umgekehrter Press-Reihenfolge freigeben und offene Encoder-Deltas verwerfen.
5. `RuntimeConfig` und Mapping im Speicher tauschen; `generation` erhöhen.
6. Bei geänderten Zugangsdaten die alte Session schließen und neu verbinden; bei reinen Mapping-Änderungen bleibt die Session bestehen.
7. Eingabe wieder freigeben.

Ein `asyncio.Lock` serialisiert Apply-Aufrufe. Während des Apply eintreffende
Eingabeereignisse werden verworfen und im UI als „busy“ angezeigt. Schlägt die
Verbindung nach erfolgreichem Apply fehl, bleibt die neue Konfiguration aktiv,
weil die Zugangsdaten vorher getestet wurden; der normale Reconnect greift. Ein
automatisches Zurückrollen nach erfolgreichem Apply findet nicht statt.

### Konsequenzen

* Gut, weil Mapping-Änderungen sofort wirken und die Session erhalten bleibt.
* Gut, weil gehaltene Tasten vor dem Tausch sauber freigegeben werden.
* Gut, weil keine systemd-Rechte und kein Helper nötig sind.
* Schlecht, weil der Apply-Pfad komplexer ist und sorgfältige Tests braucht.
* Schlecht, weil Eingaben während des Apply verloren gehen; das ist bewusst und wird im UI angezeigt.
* Schlecht, weil ADR-0006 („kein Hot Reload in v1“) ergänzt werden muss.

### Bestätigung

Accepted, wenn ein Apply bei gehaltenen MA+Store-Tasten keine hängenden
Modifier hinterlässt, die Prozess-ID gleich bleibt, eine reine Mapping-Änderung
die Session nicht unterbricht und ein Apply mit falschem Passwort abgelehnt
wird.

## Vor- und Nachteile der Optionen

### Dienstneustart

* Gut, weil einfach und robust.
* Schlecht, weil die Session unterbrochen wird und systemd-Rechte nötig sind.

### SIGHUP-Reload

* Gut, weil kein UI-spezifischer Apply-Pfad nötig wäre.
* Schlecht, weil der Reload nicht an einen Request gebunden ist und Fehler nicht synchron an die UI zurückgemeldet werden.

### In-Process-Apply

* Gut, weil synchrone Fehlerrückmeldung, Lock und Zustandsfreigabe möglich sind.
* Gut, weil die Session bei Mapping-Änderungen erhalten bleibt.
* Schlecht, weil der Ablauf viele Zustände und Tests umfasst.

### Datei-Watcher

* Gut, weil auch manuelle Editor-Änderungen übernommen würden.
* Schlecht, weil halb geschriebene Dateien und unbemerkte Änderungen schwer zu behandeln sind.
* Schlecht, weil kein klarer Apply-Zeitpunkt und keine Bestätigung existieren.

## Weitere Informationen

* Amendiert ADR-0006 (Hot Reload)
* Verwandt: ADR-0008, ADR-0009, ADR-0012
