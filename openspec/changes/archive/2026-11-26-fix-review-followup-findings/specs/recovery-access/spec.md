# Spec Delta

## ADDED Requirements

### Requirement: Konsistenter Hotspot-Zustand bei Dateischreibfehlern

Schlägt in `RecoveryService` das Persistieren von `recovery.json` nach einer
bereits in NetworkManager angewendeten Änderung fehl, MUST der Dienst auch den
Live-Zustand in NetworkManager nach bestem Bemühen auf den vorherigen Stand
zurücksetzen, damit Speicher, Datei und Schnittstelle übereinstimmen.

#### Scenario: Schreibfehler auf `recovery.json` lässt keinen Geister-Hotspot aktiv

- **WHEN** das Einschalten des Hotspots in NetworkManager gelingt, das Schreiben
  von `recovery.json` aber mit `OSError` fehlschlägt
- **THEN** deaktiviert der Dienst das AP-Profil wieder und behält den alten
  Zustand bei
