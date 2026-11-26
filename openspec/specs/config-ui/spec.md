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

Der Learn-Modus SHALL das nächste passende Ereignis samt Rohcode oder Bank-Note
erfassen, beim Encoder-Lernen das erste Control fixieren und ein ausbleibendes
Key-Up nach höchstens zwei Sekunden freigeben. Die Oberfläche MUST einen
Abbrechen-Knopf bieten, bei Timeout oder Abbruch alle Schaltflächen freigeben
und beim Verlassen des Tabs laufende Sitzungen abbrechen.

#### Scenario: Taste lernen

- **WHEN** der Learn-Modus für Tasten aktiv ist und eine Taste (auch auf einem
  gebankten MIDI-Gerät) gedrückt wird
- **THEN** zeigt das UI den logischen Control-Namen und den Rohcode oder die
  Note an und sendet keinen MA2-Frame

#### Scenario: Encoder lernen

- **WHEN** der Learn-Modus für einen Encoder aktiv ist und der Encoder gedreht wird
- **THEN** bleibt das zuerst bewegte Control fixiert und das UI zeigt Achse,
  Richtung und Detents an

#### Scenario: Timeout ohne Eingabe

- **WHEN** im Learn-Modus innerhalb der Frist keine passende Eingabe erfolgt
- **THEN** endet der Modus, alle „Lernen“-Schaltflächen sind wieder aktiv und
  der normale Betrieb läuft weiter

#### Scenario: Abbruch durch den Benutzer

- **WHEN** der Benutzer abbricht oder den Tab verlässt
- **THEN** wird die Sitzung abgebrochen und die bisherige Konfiguration bleibt
  aktiv

#### Scenario: Fehlendes Key-Up blockiert den Betrieb nicht

- **WHEN** eine gelernte Taste kein Key-Up liefert
- **THEN** endet die Nachlaufsperre spätestens nach zwei Sekunden

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

Die Oberfläche SHALL im LAN erreichbar sein; die optionale PIN-Sperre MUST ohne
Aktivierung aus bleiben und bei fehlender PIN sichtbar warnen. Eine PIN-Session
MUST serverseitig nach höchstens zwölf Stunden ablaufen. Die PIN-Prüfung MUST
serialisiert und längenunabhängig erfolgen, nach fünf Fehlversuchen wachsend
sperren (15 s, verdoppelt bis 300 s, `429 pin_locked` mit `Retry-After`, ohne
während aktiver Sperre weiterzuzählen) und bei PIN-änderndem Backup-Restore
bestehende Sessions widerrufen.

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

#### Scenario: Session läuft ab

- **WHEN** eine PIN-Session älter als zwölf Stunden ist
- **THEN** antwortet die API mit `401 pin_required`, auch wenn der Browser das
  Cookie noch sendet

#### Scenario: Sperre nach Fehlversuchen

- **WHEN** fünfmal hintereinander (auch parallel) eine falsche PIN eingegeben
  wird
- **THEN** antwortet `/api/auth/login` mit `429 pin_locked` und `Retry-After`,
  auch für eine richtige PIN, bis die Sperre abgelaufen ist, ohne den Zähler
  während der Sperre weiter zu erhöhen

#### Scenario: Sperre endet

- **WHEN** die Sperrzeit abgelaufen ist und die richtige PIN eingegeben wird
- **THEN** wird eine Session gesetzt und der Fehlversuchszähler beginnt bei null

#### Scenario: Weitere Fehlversuche verlängern die Sperre

- **WHEN** nach Ende einer Sperre erneut eine falsche PIN eingegeben wird
- **THEN** ist die nächste Sperre doppelt so lang wie die vorherige, höchstens
  300 Sekunden

#### Scenario: Backup-Restore mit geänderter PIN

- **WHEN** ein Backup mit anderer PIN wiederhergestellt wird
- **THEN** werden bisherige Sessions widerrufen

### Requirement: Schreibzugriffe und Geheimnisse

Schreibende API-Aufrufe MUST als JSON mit eigenem Anfrage-Header erfolgen; ein
Körper, der kein JSON-Objekt ist, MUST mit `400 invalid_json` abgelehnt werden.
Antworten und Logs — inklusive Python-Dicts, JSON und Exception-Tracebacks —
MUST NOT das MA2-Passwort, dessen Hash, Tokens, PSKs oder die PIN enthalten.

#### Scenario: Einfacher Formular-POST wird abgelehnt

- **WHEN** ein schreibender Aufruf ohne JSON-Inhalt oder ohne den erwarteten Header eintrifft
- **THEN** wird er mit einem Client-Fehler abgelehnt und die Konfiguration bleibt unverändert

#### Scenario: Körper ist kein Objekt

- **WHEN** `POST /api/learn/start` einen JSON-Array- oder Zeichenketten-Körper
  erhält
- **THEN** antwortet die API mit `400 invalid_json` und startet keine Sitzung

#### Scenario: Geheimnis in Dict oder Traceback wird im Log geschwärzt

- **WHEN** eine Log-Meldung oder ein Traceback `{"password": "geheim"}` oder
  `'pin': '1234'` enthält
- **THEN** erscheint im Log anstelle des Klartexts `***`

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

### Requirement: Gerätezeilen auf der Statusseite

Die Statusseite SHALL jedes konfigurierte Gerät als Zeile mit Kennung,
Transport, VID:PID, Profil und Zustand darstellen. Die Darstellung MUST ohne
horizontales Scrollen umbrechen.

#### Scenario: Gerät mit allen Angaben

- **WHEN** ein Gerät konfiguriert und erkannt ist
- **THEN** zeigt die Zeile Kennung, Transport, VID:PID, Profil und „erkannt“

### Requirement: RX- und TX-Anzeigen

Jede Gerätezeile MUST zwei Aktivitätsanzeigen besitzen: RX für Daten vom Gerät
und TX für Daten zum Gerät. Die Anzeigen MUST auf einen Anstieg des jeweiligen
Zählers sichtbar reagieren und ohne Aktivität gedimmt bleiben. Die Bedeutung von
RX und TX MUST zusätzlich zur Farbe über eine Legende oder Beschriftung
erkennbar sein. Bei `prefers-reduced-motion: reduce` MUST die Reaktion ohne
Animation erfolgen.

#### Scenario: Eingabe lässt RX blinken

- **WHEN** ein Gerät ein Ereignis liefert
- **THEN** pulsiert die RX-Anzeige dieser Zeile kurz und die TX-Anzeige bleibt unverändert

#### Scenario: Ausgabe lässt TX blinken

- **WHEN** ein Wert erfolgreich an ein Gerät geschrieben wird
- **THEN** pulsiert die TX-Anzeige dieser Zeile kurz

#### Scenario: Keine Aktivität

- **WHEN** ein Gerät längere Zeit nichts sendet oder empfängt
- **THEN** bleiben beide Anzeigen gedimmt und es entsteht kein Dauerlicht

#### Scenario: TX ohne Ausgabepfad

- **WHEN** ein Gerät nie beschrieben wird
- **THEN** bleibt seine TX-Anzeige gedimmt, ohne als Fehler markiert zu werden

### Requirement: Terminal-Log auf der Statusseite

Die Statusseite SHALL unter den Geräten ein Terminal-Log der letzten
Aktivitätsereignisse anzeigen. Jede Zeile MUST Zeitstempel mit Millisekunden,
Richtungs-Badge, Gerätekennung und Kurztext enthalten. Das Log MUST die neuesten
Einträge unten anzeigen und bei neuen Einträgen ans Ende scrollen. Es MUST auf
100 Einträge begrenzt sein und bei leerem Zustand einen Hinweis anzeigen.
Einträge MUST über ihre Sequenznummer dedupliziert werden, damit Status-Resync
und Delta-Events sich nicht doppeln.

#### Scenario: Neues Ereignis erscheint im Log

- **WHEN** ein `activity`-Event neue Einträge liefert
- **THEN** erscheinen sie in chronologischer Reihenfolge am Ende des Logs

#### Scenario: Resync ersetzt den Log-Stand

- **WHEN** ein Status-Snapshot mit Log-Ring empfangen wird
- **THEN** entspricht der angezeigte Log-Stand diesem Ring ohne doppelte Sequenznummern

#### Scenario: Leeres Log

- **WHEN** seit dem Start keine Aktivität aufgetreten ist
- **THEN** zeigt das Terminal einen Hinweis statt einer leeren Fläche

### Requirement: Kanonische TOML-Form in der Konfigurations-API

`GET /api/config` SHALL die aktive Konfiguration in derselben Tabellen- und
Schlüsselstruktur ausgeben, die `PUT /api/config` akzeptiert, abzüglich
redaktierter Geheimnisse (`ma2.password_set`, `web.pin_set`). Inaktive
Variantenfelder (`None`) MUST entfallen, und Bank-Ebenen MUST direkt unter
`mapping.device_banks.<gerät>.<bank>` mit `encoders` als Liste liegen. Vom
Client gesendete Felder `ma2.password_file` und `ma2.password_env` MUST
verworfen werden.

#### Scenario: Zweiten Encoder speichern ohne 422

- **WHEN** `GET /api/config` geladen und einer von mehreren Encodern über
  `PUT /api/config` geändert wird
- **THEN** enthalten unveränderte Encoder kein `attribute: null` oder
  `slot: null` und das Speichern gelingt ohne Fehler

#### Scenario: Bank-Ebene und MA-Page überleben Reload und Speichern

- **WHEN** für Bank 2 `ma_page` und zwei Encoder-Overrides gespeichert und die
  Konfiguration neu geladen wird
- **THEN** bleiben beide Overrides und `ma_page` sichtbar und bei weiteren
  Speichervorgängen erhalten

#### Scenario: Kein Einschleusen von `password_file`

- **WHEN** ein Client `PUT /api/config` ohne `password`, aber mit
  `ma2.password_file = "/var/lib/ma2pi/recovery.json"` sendet
- **THEN** liest der Daemon die angegebene Datei nicht und gibt keinen
  Dateifehler preis

### Requirement: Schutz vor DNS-Rebinding und fremden WebSocket-Ursprüngen

Der Webserver SHALL den `Host`-Header gegen IP-Literale, `localhost`, `.local`
und den lokalen Hostnamen prüfen und fremde Domains mit `403` oder `421`
abweisen. Ist bei Schreibanfragen oder auf `/api/events` ein `Origin`-Header
vorhanden, MUST er zum validierten `Host` passen.

#### Scenario: Zugriff über Pi-IP im Show-LAN

- **WHEN** ein Browser `http://192.168.178.21:8080/` oder `http://ma2pi.local:8080/`
  nutzt
- **THEN** werden Lesen, Schreiben und `/api/events` zugelassen

#### Scenario: DNS-Rebinding über fremde Domain

- **WHEN** eine Anfrage mit `Host: attacker.example:8080` eintrifft
- **THEN** lehnt der Server sie vor der Ausführung ab

#### Scenario: Fremder Origin auf `/api/events`

- **WHEN** eine Anfrage mit `Origin: http://example.com` `/api/events` öffnet
- **THEN** lehnt der Server das WebSocket-Upgrade ab

### Requirement: Event-Stream schließt langsame und abgemeldete Clients

Der Event-Stream SHALL je Client eine begrenzte Warteschlange nutzen. Läuft sie
über oder endet eine PIN-Session durch Abmeldung, PIN-Wechsel oder Backup-Restore,
MUST der Server betroffene `/api/events`-WebSockets aktiv schließen und keine
weiteren Events für sie einreihen; andere Clients MUST unbeeinträchtigt bleiben.

#### Scenario: Client liest zu langsam

- **WHEN** die Warteschlange eines Clients voll ist und ein weiteres Event
  veröffentlicht wird
- **THEN** wird dessen WebSocket geschlossen und der Daemon blockiert nicht

#### Scenario: Andere Clients bleiben verbunden

- **WHEN** ein Client wegen Überlaufs getrennt wird
- **THEN** erhalten alle übrigen Clients weiter jedes Event

#### Scenario: Wiederverbinden

- **WHEN** ein getrennter Client erneut `/api/events` öffnet
- **THEN** erhält er zuerst den aktuellen Status und danach neue Events

#### Scenario: WebSocket endet bei PIN-Wechsel oder Abmeldung

- **WHEN** sich der Benutzer abmeldet oder sich die PIN ändert
- **THEN** werden bestehende `/api/events`-WebSockets geschlossen

### Requirement: Vollständige Merge-Patches und Inventar im Mapping-Editor

Die Oberfläche SHALL beim Ändern einer Zuweisung abgelöste Variantenfelder mit
`null` löschen, nach erfolgreichem Speichern ihre Ausgangsmengen aktualisieren
und im Mapping-Editor auch Controls aus `controls.inventory` und `controls.banks`
einschließlich der `accelerated`-Option anbieten.

#### Scenario: Aktionsart im Mapping-Tab wechseln

- **WHEN** eine bestehende Taste von `hardkey` auf `command` oder ein Playback
  von `button` auf `fader` umgestellt wird
- **THEN** setzt der Patch abgelöste Felder auf `null` und speichert ohne `422`

#### Scenario: MIDICRAFT-Encoder im Mapping-Tab beschleunigen

- **WHEN** ein gebanktes Gerät wie `midicraft-enc` angeschlossen ist
- **THEN** zeigt der Mapping-Tab die `accelerated`-Checkbox für dessen
  Inventar-Encoder und speichert Änderungen korrekt

### Requirement: Konsistente Dialoge, Kontrast und Auth-Synchronisation

Im Zuweisungsdialog SHALL „Kein Screen-Encoder“ speicherbar sein, ein entfernter
Screen-Encoder gelöscht werden (`Slot 1..4`), ein geerbter Bank-Offset nicht
unbeabsichtigt eingefroren werden und das Entfernen einer Zuweisung möglich sein.
Dialoge MUST per `Escape` schließbar sein, dunkle Zellen (`black`) MUST Kontrast
`>= 4,5:1` einhalten, Rettungs-WLAN-Fehler MUST `role="alert"` tragen und
PIN-Änderungen oder `401` MUST den Auth-Status der App aktualisieren.

#### Scenario: Attribut-Encoder ohne Screen-Encoder speichern

- **WHEN** im Zuweisungsdialog ein Encoder auf Slot 1 ohne Screen-Encoder
  gespeichert wird
- **THEN** gelingt das Speichern und ein alter Screen-Encoder für Slot 1 wird
  entfernt

#### Scenario: Fehler beim Rettungs-WLAN und Kontrast auf schwarzen Tasten

- **WHEN** `PUT /api/recovery` fehlschlägt oder eine Zelle die Farbe `black` hat
- **THEN** erscheint der Fehler als `role="alert"` im Fehlerstil und der
  Zellentext ist mit mindestens `4,5:1` lesbar

### Requirement: Gezielter PIN-Session-Widerruf bei Konfigurationsänderungen

`PUT /api/config` SHALL bestehende PIN-Sessions und `/api/events`-WebSockets nur
dann trennen, wenn sich `web.pin_enabled` oder `web.pin` tatsächlich gegenüber
der vorherigen Konfiguration geändert hat. Ein vorübergehender Auth-Fehler in
der App-Hülle MUST nach erfolgreicher Erholung wieder ausgeblendet werden.

#### Scenario: Ändern des Log-Levels trennt andere PIN-Sessions nicht

- **WHEN** auf `AdvancedPage` nur `logging.level` oder `rate` gespeichert wird,
  während die PIN unverändert aktiv bleibt
- **THEN** bleiben bestehende PIN-Sessions und WebSockets anderer Clients
  verbunden

### Requirement: Dedupliziertes Lernen und vollständige Validierung im Mapping-Tab

Der Mapping-Tab SHALL `learnStore`-Zustände deduplizieren, damit ein früheres
Lernergebnis keine neu gestartete Sitzung beendet, leere `hardkey`-Modifier vor
dem Speichern mit Fehlermeldung abweisen, frei benannte `relative-encoder` über
`encoder_id` auflösen und unbelegte Bank-Controls nicht als Note `0` anzeigen.

#### Scenario: Zweites Lernen wird nicht durch alten Status beendet

- **WHEN** nach einer beendeten Learn-Sitzung eine zweite Learn-Sitzung im
  Mapping-Tab gestartet wird und reguläre Status-Events eintreffen
- **THEN** bleibt die neue Learn-Sitzung aktiv, bis eine neue Eingabe, ein
  Timeout oder ein Abbruch eintrifft

### Requirement: Konsistente Dialog-, LearnPanel- und StatusPage-Zustandsführung

Die Oberfläche SHALL `StatusStore` an `DevicesPage` und `LearnPanel` übergeben,
`startedSession` bei beendeter Sitzung zurücksetzen, beim Gerätewechsel offene
Dialoge/Learn-Panels schließen und `ApiError.detail` anzeigen. `AssignDialog`
MUST bei `Attributname`, `Page` und `Schrittweite` gültige Eingaben prüfen,
Screen-Encoder je Slot aktualisieren und Vererbung sowie `[mapping.modifiers]`
korrekt behandeln; `StatusPage` MUST nach `seq` scrollen und Replugs neu laden.

#### Scenario: Leerer Attributname im Zuweisungsdialog wird abgefangen

- **WHEN** im `AssignDialog` der Modus „Attributname“ mit leerem Eingabefeld
  gespeichert werden soll
- **THEN** zeigt der Dialog einen Validierungsfehler und überschreibt weder
  `Slot 1` noch dessen Screen-Encoder
