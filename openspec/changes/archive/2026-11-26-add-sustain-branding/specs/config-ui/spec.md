# Spec Delta

## ADDED Requirements

### Requirement: Produktname in der Oberfläche

Die Oberfläche SHALL den Produktnamen `gMA2PiControl` im Browser-Titel, in der
Topbar und im PIN-Gate anzeigen. Die CLI MUST denselben Namen in `--version`,
`--help` und der Startzeile verwenden, die API-Dokumentation und die
systemd-Beschreibung MUST ihn nennen. Der Browser-Tab MUST ein lokales Favicon
anzeigen. Technische Bezeichner — Python-Paket und Entrypoint `ma2pi`,
Service-Unit und -User, StateDirectory, Passwortdatei, Recovery-SSID und
API-Routen — MUST unverändert bleiben.

#### Scenario: Oberfläche zeigt den Produktnamen

- **WHEN** die Web-Oberfläche geöffnet wird
- **THEN** zeigt der Browser-Tab `gMA2PiControl`, die Topbar den zweifarbigen Produktnamen und das PIN-Gate eine Überschrift mit demselben Namen

#### Scenario: CLI nennt den Produktnamen

- **WHEN** `python -m ma2pi --version` ausgeführt wird
- **THEN** beginnt die Ausgabe mit `gMA2PiControl` gefolgt von der Version

#### Scenario: Favicon wird ausgeliefert

- **WHEN** die Oberfläche im Browser geladen wird
- **THEN** liefert der Daemon `/favicon.svg` lokal aus und der Tab zeigt das Symbol

#### Scenario: Technische Pfade bleiben stabil

- **WHEN** der Dienst nach dem Rebranding neu gestartet wird
- **THEN** bleiben `ma2pi.service`, Benutzer `ma2pi`, das StateDirectory und die Konfigurationsdateien unverändert nutzbar

### Requirement: Zentrale Design-Tokens

Das Frontend SHALL Farben, Schriften, Radien und den Fokusring über eine
zentrale Token-Schicht in `web/src/app.css` definieren. Komponenten MUST ihre
Farben ausschließlich über diese Tokens beziehen. Hartkodierte Farbwerte MUST
auf die Token-Definition, die Geräteaufkleber-Palette und die Hardware-LED-Farben
beschränkt bleiben.

#### Scenario: Akzentfarbe an einer Stelle änderbar

- **WHEN** der Wert von `--accent` in `app.css` geändert wird
- **THEN** ändern sich alle primären Aktionen und aktiven Zustände der Oberfläche, ohne dass eine Komponente angepasst werden muss

### Requirement: Sustain-Palette als UI-Akzent

Die Basisfarben MUST `#0A0A0A` (Hintergrund), `#F5F5F0` (Text) sowie
`#1A1A1A`/`#2A2A2A` (Flächen) entsprechen. Als Akzent-, Aktions- und
Aktivfarbe MUST Grün (`#6CBB89`, `#4A9A6A`, `#7DD49B`) verwendet werden. Blau
MUST NOT in diesen Rollen erscheinen.

#### Scenario: Kein Blau mehr in der Oberfläche

- **WHEN** die Seiten Status, Mapping, Geräte, Netzwerk und Konfiguration durchgesehen werden
- **THEN** erscheint keine der bisherigen Blautöne als Akzent, Button- oder Aktivfarbe

#### Scenario: Aufkleberfarben bleiben unterscheidbar

- **WHEN** eine Gerätefläche mit Aufkleberfarben aus `config.toml` dargestellt wird
- **THEN** bleiben `green`, `blue`, `red`, `yellow`, `grey`, `black` und `white` als eigenständige, unterscheidbare Farben erhalten

### Requirement: Lokal gebündelte Typografie

Die Oberfläche SHALL Bebas Neue für Marke und Überschriften sowie DM Sans für
Fließtext und Bedienelemente verwenden. Beide Schriften MUST als lokale
WOFF2-Dateien im Build liegen und über `@font-face` eingebunden werden; Verweise
auf externe Schrift- oder CDN-Hosts MUST NOT enthalten sein. Die zugehörigen
OFL-Lizenztexte MUST mitgeliefert werden. Bebas Neue MUST NOT für Fließtext,
Tabellen oder Formularinhalte verwendet werden.

#### Scenario: Oberfläche ohne Internetzugang

- **WHEN** die Oberfläche in einem Netz ohne Internetzugang geladen wird
- **THEN** werden alle Schriften korrekt dargestellt und es findet keine Anfrage an einen externen Host statt

#### Scenario: Offline-Prüfung bleibt grün

- **WHEN** `npm run check:offline` nach dem Build ausgeführt wird
- **THEN** meldet die Prüfung keine externen Ressourcen

#### Scenario: Überschriften in Display-Schrift

- **WHEN** eine Seite mit Seiten- oder Dialogtitel geöffnet wird
- **THEN** ist der Titel in Bebas Neue gesetzt und der übrige Text in DM Sans

### Requirement: Semantische Zustände und Fokus

Erfolg, Fehler und Warnung SHALL eigene, in die Palette eingepasste Farben und
Flächen besitzen. Diese Zustände MUST zusätzlich durch Text oder Symbol
erkennbar sein und dürfen nicht allein über Farbe kommuniziert werden. Text auf
diesen Flächen MUST ein Kontrastverhältnis von mindestens 4,5:1 erreichen. Jedes
fokussierbare Bedienelement MUST einen sichtbaren Fokusring verwenden.

#### Scenario: Fehlermeldung bleibt lesbar

- **WHEN** das Speichern einer Konfiguration abgelehnt wird
- **THEN** erscheint die Meldung in der Fehlerfarbe auf der Fehlerfläche, erreicht mindestens 4,5:1 Kontrast und enthält einen erläuternden Text

#### Scenario: Fokus ist sichtbar

- **WHEN** mit der Tastatur durch Buttons und Formularfelder navigiert wird
- **THEN** zeigt das aktive Element einen grünen Fokusring mit sichtbarem Abstand zum Rahmen

#### Scenario: Warnung nicht nur farblich

- **WHEN** eine Warnung angezeigt wird
- **THEN** unterscheidet sie sich von einem Fehler auch durch Symbol oder Formulierung, nicht nur durch den Farbton
