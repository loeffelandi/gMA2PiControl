# Proposal

## Why

Mapping- und Geräte-Tab haben sich auseinanderentwickelt: Der Mapping-Tab kennt
weder Bänke noch das Control-Inventar der MIDICRAFT-Geräte und kann keine
Bank-Ebene bearbeiten; der Geräte-Tab kann dafür keine Belegung löschen und
schreibt Bank-1-Änderungen am Layer vorbei. Dadurch muss der Benutzer wissen,
welcher Tab welche Änderung kann, und erhält je nach Tab unterschiedliche
Ergebnisse für dieselbe Belegung. Beide Tabs sollen zwei Sichten auf dasselbe
Zuweisungsmodell sein.

## What Changes

- Ein gemeinsames Zuweisungsmodell mit explizitem Scope (`global` oder
  `Gerät + Bank`) und sichtbarer Herkunft der effektiven Belegung (explizit,
  geerbt, geerbt mit Bank-Offset, Default).
- Beide Tabs bieten dieselben Aktionen: Hardkey, Command, Screen-Modus,
  Screen-Auswahl, Encoder-Klick, Playback-Ziel, Encoder-Ziel, Screen-Encoder,
  Modifier (Hardkey oder lokal) sowie **Belegung entfernen**.
- Der Mapping-Tab nutzt das vollständige Control-Inventar inklusive Bänken und
  zeigt die effektive Belegung samt Bank-Offset; der Geräte-Tab erhält Löschen,
  Global-Scope und eine korrekte Behandlung der Bank-1-Ebene.
- Ein gemeinsamer Zuweisungsdialog und ein gemeinsamer Konfigurationszustand:
  gleiche Aktion, gleicher Scope und gleiche Validierung ergeben in beiden Tabs
  exakt dieselbe Konfiguration; Änderungen erscheinen ohne Neuladen im anderen
  Tab.
- Schreibregeln werden vereinheitlicht: ungenutzte Felder werden ausdrücklich
  auf `null` gesetzt, Screen-Encoder-Einträge werden beim Wechsel geleert,
  geerbte Ziele werden nicht stillschweigend als explizite Overrides
  gespeichert.
- Zwei Lernwege mit klaren Zuständigkeiten: Control-Erkennung (Mapping) und
  Noten-Anlernen je Bank (Geräte); beide Tabs können den passenden Lernweg
  starten oder dorthin verlinken und zeigen einen gemeinsamen Status.
- Einheitlicher Gerätefilter (nur erkannte Geräte) und sichtbare
  Vorrangkonflikte zwischen Layer-Key, Playback und Modifier.
- **Nicht enthalten:** Änderungen der Laufzeitauflösung, ein neuer
  Schreib-Endpunkt, Drag-and-drop-Layouteditor, Import/Export oder Undo/Redo.
- **Keine Breaking Config-Änderungen:** bestehende Konfigurationen bleiben
  gültig; geändert wird die Bedienung und die Gleichheit der beiden Tabs.

## Capabilities

### New Capabilities

- keine

### Modified Capabilities

- `config-ui`: gemeinsames Zuweisungsmodell für Mapping- und Geräte-Tab,
  Scope und effektive Belegung, Löschen/Überschreiben, vollständiges
  Control-Inventar, gemeinsamer Dialog, Lernwege sowie einheitliche
  Validierung und Zustandsführung.

## Impact

- **Frontend:** neuer gemeinsamer Config-Store und ein reines
  Mapping-Modul (Resolve/Patch-Serialisierung); Refactoring von
  `MappingPage.svelte`, `DevicesPage.svelte` und `AssignDialog.svelte`;
  Wiederverwendung von `DeviceSurface`, Bank-Einstellungen und Learn-Panel;
  Typen in `web/src/lib/api.ts`.
- **Backend:** `PUT /api/config` bleibt der einzige Schreibpfad. Ergänzt werden
  `field` in Validierungsfehlern und eine Generations-/ETag-Angabe für
  veraltete Drafts. Die Laufzeitauflösung in `mapping.py`/`playback.py` bleibt
  unverändert und dient als Referenz für das Frontend-Modul.
- **Abhängigkeit:** baut auf `add-device-layout-visuals` auf (Bänke,
  Control-Inventar, Geräteflächen). Dieser Change sollte erst nach dessen
  Archivierung angewendet werden, damit die `config-ui`-Delta-Specs nicht
  übereinanderliegen. Der dort beschlossene Gerätefilter (nur erkannte Geräte)
  gilt auch hier.
- **Tests:** Golden-Tests für Resolver und Patch-Serialisierung sowie eine
  Parity-Matrix, die dieselbe Änderung aus beiden Tabs ausführt und identische
  Konfiguration und effektive Belegung erwartet.
- **Risiko:** RFC-7386-Merge, Bank-1-Ebene und Offset-Vererbung sind die
  fehleranfälligsten Stellen; sie werden durch explizite Patch-Regeln und
  gemeinsame Tests abgesichert.
