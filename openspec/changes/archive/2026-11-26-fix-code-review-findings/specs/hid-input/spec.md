# Spec Delta

## ADDED Requirements

### Requirement: Gemeinsamer nichtblockierender MIDI-Ausgabepfad

Der Daemon SHALL je MIDI-Gerät höchstens ein Raw-MIDI-Handle halten und sowohl
`[led]` als auch Executor-Feedback nichtblockierend darüber senden, ohne ein
unbeteiligtes Ersatzgerät auszuwählen. Vor `os.write` MUST der gesamte Frame in
den freien Puffer passen, und der Status-ioctl MUST einen 64-Bit-`time64`-Fallback
unterstützen.

#### Scenario: ASL wird im Betrieb ab- und wieder angesteckt

- **WHEN** die ASL bei aktivem `[led]` abgezogen und erneut eingesteckt wird
- **THEN** blockiert der Event-Loop nicht und Eingaben sowie LEDs laufen weiter

#### Scenario: Abgezogene ASL bespielt kein fremdes Gerät

- **WHEN** `led.enabled = true` ohne `led.device` gesetzt ist, die ASL fehlt und
  ein fremdes MIDI-Gerät angeschlossen ist
- **THEN** sendet der Daemon keine ASL-LED-Frames an das fremde Gerät

#### Scenario: Kein zerrissener 3-Byte-MIDI-Frame

- **WHEN** im Ausgabepuffer weniger als drei Bytes frei sind
- **THEN** schreibt der Daemon keinen Teil-Frame

### Requirement: Sofortiges Reader-Abmelden bei MIDI-Disconnect

Meldet `os.read` auf einem Raw-MIDI-Handle EOF oder einen `OSError` (außer
`BlockingIOError`), MUST das Handle seinen Event-Loop-Reader sofort entfernen;
schlägt `__init__` nach `os.open` fehl, MUST der FD sofort geschlossen werden.

#### Scenario: USB-MIDI-Kabel wird bei voller Queue gezogen

- **WHEN** ein MIDI-Gerät getrennt wird, während die Eingabe-Queue voll ist
- **THEN** wird der Reader sofort abgemeldet und es entsteht keine CPU-Schleife

### Requirement: Isolierte Profilfehler und eindeutige Knotenauswahl

Schlägt die Profilprüfung in `reconcile` für ein Gerät fehl, SHALL der Daemon
nur dieses Gerät mit Backoff zurückstellen und alle anderen Geräte sowie die
Web-UI weiterbetreiben. HID-Encoder-Decoder MUST bei Apply und Disconnect
geleert werden, und baugleiche Geräte MUST getrennte Geräteknoten erhalten.

#### Scenario: Ungültiges Geräteprofil nach Konfigurationsänderung

- **WHEN** ein gespeichertes Profil einen vom Gerät nicht unterstützten Code
  verlangt
- **THEN** protokolliert der Daemon den Fehler für dieses Gerät ohne Neustart-Schleife

#### Scenario: Zwei baugleiche Controller

- **WHEN** zwei Geräte mit identischer Vendor-/Product-ID konfiguriert und
  angeschlossen sind
- **THEN** öffnet der Daemon zwei verschiedene Geräteknoten
