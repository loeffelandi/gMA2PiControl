# Proposal

## Why

Mapping- und Geräte-Tab haben sich auseinanderentwickelt. Die Review-Changes
`fix-code-review-findings` und `fix-review-followup-findings` haben einzelne
Lücken geschlossen (siehe „Bereits umgesetzt“), die strukturelle Trennung
besteht aber fort:

- Der Mapping-Tab arbeitet mit einer eigenen Tabelle statt mit
  `AssignDialog`, kennt keinen Bank-Scope, zeigt keine Herkunft oder
  Bank-Offsets und liest `transport` von Playback-Zielen nicht.
- Der Geräte-Tab schreibt bei Bank 1 immer in die globale Ebene, auch wenn für
  Bank 1 ein Layer-Eintrag existiert, und bietet keinen gezielten globalen
  Scope für Tasten und Encoder.
- Jeder Tab lädt die Konfiguration selbst; es gibt weder gemeinsamen Zustand
  noch Erkennung veralteter Entwürfe, und `PUT /api/config` liefert bei
  Validierungsfehlern kein `field`.
- Lernen läuft über zwei getrennte Wege mit je eigenem Status, das Learn-Panel
  pollt.

Dadurch muss der Benutzer wissen, welcher Tab welche Änderung kann, und erhält
je nach Tab unterschiedliche Ergebnisse für dieselbe Belegung. Beide Tabs sollen
zwei Sichten auf dasselbe Zuweisungsmodell sein.

### Bereits umgesetzt (nicht Teil dieses Changes)

- Abgelöste Variantenfelder werden im Mapping-Tab mit `null` gelöscht;
  Inventar, Bänke und die `accelerated`-Option stehen dort zur Verfügung
  (Haupt-Spec „Vollständige Merge-Patches und Inventar im Mapping-Editor“).
- `AssignDialog` kann Zuweisungen entfernen (`onClear`), „Kein Screen-Encoder“
  speichern, Screen-Encoder je Slot aktualisieren und per `Escape` schließen;
  der Geräte-Tab nutzt das (`clearAssignment`).
- Beide Tabs zeigen nur erkannte Geräte.
- Das Learn-Ergebnis wird im Mapping-Tab dedupliziert.

Dieser Change bringt diese Teillösungen unter ein gemeinsames Modell und füllt
die verbleibenden Lücken.

## What Changes

- Ein gemeinsames Zuweisungsmodell mit explizitem Scope (`global` oder
  `Gerät + Bank`) und sichtbarer Herkunft der effektiven Belegung (explizit,
  geerbt, geerbt mit Bank-Offset, Default).
- Beide Tabs bieten dieselben Aktionen: Hardkey, Command, Screen-Modus,
  Screen-Auswahl, Encoder-Klick, Playback-Ziel (einschließlich `transport`),
  Encoder-Ziel, Screen-Encoder, Modifier (Hardkey oder lokal) sowie
  **Belegung entfernen**.
- Der Mapping-Tab erhält Bank-Scope und zeigt die effektive Belegung samt
  Herkunft und Bank-Offset; der Geräte-Tab erhält einen gezielten globalen
  Scope und eine korrekte Behandlung der Bank-1-Ebene.
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
  Ebenfalls nicht enthalten ist die Executor-Topologie (breite Executoren,
  `resolve-combined-executors`): Resolver und Anzeige zeigen das
  **konfigurierte** Ziel, nicht das zur Laufzeit umgeleitete.
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
  `field` in Validierungsfehlern (abgeleitet aus `ConfigError.path`; heute
  liefert `_apply_error` nur `validation_error` mit Text) und eine
  Generations-/ETag-Angabe für veraltete Drafts. Die Laufzeitauflösung in
  `mapping.py`/`playback.py` bleibt unverändert und dient als Referenz für das
  Frontend-Modul.
- **Abhängigkeiten:** `add-device-layout-visuals` (Bänke, Control-Inventar,
  Geräteflächen, Gerätefilter „nur erkannte Geräte“) und
  `add-midi-remote-executors` (`transport` je Playback-Ziel) sind archiviert und
  in `openspec/specs` übernommen; es gibt keine Anwendungssperre mehr.
- **Reihenfolge zu anderen aktiven Changes:** `encoder-mode-led-ui` fordert in
  „Platzierung nach Scope und Parity-Regel“ denselben Zustand und Schreibpfad
  in beiden Tabs und soll auf dem hier eingeführten Config-Store aufbauen;
  dieser Change wird zuerst angewendet. `add-device-activity-leds` und
  `device-profile-files` berühren den Zuweisungspfad nicht (Letzteres ändert nur
  die Ablage der Profile, die API bleibt gleich).
- **Tests:** Golden-Tests für Resolver und Patch-Serialisierung sowie eine
  Parity-Matrix, die dieselbe Änderung aus beiden Tabs ausführt und identische
  Konfiguration und effektive Belegung erwartet.
- **Risiko:** RFC-7386-Merge, Bank-1-Ebene und Offset-Vererbung sind die
  fehleranfälligsten Stellen; sie werden durch explizite Patch-Regeln und
  gemeinsame Tests abgesichert.
