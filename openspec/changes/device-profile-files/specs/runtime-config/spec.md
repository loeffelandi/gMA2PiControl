# Spec Delta

## ADDED Requirements

### Requirement: Backup und Wiederherstellung als Dateisatz

Besteht die Konfiguration aus Hauptdatei und Profildateien, SHALL jedes Backup
alle Dateien als zusammengehörigen Satz enthalten. Eine Wiederherstellung MUST
den gesamten Satz ersetzen und Profildateien entfernen, die im Backup nicht
enthalten sind. Ein Backup aus einer einzelnen Datei MUST weiterhin
wiederherstellbar bleiben.

#### Scenario: Backup eines Dateisatzes

- **WHEN** eine Änderung an einer Profildatei angewendet wird
- **THEN** liegt der vollständige vorherige Satz aus Hauptdatei und allen Profildateien als ein Backup vor

#### Scenario: Wiederherstellung ersetzt den Satz

- **WHEN** ein Backup wiederhergestellt wird, das eine Profildatei weniger enthält als der aktive Satz
- **THEN** ist danach genau der Satz des Backups aktiv, und die überzählige Profildatei ist entfernt, nachdem der vorherige Satz gesichert wurde

#### Scenario: Altes Einzeldatei-Backup

- **WHEN** ein vor der Aufteilung erstelltes Einzeldatei-Backup wiederhergestellt wird
- **THEN** wird es validiert und aktiviert, ohne dass doppelte Profil-Definitionen entstehen

### Requirement: Schreibreihenfolge bei mehreren Dateien

Ändert ein Apply mehrere Dateien, MUST jede Datei einzeln atomar ersetzt werden,
Profildateien vor der Hauptdatei, und vorher MUST der vollständige alte Satz als
Backup vorliegen. Bleibt nach einem Abbruch ein ungültiger Zwischenstand, MUST
der Start ihn mit Dateinamen melden, und das letzte gute Backup MUST
wiederherstellbar bleiben.

#### Scenario: Abbruch zwischen zwei Dateien

- **WHEN** der Prozess nach dem Ersetzen einer Profildatei und vor dem Ersetzen der Hauptdatei beendet wird
- **THEN** ist jede einzelne Datei vollständig lesbar, und das Backup des alten Satzes liegt vor

#### Scenario: Ungültiger Zwischenstand beim Start

- **WHEN** der Daemon nach einem solchen Abbruch eine Konfiguration mit Querverweis-Fehler findet
- **THEN** meldet er den Fehler mit Dateiname und startet nicht mit teilweise angewendeten Daten

#### Scenario: Nur eine Datei betroffen

- **WHEN** ein Apply nur die Hauptdatei ändert
- **THEN** werden die Profildateien nicht neu geschrieben
