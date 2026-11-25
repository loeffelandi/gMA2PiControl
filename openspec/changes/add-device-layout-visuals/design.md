# Design

## Kontext

Die Cherry G86-63400 und der ASL MK2-E4B3 sind physisch unregelmäßig aufgebaut:
große Tasten spannen mehrere Zellen, der Ziffernblock sitzt versetzt, und beim
ASL liegen Encoder, Clicks und drei Tasten in einer eigenen Anordnung. Eine
Tabelle kann das nicht abbilden. Das Layout soll deshalb als **Daten** in der
Konfiguration liegen und von der Oberfläche gerendert werden.

Das bestehende Tastenbild der Cherry dient als Vorlage für Reihen, Spalten und
Labels; es ist die Grundlage für das mitgelieferte Layout.

## Ziele / Nicht-Ziele

**Ziele**

- Ein Layout-Schema, das Rechtecke beliebiger Spannweite abbildet.
- Mitgelieferte Layouts für `cherry-g86` und `asl-mk2-e4b3`.
- Klare Validierung gegen die vorhandenen Controls.
- Keine Verhaltensänderung für Mapping oder Frames.

**Nicht-Ziele**

- Layout-Editor per Drag-and-drop in v1.
- Pixelgenaue Nachbildung von Gehäuse, Farbe oder Beschriftungsfont.
- Layouts für Geräte, die nicht in `[devices.*]` konfiguriert sind.

## Entscheidungen

### Schema

```toml
[layouts.cherry]
device = "cherry"          # Referenz auf [devices.*]
columns = 18

[[layouts.cherry.rows]]
cells = [
  { label = "V1", control = "v1" },
  { label = "Pause", control = "pause", col_span = 2 },
  { label = "", col_span = 1 },              # Lücke
]
```

- `columns` ist die Bezugsbreite; jede Reihe zählt ihre Zellen selbst.
- `col_span` / `row_span` erlauben große Tasten.
- Eine Zelle ohne `control` ist reine Beschriftung (z. B. „Short Cuts“).
- `label` ist der gedruckte Text, `control` der Name aus dem Profil.

Alternative: Layout im Frontend hartkodieren. Verworfen, weil dann jede
Layout-Änderung ein Frontend-Build wäre und die Daten nicht beim Gerät lägen.

Alternative: SVG-Datei je Gerät. Verworfen für v1, weil nicht validierbar und
schwer per Learn-Modus zu befüllen.

### API

Das Layout wird mit den Geräten ausgeliefert:

```json
{
  "name": "cherry",
  "layout": {
    "columns": 18,
    "rows": [{"cells": [{"label": "V1", "control": "v1"}, "..."]}]
  }
}
```

`GET /api/devices` bleibt die Quelle; `GET /api/config` liefert zusätzlich die
rohen Layout-Blöcke für den Editor.

### Validierung

`config.py` prüft beim Laden:

1. `layouts.<name>.device` existiert in `[devices.*]`.
2. Jede `control`-Referenz kommt im Profil des Geräts vor.
3. `columns >= 1`, `col_span`/`row_span >= 1`, Summe je Reihe passt zu `columns`
   (oder wird als Warnung behandelt, wenn die Zeile absichtlich kürzer ist).

### Frontend

Eine `DeviceLayout`-Komponente rendert das Raster per CSS Grid. Spannen werden
auf `grid-column: span n` abgebildet. Zellen mit `control` sind klickbar und
öffnen die Mapping-Zelle; Zellen ohne Control sind statisch.

## Risiken

- **Layout veraltet gegenüber Hardware** → nur kosmetisch; Mapping bleibt korrekt.
- **Spannen-Summen passen nicht** → Validierungswarnung, Darstellung nutzt die
  angegebene Spanne und lässt die Reihe auslaufen.
- **Aufwand für die Cherry-Erfassung** → Layout kann schrittweise befüllt werden;
  fehlende Controls bleiben leere Zellen.

## Migration

Keine. Neue optionale Sektion `[layouts.*]`; bestehende Konfigurationen bleiben
gültig.
