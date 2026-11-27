# Spec Delta

## Purpose

Beschreibt alle in der Weboberfläche editierbaren Konfigurationsfelder
maschinenlesbar, damit Formulare, Wertebereiche und Hilfe aus einer Quelle
entstehen und neue Einstellungen ohne eigene Oberflächenarbeit verfügbar werden.

## ADDED Requirements

### Requirement: Veröffentlichter Konfigurationskatalog

Der Daemon SHALL unter `GET /api/config/schema` einen Katalog aller
editierbaren Konfigurationsfelder ausliefern. Jeder Eintrag MUST Pfad, Gruppe,
Scope (`device`, `mapping` oder `global`), Typ, Default, Label und Hilfe
enthalten. Geheimnisse wie das MA2-Passwort oder die PIN MUST NOT im Katalog
erscheinen.

#### Scenario: Katalog abrufen

- **WHEN** die Oberfläche `GET /api/config/schema` aufruft
- **THEN** erhält sie je Feld Pfad, Gruppe, Scope, Typ, Default, Label und Hilfe

#### Scenario: Geheimnis bleibt verborgen

- **WHEN** das MA2-Passwort oder die PIN gesetzt ist
- **THEN** enthält die Antwort weder Feld noch Wert und nennt nur die übrigen Felder derselben Gruppe

#### Scenario: Neues Feld ist enthalten

- **WHEN** die Konfiguration um ein editierbares Feld erweitert wird
- **THEN** erscheint es genau einmal im Katalog, ohne dass die Oberfläche angepasst wurde

### Requirement: Gemeinsame Grenzen mit der Validierung

Wertebereich, Auswahlwerte und Defaults im Katalog SHALL aus denselben
Konstanten stammen wie die Konfigurationsvalidierung. Ein Katalogwert außerhalb
des tatsächlich akzeptierten Bereichs oder ein Default, den die Validierung
ablehnt, MUST durch einen automatisierten Test scheitern. Der Katalog MUST
`min`, `max`, `step` und `enum` so angeben, wie sie geprüft werden.

#### Scenario: Grenzwert wird akzeptiert

- **WHEN** ein Feld auf seinen im Katalog genannten Minimalwert gesetzt wird
- **THEN** akzeptiert die Validierung den Wert

#### Scenario: Wert unter dem Minimum

- **WHEN** ein Feld einen Wert unterhalb des Katalog-Minimums erhält
- **THEN** lehnt die Validierung ihn ab und nennt den gültigen Bereich

#### Scenario: Default ist gültig

- **WHEN** ein Feld ohne eigenen Eintrag geladen wird
- **THEN** entspricht der wirksame Wert dem Katalog-Default und wird von der Validierung akzeptiert

### Requirement: Scope bestimmt die Platzierung

Jedes Feld MUST genau einen Scope besitzen. Felder mit Scope `device`
erscheinen im Geräte-Tab, mit Scope `mapping` im Mapping-Tab, mit Scope
`global` in einem gemeinsamen Abschnitt. Zuweisungsbezogene Einstellungen, die
die Parity-Regel beiden Tabs zuordnet, MUST in beiden Tabs erreichbar sein,
ohne einen zweiten Schreibpfad zu erzeugen.

#### Scenario: LED-Wert gehört zum Gerät

- **WHEN** ein Feld aus `[led]` im Katalog geführt wird
- **THEN** erscheint es im Geräte-Tab und nicht als eigenes Mapping-Feld

#### Scenario: Auflösung gehört zum Mapping

- **WHEN** ein Feld aus `[mapping.encoder_resolution]` im Katalog geführt wird
- **THEN** erscheint es im Mapping-Tab

#### Scenario: Zuweisung in beiden Tabs

- **WHEN** ein Feld die Zuweisungs-Parität betrifft, etwa der Screen-Modus einer Taste
- **THEN** ist es in beiden Tabs über denselben Schreibpfad erreichbar

### Requirement: Feldtypen und Referenzen

Der Katalog SHALL die Typen `integer`, `number`, `boolean`, `text`, `enum`,
`color-index`, `control-ref`, `note`, `note-list` und `path` verwenden. Ein
`control-ref` MUST gegen die vorhandenen Controls aufgelöst werden; die
symbolischen Werte `auto` und `none` MUST angeboten werden, sofern das Feld sie
unterstützt. Eine unauflösbare Referenz MUST als Feldfehler erscheinen.

#### Scenario: Control-Referenz wird aufgelöst

- **WHEN** ein Feld auf ein vorhandenes Control verweist
- **THEN** zeigt die Oberfläche dessen Namen und die Referenz wird gespeichert

#### Scenario: Auto wird angezeigt

- **WHEN** ein Feld den Wert `auto` trägt
- **THEN** zeigt die Oberfläche den daraus aufgelösten Control und kennzeichnet ihn als automatisch

#### Scenario: Unbekanntes Control

- **WHEN** ein Feld auf ein Control verweist, das nicht mehr existiert
- **THEN** meldet die Oberfläche einen Feldfehler mit Pfad und Referenz und die bisherige Konfiguration bleibt aktiv

### Requirement: Bedingte Sichtbarkeit

Ein Feld MAY eine Sichtbarkeitsbedingung auf andere Felder tragen. Ein
ausgeblendetes Feld MUST seinen gespeicherten Wert behalten und MUST NOT
stillschweigend auf den Default zurückfallen. Ein Formular MUST nur die
sichtbaren Felder als änderbar anbieten.

#### Scenario: Feld wird wieder eingeblendet

- **WHEN** ein Feld wegen einer Bedingung ausgeblendet und die Bedingung später wieder erfüllt ist
- **THEN** erscheint der zuvor gespeicherte Wert unverändert

#### Scenario: Geräteprofil fehlt

- **WHEN** eine Einstellung nur für ein vorhandenes Geräteprofil gilt und das Profil fehlt
- **THEN** wird der Abschnitt ausgeblendet und es entsteht kein ungültiger Patch

### Requirement: Neustart- und Expertenkennzeichnung

Felder, deren Änderung einen Dienstneustart benötigt, MUST als
`restart_required` gekennzeichnet sein. Selten benötigte Felder MUST als
`advanced` gelten. Die Oberfläche MUST erweiterte Felder eingeklappt anzeigen
und neustartpflichtige Felder vor dem Speichern benennen.

#### Scenario: Neustartpflichtiges Feld

- **WHEN** ein Feld wie die Web-Bind-Adresse geändert wird
- **THEN** weist die Oberfläche auf den erforderlichen Dienstneustart hin

#### Scenario: Erweiterte Felder

- **WHEN** ein Abschnitt nur erweiterte Felder enthält
- **THEN** sind sie eingeklappt und werden erst auf Wunsch angezeigt

### Requirement: Vollständige Abdeckung

Der Katalog SHALL jedes editierbare Feld aus `config.toml` genau einmal
beschreiben. Bewusst nicht katalogisierte Felder MUST in einer begründeten
Ausnahmeliste stehen. Ein automatisierter Test MUST fehlende, doppelte und
veraltete Pfade erkennen.

#### Scenario: Jedes Feld genau einmal

- **WHEN** der Katalog gegen die Konfigurationsfelder geprüft wird
- **THEN** enthält er jedes editierbare Feld genau einmal

#### Scenario: Veralteter Pfad

- **WHEN** ein Katalogeintrag auf ein nicht mehr vorhandenes Feld zeigt
- **THEN** scheitert der Test mit Angabe des Pfades

#### Scenario: Begründete Ausnahme

- **WHEN** ein Feld nicht im Katalog erscheint
- **THEN** nennt die Ausnahmeliste einen Grund und der Test akzeptiert ihn
