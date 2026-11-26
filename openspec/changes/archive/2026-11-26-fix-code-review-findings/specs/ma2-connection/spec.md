# Spec Delta

## ADDED Requirements

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
