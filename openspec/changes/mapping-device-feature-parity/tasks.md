# Tasks

## 1. Gemeinsames Zuweisungsmodell

- [x] 1.1 Typen für `Assignment`, `Scope` und `AssignmentSource` anlegen und den Resolver für globale Ebene, Bank-Ebene, Vererbung, Bank-Offset und Default implementieren; Golden-Tests decken alle fünf Quellen ab. Der Resolver liefert das konfigurierte Ziel und bildet die Executor-Topologie (breite Executoren) bewusst nicht ab.
- [x] 1.2 Patch-Builder für Keys und Playbacks implementieren, der ungenutzte Aktionsfelder ausdrücklich auf `null` setzt, einschließlich `transport` (nur bei Button-Zielen, sonst `null`); Tests für Hardkey→Command, Command→Screen, Button→Fader (mit und ohne `transport = "midi"`) und Löschen. Die bestehende `null`-Logik der Review-Changes in `MappingPage`/`DevicesPage` wird übernommen und dort entfernt.
- [x] 1.3 Patch-Builder für Encoder und Screen-Encoder implementieren: vollständige `mapping.encoders`-Liste, `null` für entfernte Screen-Slots und Wechsel Slot/Attribut; Tests prüfen die erzeugten Patches.
- [x] 1.4 Bank-Einstellungen und Bank-1-Layer im Modell abbilden: vorhandener Layer gewinnt, sonst global; Offset bleibt geerbt; Tests für Bank 1 mit und ohne Layer, Bank 2 mit Offset und MA-Page.
- [x] 1.5 Golden-Fixtures zwischen Frontend-Resolver und `mapping.py`/`playback.py` abgleichen; ein Test bricht bei abweichender effektiver Belegung ab.
- [x] 1.6 ADR mit Status `Proposed` für das gemeinsame Zuweisungsmodell, Scope und Resolver mit `adr new` unter der nächsten freien Nummer anlegen (0024 ist belegt; 0024/0025 sind in `modularize-backend-packages` und `device-profile-files` angekündigt – Nummer erst beim Anlegen vergeben) und mit ADR 0022 und 0024 verlinken; Datei und ADR-Index prüfen.

## 2. Gemeinsamer Konfigurationszustand

- [x] 2.1 Config-Store in `App.svelte` erzeugen und beiden Tabs übergeben; beide Tabs laden und speichern nur noch über den Store. Test: eine Änderung im Store ist in beiden Tabs sichtbar.
- [x] 2.2 Generation/ETag zu `GET /api/config` und zum `PUT`-Ergebnis ergänzen; Client speichert die Generation und sendet sie beim Schreiben mit. API-Tests für gültige und veraltete Generation.
- [x] 2.3 `field` in Validierungsfehlern von `PUT /api/config` ergänzen (aus `ConfigError.path` in `_apply_error`; heute nur `validation_error` mit Text) und im Store an das betroffene Feld weiterreichen; Tests prüfen die Feldzuordnung für Page, Executor, Transport und Screen-Encoder.
- [x] 2.4 Konfliktbehandlung bei veraltetem Entwurf implementieren: Speichern meldet den Konflikt, bietet Neuladen oder Verwerfen an und überschreibt nichts; Komponententest mit zwei Store-Instanzen.

## 3. Gemeinsamer Zuweisungsdialog

- [x] 3.1 `AssignmentDialog` aus dem bestehenden `AssignDialog` ableiten (Entfernen, `transport` und Slot-Handling sind vorhanden) und alle Aktionen anbieten: Hardkey, Command, Screen-Modus, Screen-Auswahl, Encoder-Klick, Playback inklusive Transport, Encoder-Ziel, Screen-Encoder, Modifier (Hardkey/lokal) und „Belegung entfernen“; Komponententest je Aktion.
- [x] 3.2 Scope-Auswahl (global / diese Bank) mit Herkunftsanzeige und bewusstem Override ergänzen; Test: geerbtes Ziel wird nicht automatisch explizit gespeichert.
- [x] 3.3 Screen-Encoder-Slot 1–4, Ziel 5–10 und Leeren über das gemeinsame Modell führen (Dialog-Verhalten existiert seit `fix-review-followup-findings`); Tests für Wechsel zu Attribut, anderen Slot und „keiner“ laufen gegen den Serializer statt gegen Tab-Code.
- [x] 3.4 Feldbezogene Backend-Fehler im Dialog anzeigen und die bisherige Konfiguration behalten; Test mit abgelehntem Executor und ungültigem Screen-Encoder.

## 4. Mapping-Tab auf Parität bringen

- [x] 4.1 Control-Auswahl des Mapping-Tabs auf dieselbe gemeinsame Quelle wie der Geräte-Tab umstellen (Inventar, Noten, absolute Werte, Encoder, Bänke sind dort seit den Review-Changes vorhanden); Regressionstest: MIDICRAFT-Fader aus Inventar und Banknoten erscheinen in beiden Tabs.
- [x] 4.2 Bank-Scope im Mapping-Tab anbieten und die effektive Belegung samt Herkunft und Offset anzeigen; Test: Bank 2 zeigt Executor 6 als geerbt mit Offset.
- [x] 4.3 Löschen, Überschreiben und Aktionswechsel über den gemeinsamen Dialog und Serializer ermöglichen; Tests prüfen entfernten Bank-Override, entfernten globalen Eintrag und Hardkey→Command.
- [x] 4.4 Beschleunigungs-Checkbox und `transport` des Mapping-Tabs über das gemeinsame Modell lesen und schreiben (die Checkbox kommt bereits aus dem Inventar); Tests: Inventar-Encoder mit `accelerated = true` zeigt in beiden Tabs die aktive Checkbox, ein Button-Ziel mit `transport = "midi"` erscheint in beiden Tabs gleich.

## 5. Geräte-Tab auf Parität bringen

- [x] 5.1 Geräte-Tab auf gemeinsamen Store und Dialog umstellen und gezielten globalen Scope für Tasten und Encoder anbieten (Löschen über `clearAssignment` existiert bereits und wird auf den gemeinsamen Serializer umgestellt); Test: Löschen im Geräte-Tab entfernt die Belegung auch im Mapping-Tab.
- [x] 5.2 Bank-1-Layer korrekt bearbeiten: `useGlobalScope = bank === 1` in `DevicesPage` durch die Layer-Erkennung des Modells ersetzen, sodass ein vorhandener Layer geändert statt global daneben geschrieben wird; Test mit bestehendem Bank-1-Override und ohne.
- [x] 5.3 Screen-Encoder beim Wechsel leeren und geerbte Ziele nicht als explizit speichern; Tests für Attributwechsel, Slotwechsel und Offset-Vererbung.
- [x] 5.4 Bank-Einstellungen in eine gemeinsame Komponente ziehen und im Mapping-Tab read-only anzeigen; Test prüft gleiche Werte in beiden Tabs.

## 6. Lernwege vereinheitlichen

- [x] 6.1 Lernstatus im gemeinsamen Store zusammenführen und `learn`- sowie `device_learn`-Events über den bestehenden WebSocket verarbeiten; Polling im Learn-Panel entfernen und Test für Event-Aktualisierung.
- [x] 6.2 Noten-Anlernen aus dem Mapping-Tab für Gerät und Bank starten oder dorthin verlinken; Test prüft Start, Fortschritt und Rücksprung.
- [x] 6.3 Control-Erkennung aus dem Geräte-Tab starten und das Ergebnis in beiden Tabs anzeigen; Test mit simuliertem Lern-Event.
- [x] 6.4 Timeout und Abbruch setzen den Lernstatus in beiden Tabs zurück; Test prüft wieder bedienbare Schaltflächen und unveränderte Konfiguration.

## 7. Geräteauswahl und Vorrang

- [x] 7.1 Gerät und Bank im Store halten (der Filter auf erkannte Geräte ist in beiden Tabs bereits umgesetzt und wird in den Store verschoben); Test: nicht erkanntes Gerät fehlt in beiden Tabs, Auswahl bleibt beim Tab-Wechsel erhalten und wird verworfen, wenn das Gerät verschwindet.
- [x] 7.2 Vorrangberechnung analog zu `PlaybackRouter.handle` im Store implementieren (Layer-Key vor Playback bei Tastenereignissen, Playback vor globalem Key und Modifier, kein Layer-Key-Konflikt bei Wert-/Encoder-Controls) und Konflikte in beiden Tabs kennzeichnen; Tests mit gleichzeitigem Layer-Key und Playback-Ziel, Playback gegen globalen Key und einem Encoder mit Playback-Ziel.
- [x] 7.3 Konfliktbadge mit Erklärung und den beteiligten Ebenen anzeigen; Komponententest prüft Badge und Text.

## 8. Integration und Abnahme

- [x] 8.1 Parity-Matrix als Test anlegen: jede Aktion (inklusive Playback-Transport und Beschleunigung) in beiden Tabs mit gleichem Control und Scope ausführen und identische Konfiguration sowie effektive Belegung erwarten.
- [x] 8.2 Vollständige Suite ausführen: `pytest`, in `web/` `npm run check`, `npm run test`, `npm run check:offline` und `npm run build`; `openspec validate mapping-device-feature-parity --strict` muss fehlerfrei durchlaufen.
- [x] 8.3 README um das gemeinsame Zuweisungsmodell, Scope/Herkunft, Löschen und die zwei Lernwege ergänzen; die beschriebenen Schritte müssen der Oberfläche entsprechen.
- [ ] 8.4 Hardware-Smoke-Test auf dem Pi: dieselbe Belegung aus beiden Tabs speichern, Bank wechseln, Offset prüfen und eine Belegung löschen; Ergebnis im Change dokumentieren.
  Offen, nur am Pi ausführbar. Checkliste für den Lauf (Ergebnis hier eintragen):
  1. Geräte-Tab, Bank 2: Playback-Ziel „Nur diese Bank“ speichern; Mapping-Tab zeigt „Bank-Eintrag“.
  2. Mapping-Tab, Bank 2: dasselbe Control global speichern; Geräte-Tab zeigt „geerbt mit Bank-Offset“.
  3. Bank wechseln und am Gerät bedienen: Executor = globaler Wert + (Bank − 1) × Bankgröße.
  4. Bank-Eintrag entfernen: Bank fällt auf das geerbte Ziel zurück; globalen Eintrag entfernen: Control ist frei.
  5. „Noten anlernen“ im Mapping-Tab starten, am Gerät bedienen, im Geräte-Tab speichern.

## Workflow follow-up

- `add-device-layout-visuals` und `add-midi-remote-executors` sind archiviert und in `openspec/specs` übernommen; es gibt keine Anwendungssperre mehr.
- Reihenfolge: diesen Change vor `encoder-mode-led-ui` anwenden, dessen Abschnitte den hier eingeführten Config-Store nutzen sollen.
- Nach bestandener Abnahme archivieren und die `config-ui`-Delta-Specs synchronisieren.
