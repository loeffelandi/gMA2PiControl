# device-learn Specification

## Purpose

Beschreibt das Anlernen der physischen Control-Belegung: Weil die Noten der
MIDICRAFT-Geräte frei einstellbar sind, muss die Zuordnung von Control zu
MIDI-Kanal und Note je Bank einmalig aus der Gerätefläche heraus gelernt und in
das Profil geschrieben werden können.

## Requirements

### Requirement: Bankwahl beim Lernen

Der Daemon SHALL eine Learn-Sitzung für ein Gerät und eine vom Benutzer
gewählte Bank starten können. Die Bank MUST ausschließlich aus der
Editorauswahl stammen und MUST NOT aus einem separaten Wechselereignis
abgeleitet werden. Die Sitzung MUST die noch ungebundenen Controls dieser Bank
in Layout-Reihenfolge durchlaufen und den erwarteten MIDI-Kanal der Bank
verwenden.

#### Scenario: Sitzung für Bank 2 starten

- **WHEN** der Benutzer Bank 2 wählt und die Learn-Sitzung startet
- **THEN** werden die ungebundenen Controls von Bank 2 in Layout-Reihenfolge durchlaufen

#### Scenario: Keine Bankwahl

- **WHEN** eine Learn-Sitzung ohne gewählte Bank gestartet werden soll
- **THEN** wird der Start abgelehnt und die Oberfläche verlangt eine Bank

### Requirement: Geführter Ablauf

Die Oberfläche MUST das aktuelle Control hervorheben, den Fortschritt anzeigen
und Überspringen, Abbrechen und Speichern anbieten. Es MUST höchstens eine
Learn-Sitzung gleichzeitig aktiv sein. Eine zweite Sitzung MUST abgelehnt
werden, ohne die laufende zu verändern.

#### Scenario: Erstes Control aktiv

- **WHEN** eine Sitzung mit drei ungebundenen Controls gestartet wird
- **THEN** ist das erste Control in Layout-Reihenfolge aktiv und der Fortschritt zeigt 0 von 3

#### Scenario: Zweite Sitzung

- **WHEN** bereits eine Learn-Sitzung läuft und eine weitere gestartet wird
- **THEN** wird die zweite abgelehnt und die laufende Sitzung bleibt unverändert

### Requirement: Erfassen der physischen Belegung

Während einer Learn-Sitzung MUST das nächste Ereignis auf dem MIDI-Kanal der
gewählten Bank dem aktiven Control zugeordnet werden. Die Note MUST aus dem
Ereignis übernommen und die Art aus dem Control-Inventar bestimmt werden. Ein
Ereignis auf einem anderen Kanal MUST NOT übernommen werden. Das Ereignis MUST
die Sitzung speisen und MUST NOT an die Mapping-Engine oder die onPC
weitergereicht werden.

#### Scenario: Taste anlernen

- **WHEN** das aktive Control eine Taste ist und die physische Taste gedrückt wird
- **THEN** wird die gesendete Note gespeichert und die Sitzung springt zum nächsten Control

#### Scenario: Fader anlernen

- **WHEN** das aktive Control ein Fader ist und der Fader bewegt wird
- **THEN** wird die dabei gesendete Note gespeichert und es entsteht kein Playback-Frame

#### Scenario: Ereignis auf falschem Kanal

- **WHEN** während der Sitzung ein Ereignis auf einem anderen als dem Bank-Kanal eintrifft
- **THEN** wird es nicht übernommen und die Oberfläche weist auf den erwarteten Kanal hin

### Requirement: Überspringen, Abbrechen und Wiederholen

Der Benutzer SHALL ein Control überspringen, die Sitzung abbrechen oder ein
bereits gebundenes Control erneut anlernen können. Ein Abbruch MUST alle noch
nicht gespeicherten Belegungen verwerfen. Nach einem Timeout MUST die Sitzung
pausieren und auf erneute Eingabe warten, ohne die bisherigen Belegungen zu
verlieren.

#### Scenario: Control überspringen

- **WHEN** der Benutzer das aktive Control überspringt
- **THEN** bleibt es ungebunden und die Sitzung fährt mit dem nächsten Control fort

#### Scenario: Sitzung abbrechen

- **WHEN** die Sitzung vor dem Speichern abgebrochen wird
- **THEN** bleibt die Konfiguration unverändert

#### Scenario: Timeout

- **WHEN** während der Sitzung längere Zeit kein Ereignis eintrifft
- **THEN** pausiert die Sitzung und die bereits erfassten Belegungen bleiben erhalten

#### Scenario: Control erneut anlernen

- **WHEN** ein bereits gebundenes Control ausdrücklich erneut angelermt wird
- **THEN** ersetzt die neue Note die bisherige Bindung nach dem Speichern

### Requirement: Doppelte Note beim Lernen

Eine gelernte Note MUST innerhalb der gewählten Bank und ihres Kanals eindeutig
sein. Ist die Note in dieser Bank bereits einem anderen Control zugeordnet, MUST
die Sitzung die Übernahme ablehnen und das aktive Control beibehalten. Dieselbe
Note in einer anderen Bank mit anderem Kanal MUST zulässig bleiben.

#### Scenario: Note bereits vergeben

- **WHEN** die gedrückte Note in derselben Bank bereits einem anderen Control gehört
- **THEN** erscheint ein Hinweis mit dem belegten Control und die Sitzung wartet auf eine andere Note

#### Scenario: Gleiche Note in anderer Bank

- **WHEN** die gedrückte Note in einer anderen Bank auf einem anderen Kanal bereits gelernt wurde
- **THEN** wird sie übernommen, weil der Kanal die Bänke unterscheidet

### Requirement: Atomares Speichern der gelernten Belegung

Die Sitzung SHALL die gelernten Noten erst auf ausdrücklichen Abschluss in das
Profil schreiben. Das Speichern MUST über den bestehenden Konfigurationspfad
erfolgen, die gesamte Konfiguration validieren und bei einem Fehler keine
Teiländerung hinterlassen.

#### Scenario: Sitzung abschließen

- **WHEN** die Sitzung mit gelernten Belegungen abgeschlossen wird
- **THEN** enthält das Profil der gewählten Bank genau diese Noten und die Gerätefläche zeigt die Belegung

#### Scenario: Speichern schlägt fehl

- **WHEN** die Konfiguration beim Abschluss ungültig ist
- **THEN** bleibt die gespeicherte Konfiguration unverändert und die Meldung nennt Profil, Bank, Kanal und Note

### Requirement: Geräteverlust während des Lernens

Verliert der Daemon das Gerät während einer Learn-Sitzung, MUST die Sitzung
pausieren und den Verlust melden. Nach dem erneuten Verbinden MUST die Sitzung
mit demselben aktiven Control und den bereits erfassten Belegungen fortgesetzt
werden können.

#### Scenario: Gerät wird getrennt

- **WHEN** das Gerät während der Sitzung entfernt wird
- **THEN** pausiert die Sitzung, die erfassten Belegungen bleiben erhalten und die Oberfläche meldet den Verlust

#### Scenario: Gerät kehrt zurück

- **WHEN** das Gerät wieder verbunden wird
- **THEN** kann die Sitzung am aktiven Control fortgesetzt werden

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
