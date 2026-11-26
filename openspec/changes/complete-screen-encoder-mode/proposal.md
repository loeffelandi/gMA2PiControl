# Proposal

## Why

Der Screen-Modus der ASL-Encoder ist heute nur ein Zustandsschalter: Die Taste
wechselt Modus und LED, aber der Encoder-Klick (Fine/Ultra) adressiert weiterhin
den Attribut-Namen der onPC-Page. Im Screen-Modus entsteht dadurch ein Frame für
den falschen Encoder. Zusätzlich lässt sich `[mapping.screen_encoders]` nur per
TOML pflegen, obwohl die Oberfläche das Mapping bereits vollständig verwaltet.

## What Changes

- Der Encoder-Klick im Screen-Modus bezieht den Auflösungsframe auf den
  konfigurierten Screen-Encoder-Namen des Slots; fehlt der Name, wird kein Frame
  gesendet und eine Warnung protokolliert.
- Die mitgelieferte `config.toml` belegt `[mapping.screen_encoders]` mit der
  onPC-Nummerierung 5–8 in umgekehrter Reihenfolge: Slot 1 → 8, Slot 2 → 7,
  Slot 3 → 6, Slot 4 → 5.
- MA halten (Cherry-Logo) und dabei einen Encoder drehen adressiert
  vorübergehend die Screen-Encoder.
- Die rechte ASL-Taste (`asl_button_3`, Note 11) sendet den `NIPPLE`-Hardkey
  der onPC.
- Die Mapping-Seite zeigt pro physischem Encoder ein Dropdown für den
  Screen-Encoder (5–8 oder „keiner“) und leert entfernte Slots beim Speichern.
- Tests decken beide Pfade ab: Auflösungsframe mit Screen-Namen, kein Frame bei
  fehlendem Namen, UI-Patch mit gesetzten und entfernten Screen-Encodern.
- README und `config.toml` dokumentieren den Editor und den noch offenen
  Mitschnitt der echten Screen-Encoder-Namen.

## Capabilities

### New Capabilities

Keine.

### Modified Capabilities

- `encoder-control`: Neue Anforderung, dass die Auflösung im Screen-Modus den
  Screen-Encoder-Namen verwendet und bei fehlendem Namen keinen Frame sendet.
- `config-ui`: Der Geräte- und Mapping-Editor deckt zusätzlich die vier
  Screen-Encoder-Namen ab (Delta in `add-ma2pi-config-ui`).

## Impact

- **Code:** `ma2pi/ma2_client.py` (Auflösungsziel im Screen-Modus),
  `web/src/lib/MappingPage.svelte` (Screen-Encoder-Editor), Tests in
  `tests/test_ma2_client.py` und `web/src/lib/MappingPage.test.ts`.
- **Konfiguration:** `[mapping.screen_encoders]` bleibt optional; die
  Validierung (Slots 1–4) ist bereits vorhanden.
- **Dokumentation:** `README.md`, `config.toml`, `docs/api.md` nur wo nötig.
- **Nicht enthalten:** Das Verifizieren der echten Screen-Encoder-Namen an der
  onPC; dafür ist weiterhin ein Mitschnitt nötig.
