# Spec Delta

## ADDED Requirements

### Requirement: Atomare Validierung, Locking und monotone Karenzzeit

`PUT /api/recovery` SHALL strikte JSON-Typen, `1..32` UTF-8-Bytes ohne
Steuerzeichen für die SSID sowie `8..63` druckbare ASCII-Zeichen für das
Passwort verlangen und bei `nmcli`-Fehlern Speicher sowie `recovery.json` auf
den vorherigen Stand zurücksetzen. `auto_cycle` MUST unter demselben Lock und
mit `time.monotonic` laufen.

#### Scenario: Fehlgeschlagenes `nmcli` erhält bisherigen Hotspot-Zustand

- **WHEN** der Hotspot aktiv ist und das Anwenden neuer Werte in `nmcli`
  fehlschlägt
- **THEN** bleiben die bisherigen Einstellungen in Speicher und `recovery.json`
  erhalten

#### Scenario: Mehrbyte-SSID über 32 UTF-8-Bytes wird abgelehnt

- **WHEN** eine SSID mit mehr als 32 UTF-8-Bytes gesendet wird
- **THEN** antwortet die API mit `422 validation_error` und Feldbezug `ssid`
