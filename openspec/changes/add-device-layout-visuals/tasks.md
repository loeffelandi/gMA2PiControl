# Tasks

## 1. Konfigurationsschema und Validierung

- [x] 1.1 `DeviceLayout`/`LayoutCell` mit `columns`, `rows`, `label`, `control`, `col_span`, `row_span`, `color` und `profile`-Referenz in `config.py` implementieren; Tests für gültige Layouts, unbekanntes Profil, unbekanntes Control, doppeltes Control und ungültige Spannen in `tests/test_config.py`.
- [x] 1.2 Control-Inventar (`id`, `kind`, `label`) und Bänke (`number`, `channel`, `notes`) parsen, Altprofile aus `notes`/`midi_encoders`/`midi_values` als Bank 1 auf Kanal 1 ableiten und ungebundene Controls zulassen; Tests für Inventar ohne Noten, Altprofil und unbekannten Control.
- [x] 1.3 Bank-Validierung ergänzen: Nummer und Kanal je 1–16, Kanäle je Profil eindeutig, Kanal-Default gleich Banknummer, Noten je Bank eindeutig (gleiche Note auf anderem Kanal erlaubt); ablehnende Tests für jede Regel.
- [x] 1.4 `[mapping.device_banks.<device>]` mit `bank_size` sowie `[mapping.device_banks.<device>.<bank>]` mit `ma_page` und Overrides für Tasten, Encoder und Playbacks parsen und gegen Gerät, Bank und Control validieren; Tests für gültige Ebene, unbekannte Bank, unbekanntes Control, `bank_size = 0` und ungültige `ma_page`.
- [x] 1.5 Globale Eindeutigkeit der Control-Namen über alle Profile erzwingen, inklusive der MIDICRAFT-Präfixe; Tests für Kollision und parallele Modelle.
- [x] 1.6 README-Konfigurationsreferenz um `[layouts.*]`, Control-Inventar, Bänke, `[mapping.device_banks.*]` und `bank_size` ergänzen; `python -m ma2pi --config config.toml --check-config` muss die Beispielkonfiguration fehlerfrei prüfen.

## 2. Bankzuordnung und Eingabe

- [x] 2.1 `InputEvent` um `bank` mit Default 1 erweitern und in `midi_input` den MIDI-Kanal des Geräts der Bank und die Note dem Control zuordnen; Tests für Taste, Encoder, Wert, unbekannten Kanal, unbekannte Note und Geräte ohne Bänke in `tests/test_midi_input.py`.
- [x] 2.2 Kanäle je Profil auf Bänke und Noten innerhalb der Bank auf Controls auflösen; unbekannte Kombinationen einmalig protokollieren und prüfen, dass dieselbe Note auf einem anderen Bank-Kanal korrekt getrennt wird.
- [x] 2.3 Roh-Ereignisse für den Learn-Modus bereitstellen, ohne sie zu normalisieren oder zu mappen; Test prüft, dass ein Learn-Ereignis keinen Frame erzeugt.
- [x] 2.4 `--dump-input` um Bank und Note ergänzen und im README dokumentieren; Test prüft die Ausgabe für eine Note aus Bank 2.

## 3. Learn-Modus

- [x] 3.1 Learn-Zustand und -Ablauf im Daemon implementieren: Start für Gerät und gewählte Bank, erwarteter Kanal, Liste ungebundener Controls in Layout-Reihenfolge, aktives Control, Fortschritt, Überspringen, Timeout-Pause, Abbruch; Tests für Reihenfolge, Überspringen, Timeout, fehlende Bank und zweiten Start.
- [x] 3.2 Ereignisübernahme im Learn-Modus: nächstes Ereignis auf dem Bank-Kanal dem aktiven Control zuordnen, falschen Kanal ablehnen, doppelte Note innerhalb der Bank ablehnen, Note und Art übernehmen; Tests für alle Fälle inklusive gleicher Note auf anderem Kanal.
- [x] 3.3 Geräteverlust und Reconnect während einer Sitzung: pausieren, Zustand behalten, am aktiven Control fortsetzen; Test mit `FakeMidiSource`.
- [x] 3.4 Abschluss schreibt die gelernten Noten atomar über den bestehenden Konfigurationspfad; Tests für erfolgreiches Speichern, Validierungsfehler ohne Teiländerung und Re-Learn eines gebundenen Controls.
- [x] 3.5 Learn-Endpunkte in der Web-API bereitstellen (Start, Status/Aktualisierung, Überspringen, Abbrechen, Abschluss) inklusive PIN-Schutz und Konflikt bei laufender Sitzung; Tests in `tests/test_web.py` oder `tests/test_learn_api.py`.

## 4. Mapping-Auflösung

- [x] 4.1 Auflösung Bank-Ebene → Bank-Offset → globales Mapping in `mapping.py` implementieren; Tests für expliziten Eintrag, vererbten Executor in Bank 2/3, Button-Nummer unverändert und Nicht-Executor-Ziele ohne Offset in `tests/test_mapping.py`.
- [x] 4.2 Bank-Offset bei hinterlegter MA-Page abschalten und `Page <n>` beim ersten Ereignis einer anderen Bank einmalig senden; Tests für einmaliges Senden, fehlende Bindung und Fehlschlag ohne Eingabeblockade.
- [x] 4.3 Gehaltene Tasten und Modifier an ihre Press-Bank binden; Tests für Release nach Bankwechsel und gehaltenen Modifier über einen Wechsel.

## 5. API

- [x] 5.1 `GET /api/devices` um Layout, Control-Inventar, verfügbare Bänke und `bank_size` je Gerät erweitern; Tests mit und ohne Layout, mit mehreren Bänken und für ungebundene Controls in `tests/test_web_devices.py`.
- [x] 5.2 `GET /api/config` um Layouts, Inventar, Bänke und Mapping-Ebenen ergänzen und `PUT /api/config` atomar validieren; Tests für Struktur, Secret-Redaktion und abgelehnte Teiländerungen in `tests/test_config_api.py`.

## 6. Oberfläche

- [x] 6.1 Typen in `web/src/lib/api.ts` um Layout, Inventar, Bänke, `bank_size` und Learn-Status erweitern; `npm run check` im Verzeichnis `web/` läuft fehlerfrei.
- [x] 6.2 `DeviceSurface`-Komponente mit CSS Grid, Spannen, Palettenfarben, Labels und klickbaren Zellen implementieren; Komponententest prüft Spannen, Farben und Klick auf eine Zelle.
- [x] 6.3 Geräte-Seite in `App.svelte` auf die Flächenansicht umstellen, Tabellen-Fallback einbauen und nicht angeschlossene Geräte ausblenden; Test prüft Fallback und Filter.
- [x] 6.4 Bankauswahl im Editor: Bänke aus der API, reine Editorauswahl ohne Hardware- oder MA-Wirkung, keine Anzeige einer „aktiven“ Bank; Komponententest prüft Auswahl und Wirkungslosigkeit.
- [x] 6.5 `AssignDialog` für Einzelzuweisung (Hardkey, Command, Executor-Button, Executor-Fader) implementieren und über `PUT /api/config` speichern; Test prüft Erfolg und Fehlermeldung mit Gerät, Bank und Control.
- [x] 6.6 Mehrfachauswahl in Klick-Reihenfolge mit sichtbarer Nummerierung und Verteilungsdialog (Startwert, Schrittweite, Vorschau) implementieren; Test prüft Executor 1–5, Schrittweite 5 und atomaren Fehlschlag.
- [x] 6.7 `LearnPanel` implementieren: Bankwahl, Start, hervorgehobenes Control, Fortschritt, Überspringen, Abbrechen, Abschluss; Komponententest prüft geführten Ablauf und Abbruch ohne Speicherung.
- [x] 6.8 Bank-Einstellungen im Editor (Bankgröße je Gerät, Kanal und MA-Page je Bank) mit Feldvalidierung ergänzen; Test prüft Default, Änderung und Ablehnung von 0 beziehungsweise Kanal außerhalb 1–16.
- [x] 6.9 README-Abschnitte zu Gerätefläche, Mehrfachzuweisung und Learn-Modus ergänzen; die beschriebenen Schritte müssen der Oberfläche entsprechen.
- [x] 6.10 Beschleunigungs-Schalter im Zuweisungsdialog und bei Mehrfachzuweisung ergänzen: sichtbar nur für absolute Encoder mit Fader-Ziel, liest und schreibt `accelerated` des effektiven Ziels, legt bei Bedarf einen Eintrag der Bank-Ebene an; Tests für Sichtbarkeit, Bank-Ebene, Mehrfachzuweisung und abgelehnte Kombination. Setzt `add-value-acceleration` voraus.

## 7. Mitgelieferte Layouts

- [x] 7.1 Cherry-G86-Layout aus `cherry-layout-small.png` als `[layouts.cherry]` abbilden: alle Labels, Aufkleberfarben und Spannen für `Pause`, `Go+`, `Go-`, `Store`, `Please`; Test prüft Reihenzahl, Stichproben und große Tasten.
- [x] 7.2 ASL-MK2-E4B3-Layout als `[layouts.asl]` abbilden (vier Encoder, vier Clicks, drei Tasten); Test prüft `encoder.1`–`encoder.4` und die Tasten-Controls.
- [x] 7.3 Layouts für `PUSH²`, `FADE²`, `TURN²`, `MIX²`, `ENC` und `SPOT` anlegen; je Modell prüft ein Test die dokumentierte Control-Anzahl und die Zuordnung.
- [x] 7.4 README um die Liste der mitgelieferten Layouts und ihre Profilzuordnung ergänzen.

## 8. MIDICRAFT-Profile

- [x] 8.1 Profile mit Control-Inventar und 16 Bänken für alle sechs Modelle anlegen; Geräte-Einträge mit Vendor-ID `0x04d8`, Wildcard-Product-ID und Namensfilter ergänzen; `--check-config` und Tests für Inventar und Präfixe ausführen.
- [x] 8.2 Bank-2-Belegung des ENC als Beispiel dokumentieren (Encoder-Klick Note 0, Fader Note 15) und im README erläutern; Test prüft die Erkennung dieser Belegung nach dem Lernen.
- [x] 8.3 README-Tabelle mit Modellen, Control-Zahlen, Namenspräfixen, Bank-Default und Learn-Ablauf ergänzen.

## 9. Architektur, Integration und Abnahme

- [x] 9.1 ADR mit Status `Proposed` für Bänke als Editorzustand und Bank-Offset anlegen (`adr new`), Kontext/Entscheidung/Konsequenzen/Alternativen eintragen und mit ADR 0014/0019 verlinken; Datei und Index prüfen.
- [x] 9.2 Vollständige Suite ausführen: `pytest`, in `web/` `npm run check`, `npm run test`, `npm run check:offline` und `npm run build`; `openspec validate add-device-layout-visuals --strict` muss ohne Fehler durchlaufen.
- [ ] 9.3 Hardware-Abnahme am Pi: Cherry-Layout gegen die echte Tastatur prüfen, Learn-Modus je MIDICRAFT-Gerät und Bank durchlaufen, Bank wechseln, Bank-Offset und Mehrfachzuweisung prüfen; Ergebnis in `verification.md` festhalten.
- [ ] 9.4 Cherry-Scancodes gegen die bedruckten Labels abgleichen (offener Punkt aus `add-ma2pi-core`) und Abweichungen im Layout oder Profil korrigieren.

## Workflow follow-up

- Change nach bestandener Hardware-Abnahme archivieren und die Delta-Specs in die Haupt-Specs übernehmen.
- LED-Feedback und PickUp bleiben eigenständige Changes.
