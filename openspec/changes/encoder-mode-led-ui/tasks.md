# Tasks

## 1. Vorbereitung

- [ ] 1.1 `mapping-device-feature-parity` und `add-per-device-led-protocols` auf Umsetzungsstand prüfen und die dort gültigen Store-, Feld- und Besitzregeln in einer kurzen Konfliktliste festhalten; verifizieren, dass keine offene Doppelung zu `[led]`, `screen_encoders` oder `[mapping.screen_mode]` bleibt.
- [ ] 1.2 ADR für die kataloggetriebene Konfigurationsoberfläche mit `adr new` anlegen (Status `Proposed`, nächste freie Nummer), mit der Deployment-/Konfigurations-ADR verlinken und den Index unter `docs/adr/README.md` prüfen.

## 2. Katalog und gemeinsame Grenzen

- [ ] 2.1 Benannte Konstanten für `[led]`-Farben, Noten, Helligkeiten, Kanäle, `screen_encoders`-Slots/-Ziele, Auflösungs- und Beschleunigungswerte einführen und in den Parsern verwenden; verifizieren, dass alle bestehenden `tests/test_config.py`-Fälle unverändert grün sind.
- [ ] 2.2 `FieldSpec`-Deskriptoren und den Katalog für `[led]`, `[feedback]`, `[profiles.*.led_feedback]`, `[mapping.screen_mode]`, `[mapping.encoder_resolution]`, `[mapping.encoder_acceleration]` und `[mapping.value_acceleration]` anlegen, inklusive dynamischer Screen-Encoder-Slots; Test prüft Pfad, Typ, Default, Grenzen und genaue Einmaligkeit.
- [ ] 2.3 Grenzwert- und Deckungstest bauen: Katalog-Default, Minimum, Maximum und `min − 1` gegen `parse_config` prüfen; Ausnahmeliste für `ma2.password` und `pin` mit Grund; ein Test bricht bei fehlenden, doppelten oder veralteten Pfaden ab.
- [ ] 2.4 `GET /api/config/schema` in `ma2pi/web/__init__.py` registrieren und aus dem Katalog speisen; Test prüft Antwortform, fehlende Geheimnisse und leere Ausnahmeliste im Payload.
- [ ] 2.5 Katalog-Endpoint und Feldsemantik in `docs/api.md` dokumentieren; verifizieren, dass die dokumentierte Antwort dem Test-Fixture entspricht.

## 3. Konfigurierbare Bindungen

- [ ] 3.1 `[mapping.screen_mode].momentary`, `[led].fine_control` und `[led].nipple_control` mit `auto|<control>|none` parsen, validieren, serialisieren und defaulten; Test deckt `auto` mit und ohne MA, benannten Control, `none` und unbekannten Control mit Feldfehler ab.
- [ ] 3.2 Helfer `resolve_control_ref` implementieren und in Engine, LED-Schleife, Status und Katalog verwenden; Test prüft, dass `auto` exakt das bisherige Verhalten liefert (MA, `cycle_modifier`, `NIPPLE`).
- [ ] 3.3 `mapping.py` von `SCREEN_ENCODER_MODIFIER` lösen: momentaner Modifier aus der Config, sowohl als Modifier als auch als normale Taste; Tests für Press/Release, `cleanup()`, `release_device()` und Konfig-Tausch.
- [ ] 3.4 Fine- und Nipple-LED in `__main__.py`/`ma2_client.py` an die aufgelösten Bindungen koppeln und die Hardkey-Vergleiche entfernen; Tests für Auto-, benannte und abgeschaltete Bindung.
- [ ] 3.5 Status um festen Modus, gehaltenen Modifier, effektiven Modus und aufgelöste Bindungen erweitern; Test prüft Momentan-Press/Release, Rücksetzen bei Verbindungsverlust und Konfig-Tausch.

## 4. Generischer Einstellungs-Renderer

- [ ] 4.1 `web/src/lib/api.ts` um Schema-Typen und `configSchema()` erweitern; Test prüft Typen und Fehlerpfad des Clients.
- [ ] 4.2 `web/src/lib/settings/draft.ts` implementieren: Patch nur aus geänderten Blättern, `null` entfernt Schlüssel, verschachtelte Gruppen und dynamische Slot-Maps; Tests für Ändern, Zurücksetzen und Löschen.
- [ ] 4.3 `SettingsSection.svelte`, `Field.svelte` und die Feldkomponenten für `integer`, `number`, `boolean`, `text`, `enum`, `color-index`, `control-ref`, `note`, `note-list` und `path` bauen; Komponententests je Typ inklusive Bereichsgrenzen und unbekanntem Typ (schreibgeschützt).
- [ ] 4.4 Registry für Katalog-Gruppen nach Scope, Abschnittssuche, „Erweiterte Felder“-Schalter und Neustart-Hinweis ergänzen; Test prüft, dass eine neue Gruppe ohne Seitenänderung erscheint und `advanced` eingeklappt ist.
- [ ] 4.5 Feldbezogene Backend-Fehler und Generation/Konflikt aus dem gemeinsamen Store im Renderer anzeigen; Test mit abgelehntem Wert prüft die Meldung am Feld und den unveränderten Entwurf.

## 5. Geräte-Tab

- [ ] 5.1 ASL-LED-Abschnitt mit allen `[led]`-Feldern im Geräte-Tab registrieren, inklusive deaktiviertem Zustand und Erklärung der Wirkungslosigkeit; Test speichert eine geänderte Modus-Farbe und prüft den Patch.
- [ ] 5.2 LED-Feedback je erkanntem Profil (Protokoll, Notenliste, Takt) anbinden und Profile ohne Deklaration korrekt darstellen; Test deckt Erkennen, Aktivieren und Entfernen ab.
- [ ] 5.3 Farbvorschau (Index plus Palettenname) und Notenbesitz-Konflikt zwischen Modus-, Fine-, Nipple- und Profilnoten anzeigen, ohne Hardwarezugriff; Komponententest prüft Vorschau und Konflikttext, ein API-Test stellt sicher, dass kein LED-Frame entsteht.

## 6. Mapping-Tab

- [ ] 6.1 Abschnitt „Screen-Modus & Encoder“ mit Toggle-Tasten, momentanem Modifier samt aufgelöstem Control und Screen-Encoder-Zielen registrieren; Test prüft, dass dieselbe Änderung in beiden Tabs denselben Patch erzeugt.
- [ ] 6.2 Auflösung (Normal/Fine/Ultra und Fine-/Ultra-/Cycle-Modifier) sowie Encoder- und Wert-Beschleunigung bearbeitbar machen; Test prüft Hot-Reload ohne Dienstneustart und die gespeicherten Werte.
- [ ] 6.3 Verweis vom Mapping-Abschnitt auf den LED-Abschnitt des Geräte-Tabs ergänzen, ohne LED-Felder zu duplizieren; Test prüft Link-Ziel und dass die LED-Gruppe genau einmal registriert ist.

## 7. Integration und Abnahme

- [ ] 7.1 Vollständige Suite ausführen: `pytest -q`, in `web/` `npm run check`, `npm run test`, `npm run check:offline` und `npm run build`; `openspec validate encoder-mode-led-ui --strict` muss fehlerfrei sein.
- [ ] 7.2 README um Katalog, die neuen Bindungen und die beiden Abschnitte ergänzen; verifizieren, dass die beschriebenen Schritte der Oberfläche entsprechen.
- [ ] 7.3 Hardware-Smoke-Test auf dem Pi: momentanen Modifier auf eine andere Taste legen, Modus-LED grün/rot prüfen, Fine-/Nipple-Bindung und Farben ändern, ohne Dienstneustart speichern; Ergebnis im Change dokumentieren.

## Workflow follow-up

- Erst anwenden, nachdem `mapping-device-feature-parity` und `add-per-device-led-protocols` archiviert und ihre Delta-Specs übernommen sind.
- Nach bestandener Abnahme archivieren und die Delta-Specs nach `openspec/specs/` synchronisieren.
