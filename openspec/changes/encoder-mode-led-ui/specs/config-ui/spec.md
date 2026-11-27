# Spec Delta

## MODIFIED Requirements

### Requirement: Live-Status

Die Oberfläche SHALL den aktuellen Zustand über eine dauerhafte
WebSocket-Verbindung anzeigen: Verbindung zur onPC, Session, erkannte Geräte,
Rate-Limiter, die letzten Frame-Typen und den Encoder-Modus. Der Status MUST
festen und momentanen Modus getrennt sowie den effektiven Modus melden; die
Oberfläche MUST daraus den LED-Zustand ableiten: grün im effektiven
Screen-Modus, rot im Attribut-Modus. Zugangsdaten und Passwort-Hashes MUST NOT
Teil der Statusdaten sein. Die UI-Verbindung MUST sich nach einer Unterbrechung
selbstständig wieder aufbauen.

#### Scenario: Verbindungszustand ändert sich

- **WHEN** die onPC neu startet und der Daemon reconnectet
- **THEN** wechselt die Anzeige ohne manuelles Neuladen von „getrennt“ über „verbinde“ zu „verbunden“

#### Scenario: Frame-Aktivität

- **WHEN** Tasten gedrückt oder Encoder gedreht werden
- **THEN** aktualisieren sich Frame-Zähler und die Liste der letzten Frame-Typen in Echtzeit

#### Scenario: Encoder-Modus sichtbar

- **WHEN** die Screen-Modus-Taste am Gerät gedrückt wird
- **THEN** meldet der Status innerhalb einer Sekunde den neuen Modus und die Oberfläche zeigt den passenden LED-Zustand

#### Scenario: Momentaner Modus sichtbar

- **WHEN** der momentane Screen-Modifier gehalten wird, ohne den festen Modus zu ändern
- **THEN** zeigt die Oberfläche innerhalb einer Sekunde den effektiven Screen-Modus und nach dem Loslassen wieder den festen Modus

#### Scenario: UI-Verbindung bricht ab

- **WHEN** die WebSocket-Verbindung des Browsers zum Daemon unterbrochen wird
- **THEN** baut die Oberfläche die Verbindung automatisch wieder auf und zeigt den aktuellen Zustand

## ADDED Requirements

### Requirement: Kataloggetriebene Einstellungsabschnitte

Die Oberfläche SHALL Einstellungsabschnitte aus dem Konfigurationskatalog
rendern. Ein katalogisiertes Feld MUST ohne seitenspezifischen Formularcode
erscheinen und Eingaben, Wertebereich, Auswahlwerte, Default, Hilfe und
erweiterte Felder aus dem Katalogeintrag übernehmen. Gemeinsame
Feldschreibweisen MUST von allen Abschnitten genutzt werden.

#### Scenario: Neues Feld ohne Oberflächenänderung

- **WHEN** das Backend ein neues katalogisiertes Feld derselben Gruppe ausliefert
- **THEN** erscheint es im zugehörigen Abschnitt und lässt sich speichern

#### Scenario: Wertebereich aus dem Katalog

- **WHEN** ein Zahlenfeld mit Minimum und Maximum katalogisiert ist
- **THEN** übernimmt das Eingabefeld diese Grenzen und zeigt einen Verstoß vor dem Speichern an

#### Scenario: Unbekannter Feldtyp

- **WHEN** die Oberfläche einen katalogisierten Typ nicht kennt
- **THEN** zeigt sie das Feld schreibgeschützt mit Hinweis, statt es zu verbergen oder falsch zu speichern

### Requirement: Platzierung nach Scope und Parity-Regel

Die Oberfläche SHALL Felder nach ihrem Scope platzieren: `device` im
Geräte-Tab, `mapping` im Mapping-Tab, `global` in einem gemeinsamen Abschnitt.
Ein Abschnitt MUST auf den fachlich zuständigen Tab verweisen, wenn er dort
nicht selbst angeboten wird. Zuweisungsbezogene Einstellungen MUST in beiden
Tabs über denselben Zustand und Schreibpfad erreichbar sein.

#### Scenario: LED-Verweis aus dem Mapping-Tab

- **WHEN** der Mapping-Tab einen LED-Hinweis anzeigt
- **THEN** führt er in den LED-Abschnitt des Geräte-Tabs, ohne die Werte dort zu duplizieren

#### Scenario: Screen-Modus in beiden Tabs

- **WHEN** eine Taste in einem der beiden Tabs als Screen-Modus-Taste belegt wird
- **THEN** zeigt der andere Tab dieselbe Belegung ohne Neuladen und ohne abweichenden Patch

#### Scenario: Kein zweiter Schreibpfad

- **WHEN** dieselbe Einstellung aus beiden Tabs geändert wird
- **THEN** entsteht jeweils derselbe Patch und dieselbe gespeicherte Konfiguration

### Requirement: Feldzustand, Validierung und Speichern

Ein Abschnitt SHALL geladene Werte, geänderte Werte und Speicherstatus
unterscheiden. Validierungsfehler MUST am betroffenen Feld erscheinen und die
bisherige Konfiguration MUST aktiv bleiben. Das Speichern MUST über den
bestehenden Konfigurationspfad mit Generation erfolgen; ein veralteter Entwurf
MUST als Konflikt behandelt werden.

#### Scenario: Feldbezogener Fehler

- **WHEN** das Backend einen ungültigen Farbindex oder eine unbekannte Control-Referenz ablehnt
- **THEN** erscheint die Meldung am Feld und die vorherige Konfiguration bleibt aktiv

#### Scenario: Ungespeicherte Änderungen

- **WHEN** ein Abschnitt verlassen wird, ohne zu speichern
- **THEN** weist die Oberfläche auf die ungespeicherten Änderungen hin und bietet Speichern oder Verwerfen an

#### Scenario: Veralteter Entwurf

- **WHEN** die Konfiguration zwischen Laden und Speichern an anderer Stelle geändert wurde
- **THEN** meldet das Speichern den Konflikt, ohne die neuere Konfiguration zu überschreiben

### Requirement: Vorschau von Farben und LED-Noten

Farbfelder MUST ihren Farbindex zusammen mit der aufgelösten Bezeichnung als
Vorschau zeigen. Notenfelder MUST die belegte LED-Funktion und Konflikte mit
anderen Funktionen anzeigen. Die Vorschau MUST ohne Hardwarezugriff
auskommen und MUST das gespeicherte Verhalten nicht verändern.

#### Scenario: Farbindex anzeigen

- **WHEN** ein Feld einen Farbindex zwischen 0 und 127 trägt
- **THEN** zeigt die Oberfläche den Index, die Palettenbezeichnung sofern vorhanden und ein Farbfeld

#### Scenario: Notenkonflikt

- **WHEN** eine Modus-, Fine- oder Nipple-Note auch von einer anderen Funktion oder einem Profil beansprucht wird
- **THEN** kennzeichnet die Oberfläche den Konflikt und nennt beide Funktionen

#### Scenario: Kein Hardwarezugriff

- **WHEN** die Vorschau angezeigt oder ein Farbfeld geändert wird
- **THEN** wird kein LED-Frame an ein Gerät gesendet

### Requirement: ASL-LED-Abschnitt im Geräte-Tab

Der Geräte-Tab SHALL einen Abschnitt für die festen ASL-LED-Funktionen
anbieten: Gerät, Modus-Note, Modus-Farben für Screen und Attribut, Helligkeit,
Helligkeits- und Farbkanal sowie Fine- und Nipple-Funktion mit Note, Farbe und
Helligkeiten. Je erkanntem Geräteprofil MUST das LED-Feedback mit Protokoll,
Notenliste und Takt bearbeitbar sein.

#### Scenario: Alle LED-Werte bearbeiten

- **WHEN** der Benutzer den LED-Abschnitt öffnet
- **THEN** sind alle `[led]`-Werte und die Feedback-Werte des gewählten Profils sichtbar und speicherbar

#### Scenario: LED deaktiviert

- **WHEN** die LED-Ausgabe ausgeschaltet ist
- **THEN** bleiben die übrigen Felder sichtbar, aber als wirkungslos gekennzeichnet und die Oberfläche erklärt die Folge

#### Scenario: Profil ohne LED-Feedback

- **WHEN** ein Profil kein LED-Feedback deklariert
- **THEN** zeigt der Abschnitt den deaktivierten Zustand und bietet die Aktivierung über die katalogisierten Felder an

### Requirement: Screen-Modus-Abschnitt im Mapping-Tab

Der Mapping-Tab SHALL einen Abschnitt „Screen-Modus & Encoder“ anbieten, der
Toggle-Tasten, den momentanen Modifier samt aufgelöstem Control,
Screen-Encoder-Ziele je Slot sowie Auflösungs- und Beschleunigungswerte
bearbeitbar macht. Der Abschnitt MUST benennen, wenn eine Einstellung nur im
Geräte-Tab verfügbar ist.

#### Scenario: Momentaner Modifier

- **WHEN** der Abschnitt geöffnet wird
- **THEN** zeigt er den eingestellten Wert sowie den daraus aufgelösten Control oder „aus“

#### Scenario: Screen-Encoder-Ziele

- **WHEN** ein Screen-Encoder-Ziel für einen Slot geändert oder entfernt wird
- **THEN** verwendet der Screen-Modus unmittelbar die neue Zuordnung oder lässt den Slot ohne Ziel

#### Scenario: Auflösung und Beschleunigung

- **WHEN** Auflösungswerte, Modifier oder Beschleunigung geändert werden
- **THEN** sind die neuen Werte nach dem Speichern ohne Dienstneustart aktiv und der Abschnitt zeigt sie als gespeichert
