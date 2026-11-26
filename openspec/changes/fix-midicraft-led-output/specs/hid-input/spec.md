# Spec Delta

## ADDED Requirements

### Requirement: MIDI-Geräte schließen ohne Drain-Wartezeit

Beim Schließen eines schreibbar geöffneten MIDI-Geräts SHALL der Daemon
ausstehende Ausgabe verwerfen, bevor er das Gerät schließt. Das Schließen MUST
nicht auf ein Gerät warten, das Ausgabe nicht abnimmt; der Dienststopp darf
dadurch nicht länger als die übrigen Aufräumschritte dauern. Schlägt das
Verwerfen fehl, MUST der Daemon trotzdem schließen und nur eine Debug-Meldung
schreiben.

#### Scenario: Stopp mit gestautem Gerät

- **WHEN** der Dienst beendet wird, während ein MIDI-Gerät Ausgabe nicht
  abnimmt
- **THEN** wird das Gerät ohne Drain-Wartezeit geschlossen und der Dienst endet
  innerhalb des normalen Stopp-Zeitfensters

#### Scenario: Hotplug mit ausstehender Ausgabe

- **WHEN** ein Gerät mit ausstehender Ausgabe verschwindet und wieder erscheint
- **THEN** wird das alte Handle sofort geschlossen und das Gerät ohne Wartezeit
  neu geöffnet

#### Scenario: Verwerfen schlägt fehl

- **WHEN** das Betriebssystem das Verwerfen ablehnt
- **THEN** schließt der Daemon das Gerät trotzdem und schreibt eine
  Debug-Meldung
