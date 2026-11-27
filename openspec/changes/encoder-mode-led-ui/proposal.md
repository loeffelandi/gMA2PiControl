# Proposal

## Why

Screen-Encoder-Umschaltung und LED-Feedback sind im Code fest verdrahtet: Der
momentane Screen-Modus hängt am Hardkey `MA`, die Fine-LED am
`resolution.cycle_modifier` und die Nipple-LED am Hardkey `NIPPLE`. `[led]`,
`[mapping.encoder_resolution]` und die Beschleunigungen sind zwar
konfigurierbar, in der Oberfläche aber unsichtbar. Jede neue Idee erfordert
heute Python- und Svelte-Änderungen. Ziel ist deshalb nicht nur diese eine
Sektion, sondern ein Katalog, aus dem die Oberfläche künftige Einstellungen
ohne eigene Formulararbeit rendert.

## What Changes

- **Neue Capability `config-catalog`:** Der Daemon veröffentlicht
  `GET /api/config/schema` mit je Feld Pfad, Gruppe, Scope (`device`/`mapping`),
  Typ, Wertebereich, Default, Einheit, Label, Hilfe, Sichtbarkeitsbedingung und
  `advanced`-Kennzeichen. Katalog und `parse_config` teilen dieselben Grenzen;
  ein Test erzwingt die Deckung.
- **Generische Einstellungs-UI:** Die Oberfläche rendert Abschnitte aus dem
  Katalog mit wiederverwendbaren Feldkomponenten (Zahl, Text, Schalter,
  Auswahl, Farbindex mit Vorschau, Control-Referenz, Notenliste). Eine neue
  Einstellung braucht danach einen Katalogeintrag statt einer neuen Svelte-Seite.
- **Geräte-Tab:** ASL-LED-Abschnitt mit allen `[led]`-Werten (Modus-, Fine- und
  Nipple-Taste, Noten, Farben, Helligkeiten, Kanäle, Gerät) inklusive
  Notenbesitz-Konflikten; je Geräteprofil das LED-Feedback (Protokoll, Noten,
  Takt).
- **Mapping-Tab:** Abschnitt „Screen-Modus & Encoder“ mit Toggle-Tasten,
  momentanem Modifier, Screen-Encoder-Zielen, Auflösung (Normal/Fine/Ultra und
  Modifier) sowie Beschleunigung.
- **Bindungen statt Magic Strings:** `mapping.screen_mode.momentary`,
  `led.fine_control` und `led.nipple_control` referenzieren Controls mit `auto`
  (bisheriges Verhalten), explizitem Control oder `none`.
- **Effektiver Modus im Status:** Der Status meldet festen und momentanen Modus
  getrennt sowie den effektiven Wert; die UI-Anzeige folgt dem effektiven.
- **BREAKING:** keine. Bestehende Konfigurationen bleiben gültig, weil `auto`
  die bisherigen Bindungen nachbildet.
- **Nicht enthalten:** neue Schreib-Endpunkte, Hardware-Testknopf für LED,
  frei definierbare LED-Protokolle, Drag-and-drop-Formulare, Import/Export oder
  eine generische Roh-JSON-Bearbeitung.

## Capabilities

### New Capabilities

- `config-catalog`: maschinenlesbare Beschreibung der editierbaren
  Konfigurationsfelder inklusive Grenzen, Defaults, Gruppen und
  Sichtbarkeitsregeln als gemeinsame Quelle für UI und Validierung.

### Modified Capabilities

- `config-ui`: generische, kataloggetriebene Einstellungsabschnitte im
  Geräte- und Mapping-Tab, Platzierung nach der Parity-Regel, Feldbezug und
  Vorschau.
- `encoder-control`: konfigurierbarer momentaner Screen-Modifier,
  konfigurierbare Fine-/Nipple-LED-Bindung und effektiver Modus im Status.

## Impact

- **Backend:** `ma2pi/config.py` (neue Bindungsfelder, Katalog, gemeinsame
  Grenzen), `ma2pi/web/__init__.py` (Endpoint), `ma2pi/web/serialize.py`,
  `ma2pi/mapping.py` (Modifier-Auflösung statt `SCREEN_ENCODER_MODIFIER`),
  `ma2pi/ma2_client.py` und `ma2pi/__main__.py` (LED-Bindungen, Status).
- **Frontend:** `web/src/lib/settings/` (Renderer, Feldkomponenten, Registry),
  `web/src/lib/api.ts`, `DevicesPage.svelte`, `MappingPage.svelte`.
- **Abhängigkeiten:** baut auf `mapping-device-feature-parity` (gemeinsamer
  Store, Feldbezug, Generation, `AssignmentDialog`) und
  `add-per-device-led-protocols` (Protokolle, Farbtabelle, Notenbesitz) auf;
  erst nach deren Archivierung anwenden.
- **Tests:** Katalog-Deckung gegen `parse_config`, Web-API-Tests, Vitest für
  Renderer und Abschnitte, Parity-Test für die Platzierung nach Scope.
- **Risiko:** Katalog und Parser können auseinanderlaufen; das verhindern
  Deckungs- und Grenzwert-Tests. Generische Formulare dürfen Sonderfälle
  (Secrets, Geräte-Abhängigkeiten) nicht verlieren.
