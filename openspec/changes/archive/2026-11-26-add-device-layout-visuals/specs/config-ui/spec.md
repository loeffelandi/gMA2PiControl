# Spec Delta

## ADDED Requirements

### Requirement: Geräteflächen-Ansicht

Die Geräte-Seite SHALL je aktuell erkanntem Gerät dessen Layout als
schematische Fläche darstellen. Jede Zelle mit Control MUST ihre aktuelle
Belegung auf der gewählten Bank anzeigen. Geräte ohne Layout MUST weiterhin als
Tabelle erscheinen. Konfigurierte, aber nicht angeschlossene Geräte MUST
ausgeblendet werden.

#### Scenario: Cherry wird als Fläche dargestellt

- **WHEN** die Geräte-Seite geöffnet wird und für die Cherry ein Layout konfiguriert ist
- **THEN** erscheint die Tastatur als Raster mit den bedruckten Labels und ihren aktuellen Belegungen

#### Scenario: Gerät ohne Layout

- **WHEN** ein Gerät ohne Layout konfiguriert ist
- **THEN** zeigt die Seite für dieses Gerät die bisherige Tabellenansicht

#### Scenario: Gerät ist nicht angeschlossen

- **WHEN** ein konfiguriertes Gerät nicht erkannt wird
- **THEN** erscheint es nicht in der Geräte-Seite und seine Fläche wird nicht angeboten

### Requirement: Direktzuweisung über die Fläche

Ein Klick auf eine Zelle mit Control SHALL den Zuweisungsdialog für dieses
Control auf der gewählten Bank öffnen. Das Speichern MUST über den bestehenden
Konfigurations-Endpunkt erfolgen und die gesamte Konfiguration serverseitig
validieren. Bei einem Fehler MUST keine Teiländerung gespeichert werden und die
Meldung MUST Gerät, Bank und Control nennen.

#### Scenario: Taste über die Fläche belegen

- **WHEN** eine Zelle angeklickt, ein Hardkey gewählt und gespeichert wird
- **THEN** erscheint die Belegung in der Zelle und in der Mapping-Tabelle

#### Scenario: Ungültige Zuweisung

- **WHEN** der Dialog ein unbekanntes Ziel speichern soll
- **THEN** bleibt die Konfiguration unverändert und die Fehlermeldung nennt Gerät, Bank und Control

### Requirement: Mehrfachauswahl auf einer Fläche

Die Fläche SHALL mehrere Controls desselben Geräts zur Mehrfachzuweisung
auswählen können. Die Auswahlreihenfolge MUST der Klick-Reihenfolge entsprechen
und für den Benutzer sichtbar sein. Ein Wechsel von Gerät oder Bank MUST die
Auswahl leeren. Controls verschiedener Geräte MUST NOT gemeinsam ausgewählt
werden können.

#### Scenario: Fünf Tasten auswählen

- **WHEN** fünf Tasten nacheinander angeklickt werden
- **THEN** sind sie in genau dieser Reihenfolge markiert und die Auswahl zeigt die Anzahl

#### Scenario: Gerätewechsel leert die Auswahl

- **WHEN** bei bestehender Auswahl ein anderes Gerät geöffnet wird
- **THEN** ist die Auswahl leer

### Requirement: Verteilte Zuweisung

Der Zuweisungsdialog SHALL für eine Mehrfachauswahl eine Aktion sowie einen
Startwert und eine Schrittweite annehmen. Bei Executor-Zielen MUST die
Executor-Nummer je ausgewähltem Control in Klick-Reihenfolge um die Schrittweite
erhöht werden; alle übrigen Felder MUST für alle Controls gleich bleiben. Vor
dem Speichern MUST eine Vorschau die resultierenden Ziele zeigen. Die Zuweisung
MUST atomar gespeichert werden.

#### Scenario: Executor 1 bis 5 verteilen

- **WHEN** fünf Tasten ausgewählt sind, Aktion Executor-Button, Startwert 1 und Schrittweite 1 gewählt werden
- **THEN** erhalten die Tasten in Klick-Reihenfolge die Executor-Nummern 1, 2, 3, 4 und 5

#### Scenario: Andere Schrittweite

- **WHEN** drei Tasten mit Startwert 10 und Schrittweite 5 zugewiesen werden
- **THEN** erhalten sie die Executor-Nummern 10, 15 und 20

#### Scenario: Aktion ohne Nummer

- **WHEN** mehrere Tasten dieselbe Command-Aktion erhalten
- **THEN** wird der unveränderte Befehl für alle ausgewählten Tasten gespeichert

#### Scenario: Fehler verhindert Teilzuweisung

- **WHEN** eine der verteilten Zuweisungen ungültig ist
- **THEN** wird keine der Zuweisungen gespeichert

### Requirement: Bankauswahl im Editor

Die Gerätefläche SHALL die vom Gerät unterstützten Bänke anzeigen und eine Bank
zum Bearbeiten auswählen lassen. Die Auswahl MUST reiner Editorzustand sein und
weder das Gerät noch die MA-Page schalten. Die Oberfläche MUST keine „aktive“
oder „zuletzt erkannte“ Bank anzeigen, da das Gerät sie nicht meldet.

#### Scenario: Bank 3 bearbeiten

- **WHEN** im Editor Bank 3 gewählt wird
- **THEN** zeigt die Fläche die Belegungen der Bank 3 und speichert Änderungen in deren Ebene

#### Scenario: Keine Hardwarewirkung

- **WHEN** im Editor die Bank gewechselt wird
- **THEN** werden weder MIDI-Daten an das Gerät noch ein Page-Befehl an die MA gesendet

### Requirement: Learn-Modus für die Control-Belegung

Die Gerätefläche SHALL einen Learn-Modus für die gewählte Bank starten können,
der die ungebundenen Controls in Layout-Reihenfolge durchläuft. Das aktive
Control MUST hervorgehoben, der Fortschritt angezeigt und Überspringen,
Abbrechen und Speichern angeboten werden. Die gewählte Bank und ihr erwarteter
MIDI-Kanal MUST während der Sitzung sichtbar sein; die Bank darf nicht
automatisch wechseln.

#### Scenario: Geführtes Anlernen

- **WHEN** der Learn-Modus für Bank 2 gestartet und die erste physische Taste gedrückt wird
- **THEN** wird die Taste in Bank 2 gebunden, das nächste Control hervorgehoben und der Fortschritt aktualisiert

#### Scenario: Abbrechen ohne Speichern

- **WHEN** der Benutzer den Learn-Modus abbricht
- **THEN** bleiben die gespeicherten Belegungen unverändert

### Requirement: Bank-Einstellungen im Editor

Der Editor SHALL je Gerät die Bankgröße und je Bank den MIDI-Kanal sowie
optional eine MA-Page bearbeiten lassen. Die Bankgröße MUST mit einem Default
vorbelegt sein und vor dem Speichern auf einen Wert größer oder gleich eins
geprüft werden. Änderungen MUST über den bestehenden Konfigurationspfad
gespeichert werden.

#### Scenario: Bankgröße ändern

- **WHEN** die Bankgröße eines Geräts auf 10 gesetzt und gespeichert wird
- **THEN** verschiebt der Bank-Offset die Executor-Ziele der Bänke entsprechend

#### Scenario: Ungültige Bankgröße im Editor

- **WHEN** die Bankgröße auf 0 gesetzt werden soll
- **THEN** zeigt der Editor einen Feldfehler und speichert nicht

### Requirement: Beschleunigung in der Geräteansicht

Die Gerätefläche SHALL für ein Control, das im Profil `kind = "encoder"` hat und
ein Fader-Ziel erhält, im Zuweisungsdialog einen Schalter „Beschleunigt“
anbieten. Der Schalter MUST denselben Wert `accelerated` des effektiven
Playback-Ziels lesen und schreiben, den auch der Mapping-Editor verwendet; eine
eigene Geräte- oder Bank-Einstellung MUST NOT entstehen. Ohne gespeicherten Wert
MUST der Schalter ausgeschaltet sein.

#### Scenario: Absoluter Encoder mit Fader-Ziel

- **WHEN** ein Control im Profil als Encoder geführt wird und ein Fader-Ziel hat
- **THEN** zeigt der Zuweisungsdialog den Schalter „Beschleunigt“ und spiegelt den gespeicherten Wert wider

#### Scenario: Physischer Fader oder Button-Ziel

- **WHEN** das Control als Fader geführt wird oder das Ziel ein Button ist
- **THEN** wird kein Beschleunigungs-Schalter angeboten

#### Scenario: Schalter in einer Bank

- **WHEN** bei gewählter Bank 2 der Schalter gesetzt wird und dort noch kein Eintrag existiert
- **THEN** legt der Editor einen Eintrag der Bank-Ebene mit dem effektiven Ziel und `accelerated = true` an, ohne den globalen Eintrag zu verändern

#### Scenario: Schalter bei Mehrfachzuweisung

- **WHEN** mehrere absolute Encoder gleichzeitig ein Fader-Ziel mit aktivem Schalter erhalten
- **THEN** tragen alle erzeugten Ziele `accelerated = true`

#### Scenario: Abgelehnte Kombination

- **WHEN** das Backend den Schalter für ein Control ablehnt, das nicht als absoluter Encoder geführt wird
- **THEN** zeigt der Editor die Fehlermeldung am Control und behält die bisherige Konfiguration

## MODIFIED Requirements

### Requirement: Absolute Controls in der Geräteübersicht

Die Geräteübersicht SHALL die absoluten Controls eines MIDI-Geräts mit Note
und Art (`fader` oder `encoder`) anzeigen, sobald das Gerät erkannt wurde. Für
nicht angeschlossene Geräte MUST die Geräteübersicht keinen Eintrag anbieten.

#### Scenario: MIDICRAFT ENC wird angezeigt

- **WHEN** das Gerät `midicraft` mit seinem Profil konfiguriert und
  angeschlossen ist
- **THEN** listet die Geräteübersicht fünf Fader und fünf absolute Encoder mit
  ihren Notes und logischen Namen

#### Scenario: Gerät ist nicht angeschlossen

- **WHEN** das konfigurierte MIDICRAFT ENC nicht erkannt wird
- **THEN** erscheint es nicht in der Geräteübersicht
