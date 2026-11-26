# Proposal

## Why

Geräte erscheinen im UI bisher nur als Tabellenzeilen, obwohl Cherry-Tastatur,
ASL-Controller und die MIDICRAFT-Modelle unregelmäßige, räumlich aufgebaute
Flächen sind. Wer eine Taste belegt, denkt in Reihen, Spalten und Aufklebern,
nicht in Scancodes. Bei den MIDICRAFT-Geräten kommen zwei Eigenheiten hinzu: Die
Noten sind am Gerät frei einstellbar, und ein Page-Wechsel ändert MIDI-Kanal und
Notenbelegung gemeinsam. Welche Bank gemeint ist, wählt der Benutzer beim
Anlernen und beim Mappen in der Oberfläche; der Kanal ordnet das Ereignis der
Bank zu.

## What Changes

- Neue Capability `device-layout`: Geräte werden als datengetriebenes Raster
  (Reihen, Spalten, Spannen, Labels, optionale Aufkleberfarbe) beschrieben und
  in der Oberfläche schematisch dargestellt.
- Neue Capability `device-banks`: Bis zu 16 Bänke je Profil, jeweils mit eigenem
  MIDI-Kanal und eigener Notenbelegung. Ein Page-Wechsel am Gerät ändert beides
  gemeinsam. Die Bank wird beim Lernen und beim Mappen in der UI gewählt; der
  Kanal ordnet das Ereignis der Bank zu. Ohne expliziten Eintrag verteilt ein
  konfigurierbarer Bank-Offset die Executor-Ziele auf derselben MA-Page; eine
  MA-Page-Bindung pro Bank bleibt optional.
- Neue Capability `device-learn`: Geführter Learn-Modus über die Gerätefläche.
  Die ungebundenen Controls der gewählten Bank werden in Layout-Reihenfolge
  durchlaufen; das physische Bedienen liefert die Note, die atomar ins Profil
  geschrieben wird. Damit sind die frei einstellbaren MIDICRAFT-Noten ohne
  Handarbeit erfassbar.
- Control-Inventar im Profil: physische Controls werden unabhängig von Noten
  deklariert, sodass Fläche und Learn-Modus auch vor dem ersten Anlernen
  vollständig sind.
- Mitgelieferte Layouts: Cherry G86-63400 im Layout des aktuellen Fotos, ASL
  MK2-E4B3 sowie alle sechs aktuellen MIDICRAFT-Modelle (`PUSH²`, `FADE²`,
  `TURN²`, `MIX²`, `ENC`, `SPOT`) mit ihren Control-Zahlen.
- Mehrfachzuweisung: mehrere Felder auswählen (Klick-Reihenfolge), Aktion und
  Startwert angeben; numerische Ziele wie Executor-Nummern werden fortlaufend
  verteilt (5 Tasten, Executor, Start 1 → 1–5).
- Encoder-Beschleunigung in der Geräteansicht: Der Zuweisungsdialog bietet für
  absolute Encoder mit Fader-Ziel denselben Schalter `accelerated`, den der
  Mapping-Editor verwendet.
- **Nicht enthalten:** LED-Feedback, PickUp, freier Drag-and-drop-Layouteditor,
  ASL-Modelle außer MK2-E4B3, MIDICRAFT-Vorgängerserie, MIDI-CC-Betrieb.
- **Abhängigkeit:** baut auf `add-midicraft-input` auf (absolute Werte,
  Executor-Ziele) und auf `add-value-acceleration` (Feld `accelerated` samt
  Backend-Validierung). Alle neuen Sektionen sind optional; bestehende
  Konfigurationen bleiben gültig.

## Capabilities

### New Capabilities

- `device-layout`: Schema, Validierung und API für schematische Geräteflächen,
  damit die Oberfläche Tastaturen und Controller als Raster darstellen und
  Felder ihren logischen Controls zuordnen kann.
- `device-banks`: Bank-Modell aus MIDI-Kanal und Notenbelegung, explizite
  Bankwahl im Editor, Bank-Offset und optionale MA-Page-Bindung.
- `device-learn`: Geführter Anlernmodus für die physische Control-Belegung
  inklusive Note, Fortschritt, Abbruch und atomarem Speichern.

### Modified Capabilities

- `hid-input`: Control-Inventar unabhängig von Noten, Bänke mit Notenbelegung,
  normalisierte Ereignisse mit Bank sowie Profile für die MIDICRAFT-Familie.
- `mapping-engine`: Auflösung in der Reihenfolge Bank-Ebene vor Bank-Offset vor
  globalem Mapping, inklusive gehaltener Tasten.
- `config-ui`: Geräteflächen mit Direktzuweisung, Bankauswahl,
  Mehrfachzuweisung, Bank-Einstellungen, Learn-Modus und
  Beschleunigungs-Schalter.

## Impact

- **Code:** `ma2pi/config.py` (Control-Inventar, Bänke, Layout, Mapping-Ebenen,
  `bank_size`, Validierung), `ma2pi/events.py` (Bank im Ereignis),
  `ma2pi/midi_input.py` (Kanal und Note liefern die Bank, Roh-Ereignisse für
  Learn), `ma2pi/mapping.py` (Bank-Auflösung und Offset), neuer Learn-Zustand
  im Daemon, `ma2pi/web/` (Geräte-API, Learn-Endpunkte), `web/src/App.svelte`
  und neue Komponenten für Fläche, Auswahl, Zuweisungsdialog und Learn-Modus.
  Der Beschleunigungs-Schalter nutzt das Feld `accelerated` aus
  `add-value-acceleration`.
- **Daten:** `config.toml` erhält `[layouts.*]`, Profil-Bänke, Control-Inventar,
  `[mapping.device_banks.*]` und `bank_size`; bestehende Profile werden als
  Bank 1 abgeleitet.
- **Dokumentation:** README-Konfigurationsreferenz und Learn-Anleitung; ADR
  (Proposed) für Bänke als Editorzustand und Bank-Offset.
- **Abhängigkeiten:** keine neuen Laufzeitabhängigkeiten.
- **Risiko:** Die Noten der MIDICRAFT-Modelle sind gerätespezifisch und werden
  erst durch den Learn-Modus bekannt; mitgelieferte Profile starten deshalb mit
  Inventar und ohne Noten. Die Kanäle müssen je Profil eindeutig sein, weil sie
  die Bank bestimmen; Noten dürfen sich zwischen Bänken wiederholen.
