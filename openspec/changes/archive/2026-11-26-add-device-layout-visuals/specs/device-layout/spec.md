# Spec Delta

## Purpose

Beschreibt ein datengetriebenes, schematisches Geräte-Layout, damit die
Konfigurationsoberfläche Tastaturen und MIDI-Controller räumlich darstellen und
einzelne Felder direkt ihren logischen Controls zuordnen kann, ohne die
Anordnung im Frontend hartzukodieren.

## ADDED Requirements

### Requirement: Layout als Rasterdaten

Die Konfiguration SHALL je Geräteprofil ein optionales Layout mit einer Bezugsbreite
(`columns`) und Reihen aus Zellen definieren. Jede Zelle MUST ein Label tragen
und MAY eine Referenz auf ein logisches Control des Geräts enthalten. Zellen
MUST über mehrere Spalten (`col_span`) oder Reihen (`row_span`) spannen können.
Zellen MAY mit `row` und `col` absolut im Raster positioniert werden; beide
Angaben MUST gemeinsam erfolgen und belegte Rasterfelder MUST NOT überlappen.

#### Scenario: Layout mit einfachen Zellen

- **WHEN** ein Profil ein Layout mit drei Reihen und vier Spalten definiert
- **THEN** liefert die API genau diese Rasterstruktur mit Label und Control je Zelle

#### Scenario: Große Taste über mehrere Zellen

- **WHEN** eine Zelle eine Spalten- oder Reihenspanne größer als eins angibt
- **THEN** berücksichtigt die Darstellung die Spanne und verschiebt die folgenden Zellen entsprechend

#### Scenario: Zelle ohne Control

- **WHEN** eine Zelle nur ein Label und keine Control-Referenz hat
- **THEN** wird sie als Beschriftung dargestellt und löst keine Aktion aus

#### Scenario: Absolute Zellposition

- **WHEN** eine Zelle `row` und `col` angibt
- **THEN** erscheint sie an dieser Rasterposition, auch wenn die Reihenfolge in der Konfiguration abweicht

#### Scenario: Überlappende Zellen

- **WHEN** zwei absolute Zellen dasselbe Rasterfeld belegen
- **THEN** lehnt die Konfigurationsprüfung das Layout mit einem Fehler ab

### Requirement: Optionale Aufkleberfarbe

Jede Layout-Zelle MAY eine Farbe aus der dokumentierten Palette (`green`,
`blue`, `red`, `yellow`, `grey`, `black`, `white`) tragen. Fehlt die Angabe,
MUST die Darstellung eine neutrale Standardfarbe verwenden.

#### Scenario: Bedruckte Taste mit Farbe

- **WHEN** eine Zelle die Farbe `green` angibt
- **THEN** wird sie in der Flächenansicht grün dargestellt

#### Scenario: Zelle ohne Farbangabe

- **WHEN** eine Zelle keine Farbe angibt
- **THEN** verwendet die Darstellung die neutrale Standardfarbe

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
Konfigurationsfehler mit Profil, Reihe, Spalte und Control gemeldet werden.
Layouts MUST nur für existierende Profile erlaubt sein.

#### Scenario: Unbekanntes Control im Layout

- **WHEN** ein Layout eine Control-Referenz enthält, die im referenzierten Profil nicht vorkommt
- **THEN** schlägt die Validierung mit Profil, Position und Control fehl

#### Scenario: Layout für unbekanntes Profil

- **WHEN** ein Layout-Block verweist auf ein Profil, das nicht in `[profiles.*]` steht
- **THEN** schlägt die Validierung mit dem Profilnamen fehl

#### Scenario: Doppeltes Control im Layout

- **WHEN** dasselbe Control in zwei Zellen eines Layouts steht
- **THEN** schlägt die Validierung mit Profil und Control fehl

### Requirement: Layout-API

`GET /api/devices` SHALL je Gerät das Layout seines Profils mit allen Zellen
ausliefern oder `null`, wenn keines existiert.

#### Scenario: Layout in der Geräteantwort

- **WHEN** die Oberfläche `GET /api/devices` aufruft
- **THEN** enthält jedes Gerät mit Layout dessen Raster, Breite und Zellen

#### Scenario: Gerät ohne Layout in der Antwort

- **WHEN** ein Gerät ohne Layout konfiguriert ist
- **THEN** liefert die Antwort für dieses Gerät `layout: null`

### Requirement: Mitgeliefertes Cherry-Layout

Für die Cherry G86-63400 SHALL ein Layout mitgeliefert werden, das die
bedruckten Tasten des aktuellen Aufbaus abbildet: Funktionsblock oben,
Ziffernblock und Sondertasten unten, inklusive der großen Tasten `Pause`, `Go+`,
`Go-`, `Store` und `Please` sowie der Farben der Aufkleber.

#### Scenario: Cherry-Layout wird ausgeliefert

- **WHEN** die Oberfläche das Gerät `cherry` lädt
- **THEN** enthält die Antwort ein Raster, dessen Labels den bedruckten Tasten entsprechen und dessen große Tasten die korrekte Spanne besitzen

### Requirement: Mitgeliefertes ASL-Layout

Für den ASL MK2-E4B3 SHALL ein schematisches Layout mitgeliefert werden, das
vier Encoder, deren Push-Tasten und die drei eigenständigen Tasten abbildet.

#### Scenario: ASL-Layout wird ausgeliefert

- **WHEN** die Oberfläche das Gerät `asl` lädt
- **THEN** enthält die Antwort vier Encoder-Zellen mit `encoder.1` bis `encoder.4` sowie die Tasten-Zellen

### Requirement: Mitgelieferte MIDICRAFT-Layouts

Für jedes der sechs aktuellen MIDICRAFT-Modelle SHALL ein Layout mitgeliefert
werden, das die physische Anordnung der dokumentierten Controls abbildet:
`PUSH²` 30 Tasten, `FADE²` fünf Fader und 20 Tasten, `TURN²` 15 Tasten und 15
Potis, `MIX²` fünf Fader, 15 Tasten und fünf Potis, `ENC` fünf Fader, 15 Tasten
und fünf Encoder, `SPOT` fünf Fader, zehn Tasten und zehn Potis.

#### Scenario: MIDICRAFT-Layout wird ausgeliefert

- **WHEN** die Oberfläche ein konfiguriertes MIDICRAFT-Gerät lädt
- **THEN** enthält die Antwort ein Raster mit genau den dokumentierten Control-Zahlen des Modells

#### Scenario: Modell ohne hinterlegtes Layout

- **WHEN** ein MIDICRAFT-Gerät konfiguriert ist, für das kein Layout existiert
- **THEN** bleibt die tabellarische Ansicht nutzbar und die API meldet `layout: null`
