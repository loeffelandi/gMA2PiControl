# Spec Delta

## ADDED Requirements

### Requirement: Lesbare Zusammenfassung zusammengesetzter ASL-LED-Pakete

`describe_midi` SHALL bei zusammengesetzten ASL-LED-Schreibzugriffen
(`9F 7F 7F` gefolgt von Helligkeits- und Farb-Note-On) die angesteuerte
Ziel-Note statt des vorangestellten Freigabe-Frames im Ereignis-Log nennen und
reine Freigabe-/Abschaltsequenzen als solche kennzeichnen.

#### Scenario: ASL-Modus-LED wechselt die Farbe

- **WHEN** `LedOutput` das 9-Byte-Paket für Note 9 sendet
- **THEN** nennt der Kurztext im Ereignis-Log Note 9 statt `note 127 · velocity 127`
