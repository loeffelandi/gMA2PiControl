# ma2-connection Specification

## Purpose

Hält eine authentifizierte WebSocket-Sitzung zur grandMA2 onPC, überlebt
Verbindungsabbrüche und onPC-Neustarts und stellt eine geordnete, global
begrenzte Send-Queue bereit, die die onPC nicht durch Frame-Fluten blockiert.

## Requirements

### Requirement: Verbindungsaufbau und Login

Der Client SHALL `ws://<host>:<port>/?ma=1` verbinden, die Serverbereitschaft
abwarten, eine Session anfordern und den Login mit MD5-Hash des Passworts, der
Server-Session-ID und `maxRequests` senden. `loginResponse` mit `result: true`
MUST als authentifiziert gelten; `result: false` MUST als Login-Fehler mit
eindeutiger Meldung behandelt werden.

#### Scenario: Erfolgreicher Login

- **WHEN** die onPC erreichbar ist und Benutzer sowie Passwort stimmen
- **THEN** durchläuft der Client Server-Status, Session-Anforderung und Login und wechselt in den authentifizierten Zustand

#### Scenario: Falsches Passwort

- **WHEN** die onPC mit `result: false` auf den Login antwortet
- **THEN** wird genau eine eindeutige Fehlermeldung protokolliert und der nächste Versuch erst nach einem Backoff unternommen

#### Scenario: onPC nicht erreichbar

- **WHEN** beim Start keine WebSocket-Verbindung aufgebaut werden kann
- **THEN** bleibt der Daemon aktiv, protokolliert den Fehler und versucht es mit wachsendem Backoff erneut

### Requirement: Keepalive der Session

Während einer authentifizierten Session SHALL der Client mindestens alle zehn
Sekunden ein Keepalive-Frame `{"session": <id>}` senden, auch wenn anderer
Traffic läuft. Das Intervall MUST konfigurierbar und kleiner als zehn Sekunden
sein.

#### Scenario: Leerlaufende Session

- **WHEN** zehn Sekunden lang keine Anwendungs-Frames gesendet wurden
- **THEN** wurde in diesem Zeitraum mindestens ein Keepalive-Frame mit der aktuellen Session-ID gesendet

#### Scenario: Keepalive trotz Traffic

- **WHEN** während einer Stoßphase viele Kommandos gesendet werden
- **THEN** wird das Keepalive-Intervall trotzdem eingehalten und die Session bleibt bestehen

### Requirement: Reconnect und Session-Recovery

Bei Verbindungsverlust SHALL der Client die Session als beendet markieren,
gepufferte Anwendungs-Frames verwerfen und mit exponentiellem Backoff und
Jitter erneut verbinden. Nach erfolgreichem Login MUST der lokale Tastenzustand
geleert werden, ohne veraltete Press-/Release-Frames nachzuspielen.

#### Scenario: onPC wird neu gestartet

- **WHEN** die onPC während einer Session neu startet
- **THEN** verbindet sich der Daemon nach dem Neustart selbstständig neu und meldet sich ohne Eingriff an

#### Scenario: Verbindungsabbruch bei gehaltener Taste

- **WHEN** die Verbindung abbricht, während MA gehalten ist
- **THEN** wird der lokale Zustand geleert, kein veraltetes Release an die neue Session gesendet und der nächste Tastendruck erzeugt wieder ein vollständiges Paar

#### Scenario: Backoff ist begrenzt

- **WHEN** die onPC über längere Zeit nicht erreichbar bleibt
- **THEN** wächst die Wartezeit zwischen Versuchen bis zu einer konfigurierten Obergrenze, ohne den Daemon zu blockieren

### Requirement: Globale Send-Queue und Rate-Limiting

Alle ausgehenden Frames SHALL durch eine einzige Send-Queue mit globalem
Rate-Limiter laufen. Die Rate MUST konfigurierbar sein (Default 25 Nachrichten
pro Sekunde). Koaleszierbare Encoder-Frames dürfen zusammengefasst werden;
Hardkey-Releases und Kommandos MUST NOT verworfen werden.

#### Scenario: Encoder-Stoß wird begrenzt

- **WHEN** innerhalb von 100 ms 200 Encoder-Ticks anfallen
- **THEN** werden höchstens die konfigurierte Anzahl Frames pro Sekunde gesendet und der letzte akkumulierte Delta kommt an

#### Scenario: Queue-Überlauf schützt Releases

- **WHEN** die Queue volle Auslastung erreicht
- **THEN** werden Encoder-Frames zuerst zusammengefasst oder verworfen, während Hardkey-Releases und Kommandos erhalten bleiben

#### Scenario: Konfigurierte Rate wird nie überschritten

- **WHEN** beliebig viele Frames gleichzeitig anstehen
- **THEN** überschreitet die Anzahl gesendeter Frames pro Sekunde den konfigurierten Wert nicht

### Requirement: Dry-Run und Frame-Logging

Im Dry-Run-Modus SHALL der Client keine Netzwerkverbindung öffnen und keine
Frames senden; jeder zu sendende Frame MUST mit Zeitstempel, Richtung und
Frame-Typ protokolliert werden. Der Daemon MUST auch ohne erreichbare onPC
laufen. Zugangsdaten und Passwort-Hashes MUST NOT geloggt werden.

#### Scenario: Dry-Run ohne onPC

- **WHEN** der Daemon mit `--dry-run` gestartet wird und keine onPC erreichbar ist
- **THEN** läuft er fehlerfrei, protokolliert alle Frames und öffnet keine WebSocket-Verbindung

#### Scenario: Login-Geheimnis im Log

- **WHEN** der Login ausgeführt oder im Dry-Run protokolliert wird
- **THEN** enthält keine Logzeile das Passwort oder dessen MD5-Hash

### Requirement: Graceful Shutdown

Bei SIGINT oder SIGTERM SHALL der Daemon die Eingabeverarbeitung stoppen,
gehaltene Tasten best effort freigeben, `closeConnection` senden, WebSocket und
alle evdev-Dateideskriptoren schließen und innerhalb von fünf Sekunden mit
Exit-Code 0 beenden.

#### Scenario: Shutdown bei gehaltener Taste

- **WHEN** der Daemon per SIGTERM beendet wird, während eine Taste gehalten ist
- **THEN** wird zuerst das Release gesendet, danach `closeConnection`, und der Prozess endet mit Code 0

#### Scenario: Shutdown ohne erreichbare onPC

- **WHEN** SIGTERM eintrifft, während die onPC nicht erreichbar ist
- **THEN** werden lokale Ressourcen freigegeben und der Prozess endet innerhalb des Timeouts mit Code 0

### Requirement: Transport-Cleanup, Gesamt-Timeout und Peer-Liveness

Schlägt Login oder Handshake fehl oder bricht eine Session ab, MUST der Client
den geöffneten WebSocket-Transport schließen. Der Handshake MUST insgesamt durch
`ma2.login_timeout` begrenzt sein, `ping_interval` MUST `None` bleiben (weil
grandMA2 onPC keine RFC-6455-PING-Frames beantwortet; TCP-Keepalive auf
Socket-Ebene erkennt tote Gegenstellen) und `close()` MUST ein kurzes Timeout
einhalten.

#### Scenario: Fehlgeschlagener Login hinterlässt keinen offenen Socket

- **WHEN** die onPC den Login ablehnt oder der Handshake abbricht
- **THEN** wird der geöffnete Transport vor dem Backoff geschlossen

#### Scenario: Gezogenes Netzwerkkabel wird zeitnah erkannt

- **WHEN** die Gegenstelle ohne TCP-FIN unerreichbar wird
- **THEN** nutzt der Transport TCP-Keepalive statt WebSocket-Pings, sodass eine
  aktive onPC-Session nicht nach 20 s getrennt wird

#### Scenario: Shutdown bei unerreichbarer Gegenstelle

- **WHEN** `shutdown(timeout=5.0)` bei unerreichbarem Host aufgerufen wird
- **THEN** kehrt `shutdown` innerhalb des Zeitfensters zurück

### Requirement: Hintergrund-Abfragen ohne Blockade der Steuerung

`PlaybacksRequest`-Frames SHALL in der `SendQueue` mit niedrigerer Priorität als
Tasten-, Kommando-, Encoder- und Fader-Aktionen geführt und je Block koalesziert
werden. Der `BackpressureGuard` MUST die Senderate nur bei realem Anwachsen des
Transport-Schreibpuffers drosseln.

#### Scenario: Tasten und Encoder haben Vorrang vor Feedback-Abfragen

- **WHEN** gleichzeitig `PlaybacksRequest`-Abfragen sowie Tasten- und
  Encoder-Aktionen anstehen
- **THEN** sendet der Client zuerst Steuer- und Wert-Frames und zuletzt die
  koaleszierte Abfrage
