# Proposal

## Why

Das Mapping im UI ist heute eine reine Tabelle. Für die Cherry-Tastatur und den ASL-MIDI-Controller ist die räumliche Anordnung aber entscheidend: Wer eine Taste zuweist, denkt in Reihen und Spalten, nicht in Scancodes. Ohne hinterlegtes Layout kann die Oberfläche die Geräte nicht grafisch darstellen, und jede Layout-Änderung müsste im Frontend hartkodiert werden.

## What Changes

- Neue Capability `device-layout`: Die Konfiguration beschreibt je Gerät eine schematische Darstellung (Raster aus Reihen/Spalten mit Key-Labeln und Control-Referenzen).
- Cherry G86-63400: Layout entsprechend dem aktuellen Tastaturfoto (Reihen, Spalten, bedruckte Labels, Zuordnung zu logischen Controls).
- ASL MK2-E4B3: schematische Darstellung mit vier Encodern, Encoder-Clicks und den drei Tasten.
- Das Layout ist **Daten**, nicht Code: Die UI liest es über die API und rendert daraus die grafische Ansicht.
- Layouts sind optional; fehlt eines, bleibt die tabellarische Ansicht wie heute nutzbar.
- Die Erfassung der echten Scancodes (Task 3.8 in `add-ma2pi-core`) bleibt davon unberührt und kann das Layout später befüllen.

Nicht enthalten: freies Zeichnen, Drag-and-drop-Layout-Editor, Mehrsprachigkeit der Labels, Layouts für fremde Geräte.

## Capabilities

### New Capabilities

- `device-layout`: Schema und API für schematische Geräte-Layouts (Raster, Labels, Control-Referenzen), damit die Oberfläche Tastatur und MIDI-Controller grafisch darstellen kann.

### Modified Capabilities

Keine. `config-ui` bleibt unverändert; die neue Capability ergänzt sie.

## Impact

- **Code:** `config.py` (neue `[layouts.*]`-Sektion), `ma2pi/web/` (Layout in `GET /api/config` bzw. `GET /api/devices`), Frontend-Rendering in `web/`.
- **Daten:** `config.toml` erhält Layout-Blöcke für `cherry-g86` und `asl-mk2-e4b3`.
- **Abhängigkeiten:** keine neuen.
- **Risiko:** Ein falsch gepflegtes Layout ist nur kosmetisch; die Funktion hängt weiterhin am Mapping, nicht am Layout.
