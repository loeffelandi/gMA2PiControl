# config-ui Specification

## Purpose
Stellt eine im LAN erreichbare Weboberfläche und JSON-API bereit, über die
MA2-Zugangsdaten, Geräte und Mapping ohne SSH bearbeitet, gelernt, getestet und
gesichert werden können – ohne externe Assets oder Cloud-Abhängigkeiten.

## Requirements


### Requirement: Eingebettete Web-Oberfläche

Der Daemon SHALL die statische Svelte-Oberfläche und die JSON-API im selben
Prozess ausliefern. Bind-Adresse und Port MUST konfigurierbar sein; die
Oberfläche MUST ohne Internetverbindung und ohne externe CDN-Ressourcen laden.
Änderungen an Bind-Adresse oder Port werden erst nach einem Dienstneustart
wirksam.

#### Scenario: Oberfläche lädt ohne Internet

- **WHEN** der Browser nur den Pi im LAN erreicht, aber keinen Internetzugang hat
- **THEN** laden HTML, JavaScript, Styles und Schriften vollständig aus lokalen Assets und die Oberfläche ist bedienbar

#### Scenario: Zugriff aus dem LAN

- **WHEN** ein Browser im selben LAN die konfigurierte Adresse und den Port aufruft
- **THEN** wird die Oberfläche ausgeliefert und die API antwortet

#### Scenario: Bind-Adresse geändert

- **WHEN** die Bind-Adresse in der Konfiguration geändert und angewendet wird
- **THEN** bleibt der laufende Listener unverändert; die Änderung wird erst nach einem Dienstneustart wirksam und ist in der README dokumentiert

### Requirement: MA2-Zugangsdaten verwalten

Die API SHALL Host, Port, Pfad und Benutzername lesbar und das Passwort
ausschließlich schreibbar bereitstellen. Das Passwort MUST NOT in einer
Antwort, einem Log oder einer Fehlermeldung erscheinen. Der Verbindungstest MUST
die laufende Session nicht unterbrechen.

#### Scenario: Passwort wird nie zurückgegeben

- **WHEN** die Konfiguration über die API gelesen wird
- **THEN** enthält die Antwort weder das Passwort noch dessen Hash, sondern nur die übrigen MA2-Felder

#### Scenario: Verbindungstest erfolgreich

- **WHEN** im UI gültige Zugangsdaten eingegeben und „Testen“ gewählt wird
- **THEN** meldet die API innerhalb des Timeouts Erfolg und zeigt Benutzer sowie Session-Ziel an

#### Scenario: Verbindungstest fehlgeschlagen

- **WHEN** der Test mit falschem Passwort oder unerreichbarem Host läuft
- **THEN** meldet die API einen verständlichen Fehler, ohne das Passwort oder den Hash auszugeben

#### Scenario: Laufende Session bleibt bestehen

- **WHEN** ein Verbindungstest läuft, während der Daemon bereits mit derselben onPC verbunden ist
- **THEN** bleibt die bestehende Session bestehen und der Test verwendet keine zweite dauerhafte Session

### Requirement: Geräte- und Mapping-Editor

Die Oberfläche SHALL erkannte Geräte und deren logische Controls anzeigen und
das Bearbeiten von Tasten-, Modifier- und Encoder-Mappings ermöglichen. Pro
physischem Encoder MUST zusätzlich das Attribut-Ziel und der Screen-Encoder
als Nummer (5–10 oder „keiner“) wählbar sein. Vor dem Speichern MUST die
Konfiguration mit denselben Regeln wie der Daemon validiert werden; ungültige
Ziele werden mit Feldbezug abgelehnt.

#### Scenario: Erkannte Geräte werden angezeigt

- **WHEN** die Mapping-Seite geöffnet wird
- **THEN** erscheinen beide konfigurierten Geräte mit Name, Vendor-/Product-ID und ihren verfügbaren Controls

#### Scenario: Taste einer Aktion zuweisen

- **WHEN** eine Taste im Learn-Modus erfasst und einer Hardkey- oder CMD-Aktion zugewiesen wird
- **THEN** erscheint die Zuordnung in der Tabelle und die Validierung meldet keinen Fehler

#### Scenario: Ungültiges Encoder-Ziel

- **WHEN** ein Encoder auf Wheel 11 oder auf ein unbekanntes Attribut gesetzt wird
- **THEN** lehnt die API das Speichern mit einer Feldmeldung ab und die aktive Konfiguration bleibt unverändert

#### Scenario: Screen-Encoder-Namen bearbeiten

- **WHEN** im Mapping-Editor pro physischem Encoder ein Screen-Encoder (Nummer 5–10) ausgewählt und gespeichert wird
- **THEN** enthält `mapping.screen_encoders` für den zugeordneten Slot genau diese Nummer und der Screen-Modus adressiert den entsprechenden Hardware-Encoder

#### Scenario: Screen-Encoder-Slot leeren

- **WHEN** für einen physischen Encoder `— keiner —` gewählt und gespeichert wird
- **THEN** fehlt der zugeordnete Slot in `mapping.screen_encoders` und im Screen-Modus sendet dieser Slot keine Frames

### Requirement: Learn-Modus

Der Learn-Modus SHALL das nächste passende Eingabeereignis erfassen und im UI
anzeigen, ohne es an die onPC zu senden. Es MUST höchstens eine Learn-Sitzung
gleichzeitig geben; ein Timeout oder Abbruch MUST den normalen Betrieb ohne
Zustandsänderung wiederherstellen.

#### Scenario: Taste lernen

- **WHEN** der Learn-Modus für Tasten aktiv ist und eine Taste gedrückt wird
- **THEN** zeigt das UI den logischen Control-Namen und den Rohcode an und es wird kein MA2-Frame gesendet

#### Scenario: Encoder lernen

- **WHEN** der Learn-Modus für einen Encoder aktiv ist und der Encoder gedreht wird
- **THEN** zeigt das UI Achse, Richtung und die erkannten Detents an

#### Scenario: Timeout ohne Eingabe

- **WHEN** im Learn-Modus innerhalb der Frist keine passende Eingabe erfolgt
- **THEN** endet der Modus, das UI zeigt eine Meldung und der normale Betrieb läuft unverändert weiter

#### Scenario: Abbruch durch den Benutzer

- **WHEN** der Benutzer den Learn-Modus abbricht
- **THEN** wird kein Event übernommen und die vorherige Konfiguration bleibt aktiv

### Requirement: Live-Status

Die Oberfläche SHALL den aktuellen Zustand über eine dauerhafte
WebSocket-Verbindung anzeigen: Verbindung zur onPC, Session, erkannte Geräte,
Rate-Limiter, die letzten Frame-Typen und den aktiven Encoder-Modus
(Attribut oder Screen). Aus dem Encoder-Modus MUST sich ein LED-Zustand
ableiten lassen: grün im Screen-Modus, rot im Attribut-Modus. Zugangsdaten und
Passwort-Hashes MUST NOT Teil der Statusdaten sein. Die UI-Verbindung MUST sich
nach einer Unterbrechung selbstständig wieder aufbauen.

#### Scenario: Verbindungszustand ändert sich

- **WHEN** die onPC neu startet und der Daemon reconnectet
- **THEN** wechselt die Anzeige ohne manuelles Neuladen von „getrennt“ über „verbinde“ zu „verbunden“

#### Scenario: Frame-Aktivität

- **WHEN** Tasten gedrückt oder Encoder gedreht werden
- **THEN** aktualisieren sich Frame-Zähler und die Liste der letzten Frame-Typen in Echtzeit

#### Scenario: Encoder-Modus sichtbar

- **WHEN** die Screen-Modus-Taste am Gerät gedrückt wird
- **THEN** meldet der Status innerhalb einer Sekunde den neuen Modus und die Oberfläche zeigt den passenden LED-Zustand

#### Scenario: UI-Verbindung bricht ab

- **WHEN** die WebSocket-Verbindung des Browsers zum Daemon unterbrochen wird
- **THEN** baut die Oberfläche die Verbindung automatisch wieder auf und zeigt den aktuellen Zustand

### Requirement: Konfigurations-Backups

Die Oberfläche SHALL Konfigurations-Backups anlegen, auflisten und
wiederherstellen können. Eine Wiederherstellung MUST validiert und als
Bestätigungsschritt ausgeführt werden; bei ungültigem Backup bleibt die aktive
Konfiguration unverändert.

#### Scenario: Backup anlegen und wiederherstellen

- **WHEN** ein Backup erstellt, die Konfiguration geändert und anschließend das Backup wiederhergestellt wird
- **THEN** ist die ursprüngliche Konfiguration aktiv und die Änderung wurde rückgängig gemacht

#### Scenario: Ungültiges Backup

- **WHEN** ein beschädigtes oder schemawidriges Backup wiederhergestellt werden soll
- **THEN** lehnt die API den Vorgang ab und die aktive Konfiguration bleibt unverändert

### Requirement: PIN-Sperre der Oberfläche

Die Oberfläche SHALL im LAN erreichbar sein. Eine einfache PIN-Sperre MUST
optional konfigurierbar sein und ohne explizite Aktivierung aus bleiben. Ist
keine PIN gesetzt, MUST die Oberfläche sichtbar warnen. Ist eine PIN aktiv,
MUST die Oberfläche eine Sperrseite zeigen und die API außer den öffentlichen
Auth-Endpunkten authentifizieren.

#### Scenario: Zugriff ohne PIN

- **WHEN** keine PIN aktiviert ist
- **THEN** ist die API offen und die Oberfläche zeigt oben einen Warnbanner

#### Scenario: Zugriff mit PIN

- **WHEN** ein Client im LAN die Oberfläche oder eine geschützte API aufruft
- **THEN** wird ohne gültige PIN-Session die Sperrseite beziehungsweise `401 pin_required` geliefert

#### Scenario: PIN-Anmeldung

- **WHEN** der Benutzer die korrekte PIN eingibt
- **THEN** wird eine Session gesetzt und die Oberfläche lädt die Live-Daten

#### Scenario: Falsche PIN

- **WHEN** eine falsche PIN eingegeben wird
- **THEN** bleibt der Zugriff gesperrt und die Antwort enthält die PIN nicht

#### Scenario: PIN-Sperre deaktiviert

- **WHEN** `web.pin_enabled` auf `false` gesetzt ist
- **THEN** verhält sich die Oberfläche wie im offenen LAN-Modus, zeigt keinen Login-Schritt und warnt oben, dass keine PIN gesetzt ist

### Requirement: Schreibzugriffe und Geheimnisse

Schreibende API-Aufrufe MUST als JSON mit einem eigenen Anfrage-Header
erfolgen. Antworten und Logs MUST NOT das MA2-Passwort, dessen Hash oder die
PIN enthalten.

#### Scenario: Einfacher Formular-POST wird abgelehnt

- **WHEN** ein schreibender Aufruf ohne JSON-Inhalt oder ohne den erwarteten Header eintrifft
- **THEN** wird er mit einem Client-Fehler abgelehnt und die Konfiguration bleibt unverändert

### Requirement: Playback-Ziele im Mapping-Editor

Der Mapping-Editor SHALL logische Controls, die als absoluter Wert konfiguriert
sind, gemeinsam mit Tasten und Encodern anzeigen und je Control ein
Playback-Ziel mit Page, Executor, Art (`button` oder `fader`) und optionaler
Button-Nummer (`1..3`) bearbeiten lassen. Als Page MUST eine Zahl ab 1 oder
`current` akzeptiert werden. Vor dem Speichern MUST die Oberfläche die
Wertebereichsprüfung durchführen und Fehler am betroffenen Feld anzeigen.

#### Scenario: Control einem Executor zuweisen

- **WHEN** der Benutzer für einen Fader das Ziel `page = 1`, `executor = 5`,
  `kind = "fader"` einträgt und speichert
- **THEN** wird die Konfiguration über den bestehenden Schreibendpunkt
  übernommen und das Ziel erscheint anschließend in der Mapping-Ansicht

#### Scenario: Aktuelle Master-Page wählen

- **WHEN** der Benutzer als Page `current` einträgt
- **THEN** speichert die Oberfläche `page = "current"` und das Ziel folgt der
  aktiven Master-Page

#### Scenario: Ungültiger Executor

- **WHEN** der Benutzer `executor = 0` oder eine Page eingibt, die weder eine
  Zahl ab 1 noch `current` ist
- **THEN** zeigt die Oberfläche den Fehler am Feld an und sendet keine
  Konfigurationsänderung

#### Scenario: Button-Nummer bei Fader-Ziel

- **WHEN** der Benutzer für `kind = "fader"` eine Button-Nummer einträgt
- **THEN** weist die Oberfläche auf den ungültigen Wert hin und verhindert das
  Speichern

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

### Requirement: Checkbox je absolutem Encoder

Der Mapping-Editor SHALL für jedes Playback-Ziel mit `kind = "fader"`, dessen
Control im Profil als absoluter Encoder geführt wird, eine Checkbox
„Beschleunigt“ anzeigen. Die Checkbox MUST den gespeicherten Wert
`accelerated` widerspiegeln; ohne gespeicherten Wert MUST sie ausgeschaltet
sein. Für Button-Ziele und für Controls, die im Profil als Fader geführt
werden, MUST keine Checkbox erscheinen.

#### Scenario: Encoder mit Fader-Ziel

- **WHEN** ein absoluter Encoder ein Fader-Ziel auf Executor 3 hat und
  `accelerated = true` gespeichert ist
- **THEN** zeigt die Zeile die Checkbox aktiviert an

#### Scenario: Physischer Fader

- **WHEN** ein Control im Profil als Fader geführt wird
- **THEN** zeigt seine Playback-Zeile keine Beschleunigungs-Checkbox

#### Scenario: Button-Ziel

- **WHEN** ein Playback-Ziel `kind = "button"` hat
- **THEN** zeigt die Zeile keine Beschleunigungs-Checkbox

### Requirement: Speichern der Checkbox

Beim Speichern MUST ein eingeschalteter Wert als `accelerated = true` und ein
ausgeschalteter Wert als `accelerated = false` oder ohne Feld geschrieben
werden. Lehnt das Backend die Kombination ab, MUST der Editor die Fehlermeldung
an der betroffenen Zeile anzeigen und die bisherige Konfiguration behalten.

#### Scenario: Beschleunigung einschalten

- **WHEN** der Benutzer die Checkbox für einen Encoder aktiviert und speichert
- **THEN** enthält das gespeicherte Playback-Ziel `accelerated = true`

#### Scenario: Beschleunigung ausschalten

- **WHEN** der Benutzer die Checkbox für einen Encoder deaktiviert und speichert
- **THEN** enthält das gespeicherte Playback-Ziel kein aktives `accelerated`
  mehr und das Control wird wieder 1:1 übertragen

#### Scenario: Ungültige Kombination

- **WHEN** die Konfiguration die Checkbox für ein Control speichert, das nicht
  als absoluter Encoder geführt wird
- **THEN** zeigt der Editor die Fehlermeldung des Backends an der Zeile an und
  behält die bisherige Konfiguration bei

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
