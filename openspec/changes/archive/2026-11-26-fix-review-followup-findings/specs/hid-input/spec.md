# Spec Delta

## ADDED Requirements

### Requirement: Kurzes Abfließen der Abschaltsequenz vor dem Verwerfen

Beim Schließen eines schreibbar geöffneten MIDI-Handles SHALL der Daemon kurz
(höchstens 30 ms) warten, bis eine unmittelbar zuvor geschriebene
Abschaltsequenz (`DISABLE`) vom Gerät abgenommen wurde, und erst bei danach
weiterhin ausstehenden Bytes `SNDRV_RAWMIDI_IOCTL_DROP` ausführen. Das
Installationsskript MUST für `/opt/ma2pi/app` und `/opt/ma2pi/.venv` unabhängig
von der `umask` Leserechte für den Dienstbenutzer setzen.

#### Scenario: Gesunde ASL empfängt DISABLE beim Dienststopp

- **WHEN** der Dienst beendet wird und das ASL-Gerät Ausgabedaten regulär
  abnimmt
- **THEN** erreicht `9F 7F 7E` das Gerät vor dem Schließen des Dateideskriptors

#### Scenario: Gestautes Gerät verzögert den Stopp weiterhin nicht

- **WHEN** ein MIDI-Gerät beim Schließen keine Bytes abnimmt
- **THEN** verwirft der Daemon die Restdaten nach höchstens 30 ms und kehrt
  sofort zurück
