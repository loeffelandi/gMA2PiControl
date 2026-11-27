# Spec Delta

## Purpose

Beschreibt, wie Geräteprofile samt Layout in je einer Datei neben der
Hauptkonfiguration liegen können: Laden, Fehlerzuordnung, Schreiben, Migration
und Prüfung. Eine monolithische `config.toml` bleibt dabei weiterhin gültig.

## ADDED Requirements

### Requirement: Profilverzeichnis ist explizit konfiguriert

Die Hauptkonfiguration SHALL optional ein Profilverzeichnis (`profiles_dir`) als
relativen Pfad zum Verzeichnis der Hauptkonfiguration nennen. Fehlt der
Schlüssel, MUST die Konfiguration wie bisher nur aus der Hauptdatei gelesen
werden. Absolute Pfade, `..`-Segmente und Pfade, die aus dem
Konfigurationsverzeichnis herausführen, MUST von der Validierung abgelehnt werden.

#### Scenario: Ohne Profilverzeichnis

- **WHEN** die Hauptkonfiguration keinen `profiles_dir` enthält
- **THEN** wird kein weiteres Verzeichnis gelesen und alle Profile müssen in der Hauptdatei stehen

#### Scenario: Pfad außerhalb des Konfigurationsverzeichnisses

- **WHEN** `profiles_dir` ein absoluter Pfad ist oder `..` enthält
- **THEN** lehnt die Validierung die Konfiguration mit dem Schlüssel `profiles_dir` ab

#### Scenario: Profilverzeichnis nicht per API änderbar

- **WHEN** ein API-Patch `profiles_dir` setzen oder ändern will
- **THEN** wird der Schlüssel verworfen und die gespeicherte Konfiguration behält ihren bisherigen Wert

### Requirement: Eine Datei je Profil

Jede `*.toml`-Datei im Profilverzeichnis SHALL genau ein Profil definieren,
dessen Name dem Dateinamen ohne Endung entspricht. Die Datei MUST die
Profildaten unter `[profile]` und MAY das Layout des Profils unter `[layout]`
enthalten. Jeder andere Abschnitt in einer Profildatei MUST abgelehnt werden.

#### Scenario: Profil aus Datei

- **WHEN** `profiles.d/midicraft-enc.toml` ein `[profile]` mit Controls und Bänken sowie ein `[layout]` enthält
- **THEN** existiert das Profil `midicraft-enc` mit diesem Layout, und `[devices.*]` kann es per `profile = "midicraft-enc"` referenzieren

#### Scenario: Fremder Abschnitt in der Profildatei

- **WHEN** eine Profildatei einen Abschnitt wie `[mapping]` oder `[web]` enthält
- **THEN** lehnt die Validierung die Datei mit Dateiname und Abschnittsname ab

#### Scenario: Leeres Verzeichnis

- **WHEN** das Profilverzeichnis existiert, aber keine Profildatei enthält
- **THEN** gilt die Konfiguration als gültig, sofern die Hauptdatei alle benötigten Profile definiert

### Requirement: Profilnamen sind eindeutig

Ein Profilname MUST in der gesamten Konfiguration genau einmal definiert sein.
Ein Mischbetrieb aus Profilen in der Hauptdatei und in Profildateien SHALL
zulässig sein. Definieren Hauptdatei und eine Profildatei dasselbe Profil,
MUST die Validierung mit beiden Fundstellen fehlschlagen.

#### Scenario: Mischbetrieb

- **WHEN** `cherry-g86` in der Hauptdatei und `midicraft-enc` in einer Profildatei steht
- **THEN** sind beide Profile gültig und nutzbar

#### Scenario: Doppelte Definition

- **WHEN** `[profiles.midicraft-enc]` in der Hauptdatei und `profiles.d/midicraft-enc.toml` existieren
- **THEN** lehnt die Validierung ab und nennt Hauptdatei und Profildatei

### Requirement: Fehler nennen die Datei

Ein Validierungsfehler in einer Profildatei MUST den Dateinamen und den Pfad
innerhalb der Datei nennen, sodass der Fehler ohne Suchen auffindbar ist.
Bestehende Fehlertexte und Schlüsselpfade der Hauptdatei MUST unverändert
bleiben.

#### Scenario: Fehler in einer Profildatei

- **WHEN** in `profiles.d/midicraft-push.toml` ein Control eine unbekannte Art hat
- **THEN** nennt der Fehler `profiles.d/midicraft-push.toml` und den Schlüsselpfad des Controls

#### Scenario: Fehler in der Hauptdatei

- **WHEN** in der Hauptdatei ein Mapping auf ein unbekanntes Control verweist
- **THEN** entspricht die Meldung der bisherigen Meldung für die Hauptdatei

### Requirement: Zusammengeführte Sicht bleibt unverändert

`GET /api/config`, die Geräte-API und die Laufzeit SHALL die Konfiguration in
derselben kanonischen Struktur liefern, unabhängig davon, ob Profile in der
Hauptdatei oder in Profildateien stehen. Die Oberfläche MUST nicht erkennen
können, aus welcher Datei ein Profil stammt.

#### Scenario: Gleiche API vor und nach der Aufteilung

- **WHEN** eine monolithische Konfiguration in Hauptdatei und Profildateien aufgeteilt wird
- **THEN** ist die Antwort von `GET /api/config` bis auf den Quellpfad identisch

### Requirement: Änderungen landen in der Datei des Profils

Ändert eine Konfigurationsänderung ein Profil oder dessen Layout, SHALL sie in
die Datei dieses Profils geschrieben werden, alle übrigen Änderungen in die
Hauptdatei. Unveränderte Dateien MUST NOT neu geschrieben werden, Kommentare und
Formatierung der geänderten Dateien MUST erhalten bleiben. Steht das Profil in
der Hauptdatei, MUST die Änderung dort landen.

#### Scenario: Bank-Belegung lernen

- **WHEN** die gelernte Notenbelegung einer MIDICRAFT-Bank gespeichert wird
- **THEN** ändert sich nur die Datei dieses Profils, und die Hauptdatei samt anderen Profildateien bleibt byte-identisch

#### Scenario: Mapping ändern

- **WHEN** ein Mapping über die Oberfläche geändert wird
- **THEN** ändert sich nur die Hauptdatei

#### Scenario: Profil in der Hauptdatei

- **WHEN** die Bank-Belegung eines Profils gespeichert wird, das in der Hauptdatei steht
- **THEN** wird die Änderung in die Hauptdatei geschrieben

### Requirement: Aufteilen einer bestehenden Konfiguration

Der Daemon SHALL einen Befehl zum Aufteilen einer monolithischen Konfiguration
in Hauptdatei und Profildateien bereitstellen. Der Befehl MUST vorher ein Backup
anlegen, das Ergebnis vor dem Ersetzen validieren und eine Konfiguration
erzeugen, die dieselbe zusammengeführte Sicht liefert. Ein erneuter Aufruf MUST
ohne Änderung enden.

#### Scenario: Aufteilen

- **WHEN** der Befehl auf die mitgelieferte monolithische Konfiguration angewendet wird
- **THEN** existiert pro Profil eine Datei im Profilverzeichnis, die Hauptdatei enthält `profiles_dir`, und die zusammengeführte Sicht ist unverändert

#### Scenario: Zweiter Aufruf

- **WHEN** der Befehl auf eine bereits aufgeteilte Konfiguration angewendet wird
- **THEN** meldet er, dass nichts zu tun ist, und ändert keine Datei

#### Scenario: Validierung schlägt fehl

- **WHEN** das aufgeteilte Ergebnis die Validierung nicht besteht
- **THEN** bleibt die ursprüngliche Konfiguration unverändert und der Befehl nennt den Fehler

### Requirement: Konfigurationsprüfung umfasst alle Dateien

Die Konfigurationsprüfung des Daemons (`--check-config`) SHALL den gesamten
Dateisatz laden und validieren und bei Erfolg die Zahl der geladenen
Profildateien nennen. Fehlt das konfigurierte Profilverzeichnis, MUST die
Prüfung mit dem Verzeichnisnamen fehlschlagen.

#### Scenario: Prüfung eines Dateisatzes

- **WHEN** `--check-config` auf eine Konfiguration mit sechs Profildateien läuft
- **THEN** meldet sie Erfolg und nennt sechs geladene Profildateien

#### Scenario: Fehlendes Verzeichnis

- **WHEN** `profiles_dir` auf ein nicht vorhandenes Verzeichnis zeigt
- **THEN** schlägt die Prüfung mit dem Verzeichnisnamen fehl
