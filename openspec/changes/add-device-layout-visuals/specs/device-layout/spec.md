# Spec Delta

## Purpose

Beschreibt ein datengetriebenes, schematisches Geräte-Layout, damit die
Konfigurationsoberfläche Tastatur und MIDI-Controller räumlich darstellen kann,
ohne die Anordnung im Frontend hartzukodieren.

## ADDED Requirements

### Requirement: Layout als Konfigurationsdaten

Die Konfiguration SHALL je Gerät ein optionales Layout definieren können, das
die physische Anordnung als Raster aus Reihen und Spalten beschreibt. Jede Zelle
MUST ein Label und optional eine Referenz auf ein logisches Control des Geräts
tragen. Zellen MUST über mehrere Spalten oder Reihen spannen können, damit große
Tasten wie `Pause`, `Please` oder `Store` korrekt dargestellt werden.

#### Scenario: Layout mit einfachen Zellen

- **WHEN** ein Gerät ein Layout mit drei Reihen und vier Spalten definiert
- **THEN** liefert die API genau diese Rasterstruktur mit Label und Control je Zelle

#### Scenario: Große Taste über mehrere Zellen

- **WHEN** eine Zelle eine Spalten- oder Reihenspanne größer als eins angibt
- **THEN** berücksichtigt die Darstellung die Spanne und verschiebt die folgenden Zellen entsprechend

#### Scenario: Zelle ohne Control

- **WHEN** eine Zelle nur ein Label und keine Control-Referenz hat
- **THEN** wird sie als Beschriftung dargestellt und löst keine Aktion aus

### Requirement: Layout ist optional und rein darstellend

Fehlt für ein Gerät ein Layout, MUST der Daemon weiterhin starten und die
tabellarische Konfiguration MUST nutzbar bleiben. Ein Layout MUST NOT das
Mapping, die Ereignisverarbeitung oder die an die onPC gesendeten Frames
beeinflussen.

#### Scenario: Gerät ohne Layout

- **WHEN** ein Gerät konfiguriert ist, aber keinen Layout-Block hat
- **THEN** startet der Daemon normal und die API meldet für dieses Gerät kein Layout

#### Scenario: Layout ändert das Verhalten nicht

- **WHEN** nur das Layout geändert wird
- **THEN** bleiben erkannte Geräte, Mapping und gesendete Frames unverändert

### Requirement: Layout-Validierung

Beim Laden MUST jede Control-Referenz im Layout gegen die Controls des
zugehörigen Geräteprofils geprüft werden. Eine unbekannte Referenz MUST als
Konfigurationsfehler mit Gerät, Reihe, Spalte und Control gemeldet werden.
Layouts MUST nur für konfigurierte Geräte erlaubt sein.

#### Scenario: Unbekanntes Control im Layout

- **WHEN** ein Layout eine Control-Referenz enthält, die im Profil des Geräts nicht vorkommt
- **THEN** schlägt die Validierung mit Gerät, Position und Control fehl

#### Scenario: Layout für unbekanntes Gerät

- **WHEN** ein Layout-Block verweist auf ein Gerät, das nicht in `[devices.*]` steht
- **THEN** schlägt die Validierung mit dem Gerätenamen fehl

### Requirement: Cherry-Layout

Für die Cherry G86-63400 SHALL ein Layout mitgeliefert werden, das die
bedruckten Tasten des aktuellen Aufbaus in Reihen und Spalten abbildet:
Funktionsblock oben, Ziffernblock und Sondertasten unten, inklusive der großen
Tasten `Pause`, `Go+`, `Go-`, `Store` und `Please`.

#### Scenario: Cherry-Layout wird ausgeliefert

- **WHEN** die Oberfläche das Gerät `cherry` lädt
- **THEN** enthält die Antwort ein Raster, dessen Labels den bedruckten Tasten entsprechen

### Requirement: ASL-Layout

Für den ASL MK2-E4B3 SHALL ein schematisches Layout mitgeliefert werden, das
vier Encoder, deren Push-Tasten und die drei eigenständigen Tasten abbildet.

#### Scenario: ASL-Layout wird ausgeliefert

- **WHEN** die Oberfläche das Gerät `asl` lädt
- **THEN** enthält die Antwort vier Encoder-Zellen mit `encoder.1` bis `encoder.4` sowie die Tasten-Zellen
