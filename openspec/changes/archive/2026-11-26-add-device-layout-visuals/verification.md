# Verification

Stand: 2026-11-26

## Automatisierte Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `pytest` (Change-Tests: Layouts, Config, Mapping, Playback, Learn, Geräte-API, MIDI-Input) | 246 bestanden |
| `npm run check` | 0 Fehler, 12 bestehende Warnungen |
| `npm run test` | 61 bestanden |
| `npm run build` | erfolgreich |
| `--check-config` | Konfiguration gültig |
| `openspec validate add-device-layout-visuals --strict` | gültig |

Hinweis: Der vollständige Backend-Lauf enthält derzeit einen Fehler aus dem
parallel entstandenen Activity-Monitor (`tests/test_activity.py`); er gehört
nicht zu diesem Change.

## Hardware-Abnahme am Pi

### Cherry-Layout

Vom Benutzer gegen die echte Tastatur geprüft und bestätigt. Dabei korrigiert:

- 18 Spalten statt 21; Pause/Go-/Go+ als 2×2-Blöcke.
- `Please` zwei Spalten breit unter `If`/`At`; `Down` unter `Set`.
- `X13` ergänzt; `X11`–`X15` grün, `X16`–`X20` blau.
- MA-Taste beschriftet; Fd-Pg-Tasten rot, Ziel-Taste grün.

### Learn-Modus

Vom Benutzer bestätigt: Das Anlernen funktioniert. Die Gerätefläche markiert
das aktive Control pulsierend, zeigt die Aktion (`Drehen`, `Drücken`,
`Bewegen`) und scrollt das Feld automatisch in den sichtbaren Bereich.

### Bankwechsel und Anlernen einer neuen Bank

Vom Benutzer bestätigt: Der Bankwechsel in der Oberfläche funktioniert, und
eine neue Bank lässt sich anlernen.

### Bank-Offset und Mehrfachzuweisung

Vom Benutzer bestätigt: Der Bank-Offset verschiebt die Executor-Ziele je Bank
korrekt, und Mehrfachzuweisungen verteilen die Executor-Nummern in
Klick-Reihenfolge und werden atomar gespeichert.

### Cherry-Scancodes (Task 9.4)

Vom Benutzer bestätigt: Die bedruckten Labels lösen die erwarteten logischen
Controls aus; es sind keine Abweichungen mehr offen.

## Offene Punkte

Keine. Change archivieren und die Delta-Specs in die Haupt-Specs übernehmen.
