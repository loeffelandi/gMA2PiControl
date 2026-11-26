# Tasks

## 1. Gemeinsames Zuweisungsmodell

- [ ] 1.1 Typen für `Assignment`, `Scope` und `AssignmentSource` anlegen und den Resolver für globale Ebene, Bank-Ebene, Vererbung, Bank-Offset und Default implementieren; Golden-Tests decken alle fünf Quellen ab.
- [ ] 1.2 Patch-Builder für Keys und Playbacks implementieren, der ungenutzte Aktionsfelder ausdrücklich auf `null` setzt; Tests für Hardkey→Command, Command→Screen, Button→Fader und Löschen.
- [ ] 1.3 Patch-Builder für Encoder und Screen-Encoder implementieren: vollständige `mapping.encoders`-Liste, `null` für entfernte Screen-Slots und Wechsel Slot/Attribut; Tests prüfen die erzeugten Patches.
- [ ] 1.4 Bank-Einstellungen und Bank-1-Layer im Modell abbilden: vorhandener Layer gewinnt, sonst global; Offset bleibt geerbt; Tests für Bank 1 mit und ohne Layer, Bank 2 mit Offset und MA-Page.
- [ ] 1.5 Golden-Fixtures zwischen Frontend-Resolver und `mapping.py`/`playback.py` abgleichen; ein Test bricht bei abweichender effektiver Belegung ab.
- [ ] 1.6 ADR mit Status `Proposed` für das gemeinsame Zuweisungsmodell, Scope und Resolver anlegen und mit ADR 0022 verlinken; Datei und ADR-Index prüfen.

## 2. Gemeinsamer Konfigurationszustand

- [ ] 2.1 Config-Store in `App.svelte` erzeugen und beiden Tabs übergeben; beide Tabs laden und speichern nur noch über den Store. Test: eine Änderung im Store ist in beiden Tabs sichtbar.
- [ ] 2.2 Generation/ETag zu `GET /api/config` und zum `PUT`-Ergebnis ergänzen; Client speichert die Generation und sendet sie beim Schreiben mit. API-Tests für gültige und veraltete Generation.
- [ ] 2.3 `field` in Validierungsfehlern der Config-API ergänzen und im Store an das betroffene Feld weiterreichen; Test prüft die Feldzuordnung für Page, Executor und Screen-Encoder.
- [ ] 2.4 Konfliktbehandlung bei veraltetem Entwurf implementieren: Speichern meldet den Konflikt, bietet Neuladen oder Verwerfen an und überschreibt nichts; Komponententest mit zwei Store-Instanzen.

## 3. Gemeinsamer Zuweisungsdialog

- [ ] 3.1 `AssignmentDialog` aus dem bestehenden Dialog ableiten und alle Aktionen anbieten: Hardkey, Command, Screen-Modus, Screen-Auswahl, Encoder-Klick, Playback, Encoder-Ziel, Screen-Encoder, Modifier (Hardkey/lokal) und „Belegung entfernen“; Komponententest je Aktion.
- [ ] 3.2 Scope-Auswahl (global / diese Bank) mit Herkunftsanzeige und bewusstem Override ergänzen; Test: geerbtes Ziel wird nicht automatisch explizit gespeichert.
- [ ] 3.3 Screen-Encoder-Slot auf 1–4 begrenzen, Ziel 5–10 validieren und Leeren unterstützen; Test für Wechsel zu Attribut, anderen Slot und „keiner“.
- [ ] 3.4 Feldbezogene Backend-Fehler im Dialog anzeigen und die bisherige Konfiguration behalten; Test mit abgelehntem Executor und ungültigem Screen-Encoder.

## 4. Mapping-Tab auf Parität bringen

- [ ] 4.1 Control-Auswahl auf das vollständige Inventar inklusive Noten, absoluten Werten, Encodern und Bänken umstellen; Test: MIDICRAFT-Fader aus Inventar und Banknoten erscheinen im Mapping-Tab.
- [ ] 4.2 Bank-Scope im Mapping-Tab anbieten und die effektive Belegung samt Herkunft und Offset anzeigen; Test: Bank 2 zeigt Executor 6 als geerbt mit Offset.
- [ ] 4.3 Löschen, Überschreiben und Aktionswechsel über den gemeinsamen Dialog und Serializer ermöglichen; Tests prüfen entfernten Bank-Override, entfernten globalen Eintrag und Hardkey→Command.
- [ ] 4.4 Beschleunigungs-Checkbox aus dem Inventar statt aus `midi_values` ableiten; Test: Inventar-Encoder mit `accelerated = true` zeigt die aktive Checkbox.

## 5. Geräte-Tab auf Parität bringen

- [ ] 5.1 Geräte-Tab auf gemeinsamen Store und Dialog umstellen, globalen Scope und Löschen anbieten; Test: Löschen im Geräte-Tab entfernt die Belegung auch im Mapping-Tab.
- [ ] 5.2 Bank-1-Layer korrekt bearbeiten: vorhandenen Layer ändern statt global daneben zu schreiben; Test mit bestehendem Bank-1-Override.
- [ ] 5.3 Screen-Encoder beim Wechsel leeren und geerbte Ziele nicht als explizit speichern; Tests für Attributwechsel, Slotwechsel und Offset-Vererbung.
- [ ] 5.4 Bank-Einstellungen in eine gemeinsame Komponente ziehen und im Mapping-Tab read-only anzeigen; Test prüft gleiche Werte in beiden Tabs.

## 6. Lernwege vereinheitlichen

- [ ] 6.1 Lernstatus im gemeinsamen Store zusammenführen und `learn`- sowie `device_learn`-Events über den bestehenden WebSocket verarbeiten; Polling im Learn-Panel entfernen und Test für Event-Aktualisierung.
- [ ] 6.2 Noten-Anlernen aus dem Mapping-Tab für Gerät und Bank starten oder dorthin verlinken; Test prüft Start, Fortschritt und Rücksprung.
- [ ] 6.3 Control-Erkennung aus dem Geräte-Tab starten und das Ergebnis in beiden Tabs anzeigen; Test mit simuliertem Lern-Event.
- [ ] 6.4 Timeout und Abbruch setzen den Lernstatus in beiden Tabs zurück; Test prüft wieder bedienbare Schaltflächen und unveränderte Konfiguration.

## 7. Geräteauswahl und Vorrang

- [ ] 7.1 Beide Tabs auf dieselbe Menge erkannter Geräte filtern und Gerät/Bank im Store halten; Test: nicht erkanntes Gerät fehlt in beiden Tabs, Auswahl bleibt beim Tab-Wechsel erhalten.
- [ ] 7.2 Vorrangberechnung (Layer-Key vor Playback vor Modifier/globalem Key) im Store implementieren und Konflikte in beiden Tabs kennzeichnen; Test mit gleichzeitigem Layer-Key und Playback-Ziel.
- [ ] 7.3 Konfliktbadge mit Erklärung und den beteiligten Ebenen anzeigen; Komponententest prüft Badge und Text.

## 8. Integration und Abnahme

- [ ] 8.1 Parity-Matrix als Test anlegen: jede Aktion in beiden Tabs mit gleichem Control und Scope ausführen und identische Konfiguration sowie effektive Belegung erwarten.
- [ ] 8.2 Vollständige Suite ausführen: `pytest`, in `web/` `npm run check`, `npm run test`, `npm run check:offline` und `npm run build`; `openspec validate mapping-device-feature-parity --strict` muss fehlerfrei durchlaufen.
- [ ] 8.3 README um das gemeinsame Zuweisungsmodell, Scope/Herkunft, Löschen und die zwei Lernwege ergänzen; die beschriebenen Schritte müssen der Oberfläche entsprechen.
- [ ] 8.4 Hardware-Smoke-Test auf dem Pi: dieselbe Belegung aus beiden Tabs speichern, Bank wechseln, Offset prüfen und eine Belegung löschen; Ergebnis im Change dokumentieren.

## Workflow follow-up

- Diesen Change erst anwenden, nachdem `add-device-layout-visuals` archiviert und die dortigen Delta-Specs in `openspec/specs/config-ui/spec.md` übernommen wurden.
- Nach bestandener Abnahme archivieren und die `config-ui`-Delta-Specs synchronisieren.
