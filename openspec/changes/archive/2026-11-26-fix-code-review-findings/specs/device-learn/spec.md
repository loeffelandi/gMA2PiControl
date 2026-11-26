# Spec Delta

## ADDED Requirements

### Requirement: Entprellung und Velocity-Schwelle beim Bank-Lernen

Beim Anlernen einer Bank-Belegung SHALL der Daemon für `kind = "button"` erst
einen echten Druck (Velocity `>= 2`) übernehmen und unmittelbare Nachläufer
derselben gerade erfassten Note ignorieren, damit Fader- und Encoder-Bewegungen
keinen falschen Doppelnoten-Fehler beim nächsten Control auslösen.

#### Scenario: Fader-Bewegung erzeugt keinen Doppelnoten-Fehler

- **WHEN** das aktive Control ein Fader ist und dessen Bewegung mehrere
  aufeinanderfolgende Nachrichten derselben Note sendet
- **THEN** übernimmt die Sitzung die Note einmalig und verwirft die direkten
  Folgenachrichten ohne Fehlermeldung

#### Scenario: Button-Release löst kein nächstes Control aus

- **WHEN** eine Taste mit Velocity `0` oder `1` losgelassen wird, während das
  nächste Control ein Button ist
- **THEN** wird das Loslassen ignoriert

### Requirement: Event-Updates und Schutz vor verwaisten Bank-Learn-Sitzungen

Beim Start einer Bank-Learn-Sitzung MUST der Daemon gehaltene Tasten des Geräts
freigeben und jeden Zustandswechsel als `device_learn`-Event senden. Bleibt eine
pausierte Sitzung über das erweiterte Inaktivitätsfenster hinaus unbenutzt, MUST
sie automatisch enden, damit Eingaben des Geräts nicht dauerhaft verworfen werden.

#### Scenario: Verwaiste Sitzung gibt Gerät wieder frei

- **WHEN** eine pausierte Bank-Learn-Sitzung nicht fortgesetzt wird
- **THEN** beendet der Daemon die Sitzung nach Ablauf der Frist ohne
  Konfigurationsänderung und leitet Eingaben wieder weiter
