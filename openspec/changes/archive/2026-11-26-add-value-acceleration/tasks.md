# Tasks

## 1. Architekturentscheidung

- [x] 1.1 ADR mit Status `Proposed` für das virtuelle Wertemodell und die
  Ratenbeschleunigung anlegen (`adr new`), Kontext/Entscheidung/Konsequenzen/
  Alternativen eintragen und prüfen, dass die Datei unter `docs/adr/` mit
  fortlaufender Nummer und Status `Proposed` existiert.

## 2. Konfiguration und Validierung

- [x] 2.1 `ValueAccelerationSettings` (`curve`, `window`, `slow_rate`,
  `fast_rate`, `max_multiplier`) mit Standardwerten und
  `ValueAccelerationSettings()` in `ma2pi/config.py` bzw.
  `ma2pi/acceleration.py` ergänzen; `MappingSettings.value_acceleration` und
  den Parser für `[mapping.value_acceleration]` anlegen. Tests für Defaults,
  Teilabschnitt, gültige und ungültige Werte in `tests/test_config.py`.
- [x] 2.2 `PlaybackMapping.accelerated` (Default `false`) und das TOML-Feld
  `accelerated` ergänzen. Validierung: nur bei `kind = "fader"` und nur, wenn
  das Control im Profil `kind = "encoder"` hat; sonst `ConfigError` mit Control
  und Feld. Ablehnende Tests für Fader- und Button-Ziele.
- [x] 2.3 Beispielkonfiguration um `[mapping.value_acceleration]` und ein
  beschleunigtes Encoder-Ziel ergänzen; `test_example_config_is_valid` und
  `pytest tests/test_config.py` ausführen.

## 3. Beschleunigung im Playback-Router

- [x] 3.1 `ma2pi/acceleration.py` mit der Kurvenfunktion
  (`none`/`linear`/`exponential`, Klemmung auf `[1, max_multiplier]`) und
  `ValueAccelerator` für den Zustand je Control anlegen. Der Zeitgeber ist
  injizierbar; Tests decken lineare und exponentielle Zwischenwerte,
  Klemmung, Ratenfenster und `none` ab.
- [x] 3.2 `PlaybackRouter` erweitern: Ziel zuerst auflösen, bei Fader-Ziel mit
  `accelerated` den virtuellen Wert anwenden, danach auf 0.0–1.0 klemmen und
  wie bisher deduplizieren. Zustand bei Konfigurationswechsel verwerfen.
  Tests mit Fake-Clock für 1:1 bei langsamer Drehung, Verstärkung bei schneller
  Drehung, ersten Wert, Delta 0, zwei unabhängige Controls und Reset.
- [x] 3.3 Test ergänzen, dass ein Rohwertlauf von 0 bis 127 in kleinen
  schnellen Schritten spätestens bei 127 den gesendeten Wert 1.0 erreicht und
  der Rückweg spätestens bei 0 den Wert 0.0.

## 4. Mapping-Editor

- [x] 4.1 `web/src/lib/MappingPage.svelte` um die Checkbox „Beschleunigt“ für
  Fader-Ziele ergänzen, deren Control im Geräteprofil `kind = "encoder"` hat.
  Anfangszustand aus `accelerated`, Checkbox nur bei Encodern und nur bei
  Fader-Zielen.
- [x] 4.2 Payload in `patch()` um `accelerated` erweitern; beim Ausschalten
  `false` schreiben oder das Feld weglassen. Backend-Fehler an der Zeile
  anzeigen.
- [x] 4.3 `web/src/lib/MappingPage.test.ts` um Laden, Ein-/Ausschalten,
  Payload und das Fehlen der Checkbox bei Fadern und Button-Zielen ergänzen;
  `npm run test` und `npm run check` ausführen.

## 5. Dokumentation und Abnahme

- [x] 5.1 README um `[mapping.value_acceleration]`, das Feld `accelerated` und
  die Standardwerte ergänzen; Verhalten bei langsamer/schneller Drehung und
  die fehlende PickUp-Rückmeldung dokumentieren.
- [x] 5.2 Gesamttests ausführen: `pytest`, `npm run test`, `npm run check`,
  `npm run check:offline`, `npm run build`; Ergebnis in
  `verification.md` eintragen.
- [x] 5.3 Auf dem Pi installieren und mit dem ENC prüfen: langsame Drehung
  bleibt fein, eine kräftige Umdrehung erreicht den vollen Faderbereich,
  ein Encoder ohne Opt-in bleibt 1:1, die physischen Fader sind unverändert.
  Messwerte und Beobachtungen in `verification.md` nachtragen.
