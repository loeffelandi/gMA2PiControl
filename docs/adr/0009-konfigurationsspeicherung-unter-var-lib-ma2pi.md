# 0009. Konfigurationsspeicherung unter /var/lib/ma2pi

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

Amends [0004. Deployment als venv-Dienst unter /opt/ma2pi](0004-deployment-als-venv-dienst-unter-opt-ma2pi.md)

## Kontext und Problemstellung

ADR-0004 legt die Konfiguration unter `/etc/ma2pi/config.toml` ab und verzichtet
bewusst auf beschreibbare Pfade. Die Web-Oberfläche muss die Konfiguration aber
ändern können. Der Dienst läuft als `ma2pi` und darf `/etc` nicht schreiben.
Ein privilegierter Hilfsdienst wäre möglich, erhöht aber Angriffsfläche und
Komplexität. Gleichzeitig müssen Kommentare in der TOML-Datei erhalten bleiben
und ein Schreibabbruch darf die Konfiguration nicht zerstören.

## Entscheidungstreiber

* Schreiben ohne Root und ohne privilegierten Helper
* Keine Beschädigung der Konfiguration bei Absturz oder Stromausfall
* Kommentare und Formatierung bleiben erhalten
* Nachvollziehbare Backups und einfacher Rollback
* systemd-Hardening bleibt so streng wie möglich

## Betrachtete Optionen

* Konfiguration weiter in `/etc`, Schreiben über privilegierten Helper
* Konfiguration nach `/var/lib/ma2pi` verlagern, Dienst schreibt selbst
* Konfiguration in `/opt/ma2pi` neben dem Code
* Konfiguration in einer Datenbank oder einem JSON-Store

## Entscheidung

Die aktive Konfiguration liegt unter `/var/lib/ma2pi/config.toml`
(`0640 ma2pi:ma2pi`), das Passwort unter `/var/lib/ma2pi/ma2pi.password`
(`0600 ma2pi:ma2pi`). Die systemd-Unit erhält `StateDirectory=ma2pi` und
`ReadWritePaths=/var/lib/ma2pi`; `ProtectSystem=strict` bleibt bestehen.
`/etc/ma2pi` bleibt nur für die Erstinstallation und systemweite Dateien.

Schreiben erfolgt atomar mit `tomlkit`:

1. Bestehendes Dokument laden, JSON-Merge-Patch anwenden.
2. Mit demselben Validator wie beim Start prüfen.
3. `backups/config-<timestamp>.toml` und `backups/last-good.toml` anlegen.
4. Temporäre Datei im Zielverzeichnis schreiben, `fsync`, `chmod 0640`,
   `os.replace`, Verzeichnis `fsync`n.

Die letzten 20 Backups bleiben erhalten. Eine vorhandene
`/etc/ma2pi/config.toml` wird bei der Installation einmalig migriert und
gesichert.

### Konsequenzen

* Gut, weil der Dienst ohne Root und ohne Helper schreiben kann.
* Gut, weil atomarer Replace und Backups einen Abbruch absichern.
* Gut, weil `tomlkit` Kommentare an unveränderten Stellen erhält.
* Schlecht, weil ADR-0004 in den Punkten Config-Pfad und `ReadWritePaths` ergänzt werden muss.
* Schlecht, weil Kommentare innerhalb komplett ersetzter Arrays verloren gehen können.
* Schlecht, weil manuelle Editor-Änderungen und UI-Änderungen nebeneinander bestehen und beim nächsten Apply validiert werden.

### Bestätigung

Accepted, wenn der Dienst als `ma2pi` schreiben kann, ein simulierter Abbruch
die alte Datei intakt lässt, ein Backup-Restore funktioniert und die Migration
aus `/etc` auf einer frischen Installation nachvollziehbar ist.

## Vor- und Nachteile der Optionen

### `/etc` mit privilegiertem Helper

* Gut, weil die Konfiguration an ihrem systemweiten Ort bleibt.
* Schlecht, weil ein Root-Helper oder Polkit-Regel nötig wäre.
* Schlecht, weil die Angriffsfläche wächst und die Fehlerbehandlung komplexer wird.

### `/var/lib/ma2pi`

* Gut, weil der Dienst eigener Herr seiner Laufzeitdaten ist.
* Gut, weil systemd den Pfad über `StateDirectory` sauber verwaltet.
* Schlecht, weil sich der dokumentierte Config-Pfad ändert und migriert werden muss.

### `/opt/ma2pi`

* Gut, weil alles unter einem Verzeichnis liegt.
* Schlecht, weil Code und veränderliche Daten vermischt werden und Updates die Config treffen könnten.

### Datenbank oder JSON-Store

* Gut, weil strukturierte Updates einfach wären.
* Schlecht, weil die Handlesbarkeit und die Kommentare verloren gehen und eine zusätzliche Abhängigkeit entsteht.

## Weitere Informationen

* Amendiert ADR-0004 (Config-Pfad, ReadWritePaths)
* Verwandt: ADR-0008, ADR-0010, ADR-0011
