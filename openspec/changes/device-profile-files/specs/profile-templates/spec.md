# Spec Delta

## Purpose

Erlaubt eine kompakte Deklaration wiederkehrender Profilstrukturen (Bänke,
Control-Gruppen, Layout-Zellen). Die Konfiguration wird beim Laden zur
ausgeschriebenen Form expandiert, sodass API, Oberfläche und Laufzeit
unverändert arbeiten.

## ADDED Requirements

### Requirement: Bankanzahl statt ausgeschriebener Bänke

Ein MIDI-Profil SHALL über `bank_count` (1 bis 16) die Bänke 1 bis `bank_count`
mit Kanal gleich Banknummer und ohne Noten erzeugen. Eine ausdrücklich
definierte Bank mit gleicher Nummer MUST die erzeugte ersetzen. Eine
ausdrückliche Bank mit einer Nummer über `bank_count` MUST abgelehnt werden.
Alle Bank-Regeln (eindeutige Kanäle, Noten je Bank) MUST nach der Expansion
gelten.

#### Scenario: Sechzehn leere Bänke

- **WHEN** ein Profil `bank_count = 16` und keine ausdrücklichen Bänke angibt
- **THEN** besitzt es 16 Bänke mit Kanal gleich Nummer und ohne Noten, identisch zu 16 ausgeschriebenen Bänken

#### Scenario: Ausdrückliche Bank überschreibt

- **WHEN** zusätzlich Bank 1 mit Noten definiert ist
- **THEN** trägt Bank 1 diese Noten, und die Bänke 2 bis 16 bleiben erzeugt und leer

#### Scenario: Bank über der Anzahl

- **WHEN** `bank_count = 4` gilt und eine ausdrückliche Bank 5 definiert ist
- **THEN** lehnt die Validierung die Bank mit ihrer Position ab

### Requirement: Control-Gruppen

Ein Profil SHALL Controls über Gruppen aus Präfix, Art, Anzahl und optionalem
Label-Muster deklarieren können; eine Gruppe mit Präfix `p` und Anzahl `n`
erzeugt die Controls `p_1` bis `p_n`. Das Label-Muster MUST den Platzhalter
`{n}` unterstützen und eine Startzahl für die Zählung erlauben. Gruppen und
ausdrücklich ausgeschriebene Controls MUST sich im selben Profil ausschließen.

#### Scenario: Fünf Fader

- **WHEN** eine Gruppe Präfix `mc_fader`, Art `fader`, Anzahl 5 und Label `F{n}` angibt
- **THEN** existieren die Controls `mc_fader_1` bis `mc_fader_5` mit den Labels `F1` bis `F5`

#### Scenario: Fortlaufende Beschriftung über Gruppen

- **WHEN** eine zweite Tastengruppe Label `B{n}` mit Startzahl 6 angibt
- **THEN** tragen ihre Controls die Labels `B6` aufwärts

#### Scenario: Gruppen und ausgeschriebene Controls gemischt

- **WHEN** ein Profil sowohl Gruppen als auch ausgeschriebene Controls enthält
- **THEN** lehnt die Validierung das Profil mit beiden Schlüsseln ab

#### Scenario: Doppelte Control-Namen

- **WHEN** zwei Gruppen dieselben Control-Namen erzeugen
- **THEN** lehnt die Validierung ab wie bei ausgeschriebenen doppelten Controls

#### Scenario: Zwei Geräte desselben Modells

- **WHEN** zwei Profile mit gleichen Gruppen, aber unterschiedlichen Präfixen (etwa `mc_` und `mc2_`) und je einem eigenen Gerät konfiguriert sind
- **THEN** sind beide Profile gültig, ihre Control-Namen kollidieren nicht, und jedes Gerät hat seine eigene Notenbelegung

#### Scenario: Zwei Profile mit gleichem Präfix

- **WHEN** zwei Profile Gruppen mit demselben Präfix erzeugen
- **THEN** lehnt die Validierung ab und nennt die doppelten Control-Namen sowie beide Profile

### Requirement: Layout-Zellenmuster

Eine Layout-Zelle SHALL über `count` als Muster deklariert werden können, mit
Control-Muster, Label-Muster (Platzhalter `{n}`), optionaler Farbe und
optionaler Startzahl; sie erzeugt `count` Zellen in derselben Reihe. Muster und
ausgeschriebene Zellen MUST in einer Reihe mischbar sein. Ein Muster MUST NOT
mit `row`, `col`, `col_span` oder `row_span` kombiniert werden. Referenzen auf
unbekannte Controls MUST wie bei ausgeschriebenen Zellen abgelehnt werden.

#### Scenario: Reihe aus einem Muster

- **WHEN** eine Reihe eine Zelle mit Control-Muster `mc_click_{n}`, Label `K{n}`, Farbe `green` und `count = 5` enthält
- **THEN** besteht die Reihe aus fünf Zellen mit den Controls `mc_click_1` bis `mc_click_5` und den Labels `K1` bis `K5`

#### Scenario: Zweite Reihe ab Startzahl

- **WHEN** eine Reihe für Tasten 7 bis 12 ein Muster mit Startzahl 7 und `count = 6` angibt
- **THEN** beginnt sie bei `mcp_button_7` und endet bei `mcp_button_12`

#### Scenario: Muster mit absoluter Position

- **WHEN** ein Muster zusätzlich `row` und `col` angibt
- **THEN** lehnt die Validierung die Zelle mit ihrer Position ab

#### Scenario: Unbekannte Control-Referenz

- **WHEN** ein Zellenmuster ein Control erzeugt, das im Profil nicht existiert
- **THEN** lehnt die Validierung das Layout mit der Position des Musters ab

### Requirement: Expansion ist für alle Verbraucher unsichtbar

Die expandierte Konfiguration SHALL in jeder Hinsicht einer ausgeschriebenen
Konfiguration entsprechen: `GET /api/config`, die Geräte-API, das Layout und die
Laufzeit MUST dieselben Werte liefern. Die kompakten Schlüssel MUST NOT in der
API erscheinen.

#### Scenario: Kompakt gleich ausgeschrieben

- **WHEN** dasselbe Profil einmal kompakt und einmal vollständig ausgeschrieben konfiguriert wird
- **THEN** liefert `GET /api/config` für beide eine identische Profilstruktur ohne `bank_count` oder Gruppen

### Requirement: Kompakte Form bleibt beim Schreiben erhalten

Speichert die Oberfläche eine Bank-Belegung, SHALL die Profildatei die kompakte
Deklaration behalten: `bank_count` bleibt bestehen, und nur Bänke mit Noten oder
abweichendem Kanal werden ausdrücklich geschrieben. Control-Gruppen und
Layout-Muster MUST unverändert erhalten bleiben, Kommentare ebenfalls.

#### Scenario: Erste Belegung lernen

- **WHEN** in einem Profil mit `bank_count = 16` die Noten von Bank 1 gespeichert werden
- **THEN** enthält die Profildatei weiterhin `bank_count = 16` und genau eine ausdrückliche Bank 1, nicht 16 Bänke

#### Scenario: Belegung wieder löschen

- **WHEN** alle Noten einer Bank entfernt werden und ihr Kanal der Nummer entspricht
- **THEN** wird ihre ausdrückliche Bank aus der Datei entfernt und die erzeugte leere Bank gilt wieder

#### Scenario: Änderung des Inventars per API

- **WHEN** ein API-Patch Controls für ein Profil mit Control-Gruppen setzen will
- **THEN** lehnt die Validierung die Änderung ab, weil sich Gruppen und ausgeschriebene Controls ausschließen
