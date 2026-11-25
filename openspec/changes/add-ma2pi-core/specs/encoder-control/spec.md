# Spec Delta

## Purpose

Übersetzt die vier Drehgeber des ASL MK2 E4B3 in MA2-Encoder-Wheels oder
Attributänderungen, bündelt Detent-Deltas zu wenigen Frames, unterstützt
Beschleunigung sowie Normal/Fine/Ultra und schützt die onPC vor zu hohen
Frame-Raten.

## ADDED Requirements

### Requirement: Encoder-Zielmapping

Jeder physische Encoder SHALL in der Konfiguration genau ein Ziel erhalten:
Wheel 1–4 (Main), Wheel 5–10 (Screen) oder einen Attributnamen. Ungültige
Wheel-Nummern, doppelte Encoder-IDs oder unbekannte Ziele MUST die
Konfigurationsvalidierung fehlschlagen lassen.

#### Scenario: Encoder auf Main-Wheel

- **WHEN** Encoder 1 auf Wheel 1 gemappt ist
- **THEN** werden seine Deltas als Änderungen an Wheel 1 gesendet

#### Scenario: Encoder auf Attribut

- **WHEN** Encoder 2 auf das Attribut `Dimmer` gemappt ist
- **THEN** werden seine Deltas als relative Dimmer-Änderung gesendet

#### Scenario: Ungültige Wheel-Nummer

- **WHEN** die Konfiguration Wheel 11 zuweist
- **THEN** bricht der Start mit einer Meldung ab, die den gültigen Bereich 1–10 nennt

#### Scenario: Doppelte Encoder-ID

- **WHEN** zwei Einträge dieselbe Encoder-ID definieren
- **THEN** bricht die Validierung mit Verweis auf beide Einträge ab

### Requirement: Delta-Akkumulation und Flush

Die Engine SHALL signed Detent-Deltas pro Encoder akkumulieren und höchstens
einmal pro konfiguriertem Flush-Intervall (Default 40 ms) senden. Ein Flush mit
Delta 0 MUST unterbleiben; nach einer Idle-Frist MUST der letzte aufgelaufene
Delta gesendet werden, damit keine Detents verloren gehen.

#### Scenario: Schneller Stoß

- **WHEN** innerhalb von 10 ms zehn Detents an einem Encoder anfallen
- **THEN** entsteht daraus ein einziger Frame mit dem akkumulierten Delta statt zehn Einzelframes

#### Scenario: Langsame Drehung

- **WHEN** die Detents langsamer als das Flush-Intervall eintreffen
- **THEN** wird jeder Detent spätestens nach Ablauf des Intervalls gesendet

#### Scenario: Gleiche Drehung in beide Richtungen

- **WHEN** innerhalb eines Intervalls gleich viele Detents vorwärts und rückwärts anfallen
- **THEN** ist das akkumulierte Delta 0 und es wird kein Frame gesendet

#### Scenario: Letzter Detent vor dem Loslassen

- **WHEN** die Drehung endet, kurz nachdem ein Detent akkumuliert wurde
- **THEN** wird dieser letzte Delta nach der Idle-Frist noch gesendet

### Requirement: Beschleunigungskurve

Die Übersetzung von Detents in Delta SHALL eine konfigurierbare Kurve
(`none`, `linear`, `exponentiell`) verwenden. Bei schnellem Drehen MUST der Delta
pro Detent größer sein als bei langsamem; das Vorzeichen MUST erhalten bleiben
und ein von Null verschiedener Input darf nie Delta 0 erzeugen.

#### Scenario: Langsame Drehung ohne Beschleunigung

- **WHEN** die Kurve `none` aktiv ist und ein Detent eintrifft
- **THEN** entspricht der gesendete Delta genau einem Detent

#### Scenario: Schnelle Drehung mit Beschleunigung

- **WHEN** die Kurve `linear` aktiv ist und mehrere Detents innerhalb eines kurzen Fensters eintreffen
- **THEN** ist der Delta pro Detent größer als bei einem einzelnen langsamen Detent

#### Scenario: Vorzeichen bleibt erhalten

- **WHEN** schnell gegen den Uhrzeigersinn gedreht wird
- **THEN** sind alle gesendeten Deltas negativ

### Requirement: Auflösungsumschaltung Normal/Fine/Ultra

Modifier-Tasten SHALL die Encoder-Auflösung zwischen Normal, Fine und Ultra
umschalten. Die Umschaltung MUST nur nachfolgende Detents betreffen; ein davor
akkumulierter Delta MUST mit der alten Auflösung geflusht werden. Bei
gleichzeitig gehaltenen Fine- und Ultra-Modifern MUST Ultra Vorrang haben.

#### Scenario: Fine hält die Auflösung fein

- **WHEN** Fine gehalten wird und ein Detent eintrifft
- **THEN** wird der konfigurierte Fine-Anteil (z. B. `0.1`) statt des Normalwerts gesendet

#### Scenario: Umschaltung mitten in der Akkumulation

- **WHEN** während eines offenen Akkumulationsfensters auf Fine umgeschaltet wird
- **THEN** wird der bisherige Delta mit Normal-Auflösung geflusht und erst der nächste Detent mit Fine-Auflösung gesendet

#### Scenario: Ultra und Fine gleichzeitig

- **WHEN** Fine und Ultra gleichzeitig gehalten werden
- **THEN** gilt die Ultra-Auflösung

### Requirement: Transportauswahl CMD-Wrapper oder nativ

Der Encoder-Transport MUST per Konfiguration zwischen CMD-Wrapper und nativem
Protokoll wählbar sein; Default ist der CMD-Wrapper, solange das native
Wheel-Format nicht per Capture verifiziert ist. Im CMD-Modus SHALL pro Flush
genau ein Befehl mit relativem Delta entstehen, im nativen Modus genau ein
nativer Frame.

#### Scenario: CMD-Wrapper für ein Attribut

- **WHEN** der CMD-Modus aktiv ist und ein akkumulierter Delta für `Dimmer` anliegt
- **THEN** wird ein `command`-Frame mit einer relativen Anweisung wie `Attribute "Dimmer" At +0.1 Please` gesendet

#### Scenario: Nativer Attribut-Frame

- **WHEN** der native Modus aktiv ist und ein Attribut-Ziel konfiguriert ist
- **THEN** wird pro Flush ein nativer Encoder-Frame mit Name und Delta gesendet

#### Scenario: Nativer Wheel-Modus ohne verifiziertes Format

- **WHEN** der native Modus für ein Wheel-Ziel aktiviert ist, aber kein verifiziertes Wheel-Frame-Format vorliegt
- **THEN** bricht der Start mit dem Hinweis ab, zuerst den Capture-Workflow auszuführen oder den CMD-Modus zu wählen

#### Scenario: Dry-Run zeigt den gewählten Transport

- **WHEN** der Daemon im Dry-Run mit CMD-Modus läuft
- **THEN** werden die erzeugten CMD-Frames protokolliert, ohne dass eine Verbindung geöffnet wird

### Requirement: Rate-Limiting und Lockup-Schutz

Encoder-Ausgaben SHALL dem globalen Rate-Limiter unterliegen. Bei Sättigung MUST
der Daemon Deltas weiter akkumulieren, statt Frames unbegrenzt zu puffern; der
akkumulierte Delta MUST auf einen konfigurierten Maximalwert begrenzt und jedes
Verwerfen geloggt werden.

#### Scenario: Dauerhaft schnelle Drehung

- **WHEN** ein Encoder 100 Detents pro Sekunde liefert und das Limit 25 Frames pro Sekunde beträgt
- **THEN** werden höchstens 25 Frames pro Sekunde gesendet und die Summe der gesendeten Deltas entspricht bis zur Obergrenze der Eingabe

#### Scenario: Begrenzter Puffer

- **WHEN** die onPC über längere Zeit keine Frames mehr abnimmt
- **THEN** wächst der Encoder-Puffer nicht unbegrenzt, sondern wird bei der konfigurierten Obergrenze gekappt und das Kappen protokolliert

#### Scenario: Nachlauf nach dem Loslassen

- **WHEN** die Drehung endet und noch ein akkumulierter Delta offen ist
- **THEN** wird dieser Delta nach dem nächsten freien Limit-Slot gesendet

### Requirement: Kompatibilität mit aufgezeichnetem Wheel-Protokoll

Nach einem Capture MUST der native Wheel-Modus strukturell dieselben Frames
erzeugen wie die aufgezeichnete Referenz (gleiche Frame-Art und Felder), und ein
Fixture der Aufzeichnung MUST in den Tests wiederverwendet werden. Ohne Capture
MUST der CMD-Wrapper unverändert funktionieren.

#### Scenario: Capture-Fixture wird reproduziert

- **WHEN** ein aufgezeichneter Wheel-Frame als Fixture vorliegt und der native Modus aktiv ist
- **THEN** erzeugt die Engine für dieselbe Eingabe einen Frame mit identischer Struktur

#### Scenario: CMD-Modus bleibt unabhängig vom Capture

- **WHEN** noch kein Capture vorliegt
- **THEN** funktionieren alle Encoder im CMD-Modus ohne Fehler und ohne native Wheel-Frames
