# Verification

Stand: 2026-11-26

## Automatisierte Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `pytest` | 419 Tests bestanden |
| `npm run test` | 38 Tests bestanden |
| `npm run check` | 0 Fehler, 0 Warnungen |
| `npm run check:offline` | keine externen Netzwerkressourcen |
| `npm run build` | erfolgreich |

Abgedeckt: Konfigurationsdefaults und -validierung für
`[mapping.value_acceleration]`, das Opt-in `accelerated` (nur absolute Encoder
mit Fader-Ziel), Kurvenfunktion und Ratenfenster, virtueller Wert mit 1:1 bei
langsamer und Verstärkung bei schneller Drehung, Klemmung an beiden Enden,
Reset bei Konfigurationswechsel sowie die Checkbox im Mapping-Editor.

## Software-Prüfung auf dem Pi (2026-11-26)

- Backend und Web-UI wurden nach `/opt/ma2pi/app` installiert; der Dienst läuft
  mit dem neuen Stand.
- Live-Konfiguration: `mc_encoder_1` ist mit `page = "current"`,
  `executor = 2`, `kind = "fader"` und `accelerated = true` aktiv. Ein Backup
  wurde vor der Änderung angelegt.
- `[mapping.value_acceleration]` fehlt in der Live-Konfiguration; es greifen die
  Standardwerte (`linear`, `0.12`, `2`, `10`, `8.0`).
- Simulation mit dem installierten Code und der Live-Konfiguration:
  - langsam: `0.0`, `0.0079`, `0.0157` (exakt 1:1)
  - schnell: 40 Schritte im 10-ms-Raster erreichen `1.0` nach 21 Frames
- Die Oberfläche wird mit dem neuen Build (`index-fUT3pDst.js`) ausgeliefert.

## Hardware-Abnahme (bestanden)

Vom Benutzer am 2026-11-26 am ENC bestätigt: Die Beschleunigung funktioniert
wie gewünscht. Langsame Drehung bleibt fein, eine kräftige Umdrehung erreicht
den vollen Faderbereich, das Opt-in wirkt je Encoder und die physischen Fader
sowie relativen Encoder bleiben unverändert.

Voraussetzung ist der Parser-Fix aus `add-midicraft-input`: Note-On mit
Velocity 0 muss als Wert `0.0` ankommen, sonst bleibt ein Executor am unteren
Ende stehen.
