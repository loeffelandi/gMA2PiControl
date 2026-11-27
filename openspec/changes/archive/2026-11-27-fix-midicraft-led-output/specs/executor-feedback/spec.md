# Spec Delta

## Purpose

Schützt die LED-Ausgabe an MIDI-Controller: Feedback je Gerät schaltbar,
getaktete Frames und kein Weiterschreiben an Geräte, die nichts abnehmen.
Setzt `add-midicraft-led-feedback` voraus.

## ADDED Requirements

### Requirement: Feedback je Gerät schaltbar

`[profiles.<id>.led_feedback]` SHALL den optionalen Schlüssel `enabled`
(Bool, Default `true`) akzeptieren. Bei `enabled = false` MUST `ma2pi` für
Geräte dieses Profils keine LED-Ziele bilden, keine Playbacks nur für dieses
Gerät abfragen und keine LED-Frames senden. Andere Geräte MUST unbeeinflusst
bleiben.

#### Scenario: ENC aus, ASL an

- **WHEN** `[feedback] enabled = true` gilt, `midicraft-enc` hat
  `led_feedback.enabled = false` und `asl-mk2-e4b3` hat Feedback aktiv
- **THEN** sendet `ma2pi` LED-Frames nur an die ASL und keine an den ENC

#### Scenario: Alle Profile aus

- **WHEN** jedes Profil mit `led_feedback` hat `enabled = false`
- **THEN** unterbleibt das Polling wie bei „kein LED-fähiges Ziel“

#### Scenario: Eingabe bleibt unberührt

- **WHEN** das Feedback eines Geräts abgeschaltet ist
- **THEN** werden Eingaben dieses Geräts unverändert verarbeitet

### Requirement: Getaktete LED-Ausgabe

`ma2pi` SHALL LED-Frames je Gerät mit einem Mindestabstand senden, der über
`frame_interval_ms` in `[profiles.<id>.led_feedback]` festgelegt wird (ganze
Zahl 1–500, Default 20). Pro Gerät MUST höchstens ein Frame je Intervall das
Gerät erreichen. Ein neuer Zustand für eine LED, deren Frame noch aussteht, MUST
den offenen ersetzen. Werte außerhalb des Bereichs MUST die
Konfigurationsprüfung mit Nennung des Feldes ablehnen.

#### Scenario: Startzustand verteilt

- **WHEN** beim Start 15 LEDs gesetzt werden müssen und `frame_interval_ms = 20`
  gilt
- **THEN** liegen zwischen zwei Frames an dasselbe Gerät mindestens 20 ms

#### Scenario: Offener Frame wird ersetzt

- **WHEN** für eine LED ein Frame aussteht und sich ihr Zustand erneut ändert
- **THEN** wird nur der neueste Zustand gesendet

#### Scenario: Gerät beeinflusst anderes Gerät nicht

- **WHEN** der Ausgabestau eines Geräts länger dauert als das Intervall eines
  anderen
- **THEN** sendet das andere Gerät weiter im eigenen Takt

#### Scenario: Ungültiges Intervall

- **WHEN** `frame_interval_ms = 0` konfiguriert ist
- **THEN** lehnt `--check-config` die Konfiguration ab und nennt
  `led_feedback.frame_interval_ms`

### Requirement: Ausgabestau pausiert die LED-Ausgabe

Meldet das Betriebssystem für ein MIDI-Gerät länger als 2 Sekunden
ausstehende Ausgabe, die das Gerät nicht abnimmt, oder lehnt es Schreibversuche
dauerhaft ab, SHALL `ma2pi` die LED-Ausgabe für dieses Gerät pausieren und
genau eine Warnung mit Gerät und Anzahl ausstehender Bytes protokollieren.
Eingaben dieses Geräts MUST weiter verarbeitet werden. Nach dem erneuten
Öffnen des Geräts MUST die Ausgabe wieder aufgenommen und der vollständige
Zustand neu gesendet werden.

#### Scenario: Gerät nimmt nichts mehr ab

- **WHEN** ein Gerät 2 Sekunden lang ausstehende Ausgabe nicht abnimmt
- **THEN** sendet `ma2pi` keine weiteren LED-Frames an dieses Gerät und
  protokolliert eine Warnung

#### Scenario: Eingabe läuft weiter

- **WHEN** die LED-Ausgabe eines Geräts pausiert ist
- **THEN** werden Eingaben dieses Geräts weiter zugestellt

#### Scenario: Gerät wird neu geöffnet

- **WHEN** ein pausiertes Gerät nach Disconnect erneut geöffnet wird
- **THEN** nimmt `ma2pi` die Ausgabe wieder auf und sendet den aktuellen
  Zustand aller LEDs erneut

#### Scenario: Statusabfrage nicht verfügbar

- **WHEN** das Betriebssystem keinen Ausgabestatus liefert
- **THEN** gilt das Gerät als nicht gestaut und `ma2pi` verhält sich wie bisher
