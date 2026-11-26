# device-activity Specification

## Purpose
TBD - created by archiving change add-device-activity-monitor. Update Purpose after archive.

## Requirements

### Requirement: RX- und TX-Zähler pro Gerät

Der Daemon SHALL für jedes Gerät eingehende und ausgehende Aktivität zählen.
Je Gerät MUST er einen RX-Zähler, einen TX-Zähler sowie die Zeitstempel der
letzten RX- und TX-Aktivität führen. Als RX MUST jedes konsumierte
Eingabeereignis zählen; als TX MUST jeder erfolgreiche Schreibzugriff auf ein
Gerät zählen. Geräte MUST unter ihrem Konfigurationsnamen geführt werden.
Frames an onPC MUST im Ereignis-Log unter `ma2` erscheinen, aber keinen
Gerätezähler anlegen.

#### Scenario: Tastendruck zählt als RX

- **WHEN** ein Gerät ein Eingabeereignis liefert und der Daemon es konsumiert
- **THEN** steigt der RX-Zähler dieses Geräts um eins und `last_rx` trägt den aktuellen Zeitstempel

#### Scenario: LED-Schreibzugriff zählt als TX

- **WHEN** ein Feedback- oder LED-Wert erfolgreich an ein Gerät geschrieben wird
- **THEN** steigt der TX-Zähler dieses Geräts um eins

#### Scenario: onPC-Frame erscheint im Log

- **WHEN** ein Frame an onPC gesendet wird
- **THEN** erscheint er im Ereignis-Log unter `ma2` und es entsteht kein Gerätezähler `ma2`

#### Scenario: Gerät ohne Ausgabepfad

- **WHEN** ein Gerät wie die Cherry-Tastatur nie beschrieben wird
- **THEN** bleibt sein TX-Zähler bei null, ohne als Fehler zu gelten

### Requirement: Erfassung ohne Blockade

Die Zähler und das Ereignis-Log MUST thread-sicher fortgeschrieben werden. Ein
Erfassungsaufruf MUST NOT blockieren, kein I/O auslösen und die
Eingabeverarbeitung nicht verzögern.

#### Scenario: Aufruf aus dem MIDI-Thread

- **WHEN** ein Schreibzugriff aus einem MIDI-Thread erfasst wird
- **THEN** wird der Eintrag ohne Warten auf den Event-Loop übernommen

### Requirement: Begrenztes Ereignis-Log

Der Daemon SHALL ein Ereignis-Log mit fortlaufender Sequenznummer, Zeitstempel,
Richtung (`rx`/`tx`), Gerätekennung, Art und Kurztext führen. Das Log MUST auf
100 Einträge begrenzt sein. Wiederkehrende Polling-Frames (`playbacksRequest`)
MUST NOT protokolliert werden, damit echte Eingaben im Ring bleiben. Kurztexte
MUST keine Kommandotexte, Passwörter oder Zugangsdaten enthalten. Die
Sequenznummer MUST prozessweit monoton steigen.

#### Scenario: Log bleibt begrenzt

- **WHEN** mehr als 100 Ereignisse auflaufen
- **THEN** enthält das Log nur die letzten 100 Einträge und die Sequenznummern bleiben monoton

#### Scenario: Polling bleibt draußen

- **WHEN** onPC einen wiederkehrenden `playbacksRequest`-Frame beantwortet
- **THEN** entsteht dafür kein Eintrag im Ereignis-Log

#### Scenario: Keine Geheimnisse im Log

- **WHEN** ein Eingabeereignis oder ein Frame protokolliert wird
- **THEN** enthält der Kurztext nur Art, Note/Wert, Bank, Seite, Executor oder Button, aber keinen Kommandotext und kein Passwort

### Requirement: Aktivität im Status und als Delta-Event

Der Status-Snapshot SHALL die aktuellen Gerätezähler und das vollständige
Ereignis-Log als Resync enthalten. Zusätzlich SHALL der Daemon einen
WebSocket-Event `activity` mit den aktuellen Zählern und den seit dem letzten
Flush neuen Einträgen senden. Der Event MUST höchstens alle 250 ms gesendet
werden und MUST nur entstehen, wenn Abonnenten vorhanden sind und neue Einträge
vorliegen. Ein Puffer für noch nicht gesendete Einträge MUST begrenzt sein.

#### Scenario: Schnelles Blinken ohne Event-Flut

- **WHEN** innerhalb von 250 ms mehrere Eingaben auflaufen
- **THEN** werden sie in einem einzigen `activity`-Event gebündelt

#### Scenario: Keine Aktivität, kein Event

- **WHEN** seit dem letzten Flush keine neuen Einträge auflaufen
- **THEN** wird kein `activity`-Event gesendet

#### Scenario: Resync nach Reconnect

- **WHEN** ein Client neu verbindet
- **THEN** erhält er über den Status-Snapshot die Gerätezähler und die letzten 100 Log-Einträge

### Requirement: Zielangaben ausgehender onPC-Frames im Ereignis-Log

`describe_frame` SHALL für ausgehende Frames an die grandMA2 onPC die tatsächlich
verwendeten Protokollfelder (`pageIndex`, `execIndex`, `buttonId`, `name` sowie
`keyname` bei `hardkeyPress` und `hardkeyRelease`) auswerten und 0-basierte
Indizes für die Anzeige wieder 1-basiert (`current` bei `pageIndex == -1`)
formatieren, ohne Kommandotexte oder Geheimnisse aufzunehmen.

#### Scenario: Playback- und Hardkey-Frames zeigen ihr Ziel im Log

- **WHEN** ein `playbackButton`-Frame für Page `current`, Executor 3, Button 1
  oder ein `hardkeyPress` für `Go+` gesendet wird
- **THEN** enthält der Kurztext im Ereignis-Log `page current · executor 3 · button 1`
  beziehungsweise `Go+` statt nur der bloßen Frame-Art

### Requirement: Lesbare Zusammenfassung zusammengesetzter ASL-LED-Pakete

`describe_midi` SHALL bei zusammengesetzten ASL-LED-Schreibzugriffen
(`9F 7F 7F` gefolgt von Helligkeits- und Farb-Note-On) die angesteuerte
Ziel-Note statt des vorangestellten Freigabe-Frames im Ereignis-Log nennen und
reine Freigabe-/Abschaltsequenzen als solche kennzeichnen.

#### Scenario: ASL-Modus-LED wechselt die Farbe

- **WHEN** `LedOutput` das 9-Byte-Paket für Note 9 sendet
- **THEN** nennt der Kurztext im Ereignis-Log Note 9 statt `note 127 · velocity 127`
