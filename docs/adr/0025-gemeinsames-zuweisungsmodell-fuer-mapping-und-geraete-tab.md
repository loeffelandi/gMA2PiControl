# 25. Gemeinsames Zuweisungsmodell für Mapping- und Geräte-Tab

* Datum: 2026-11-27
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Related to [22. Geraete-Baenke als MIDI-Kanaele und Bank-Offset](0022-geraete-baenke-als-midi-kanaele-und-bank-offset.md)

Related to [24. Executor-Tasten über MA-MIDI-Remotes per RTP-MIDI](0024-executor-tasten-ueber-ma-midi-remotes-per-rtp-midi.md)

## Kontext und Problemstellung

Mapping-Tab und Geräte-Tab bearbeiten dieselbe Konfiguration, aber mit
getrennter Logik: Der Mapping-Tab pflegt eine Tabelle der globalen Ebenen und
speichert alles auf einmal, der Geräte-Tab weist je Control über einen Dialog zu
und kennt Bänke. Dieselbe Belegung ergibt je nach Tab unterschiedliche
Konfigurationen. Bank-Offset (ADR-0022), ein Bank-1-Layer, geerbte Ziele und der
RFC-7386-Merge von `PUT /api/config` (Objekte mergen, Arrays ersetzen, `null`
löscht) machen jede Abweichung zu einem schwer sichtbaren Fehler: gespeichert,
aber von einer anderen Ebene überdeckt oder mit Restfeldern abgelehnt.

## Entscheidungstreiber

* Dieselbe Aktion auf demselben Control und Scope ergibt in beiden Tabs exakt
  dieselbe Konfiguration
* Die Laufzeitauflösung in `playback_targets.py`, `playback.py` und `mapping.py`
  bleibt die Referenz; die UI darf nicht eine eigene Wahrheit entwickeln
* Geerbte Ziele dürfen nie stillschweigend als explizite Overrides gespeichert
  werden (der Bank-Offset würde eingefroren)
* `PUT /api/config` bleibt der einzige Schreibpfad
* Prüfbar ohne Hardware

## Betrachtete Optionen

* Beide Tabs behalten getrennte Schreiblogik und gleichen per Reload ab
* Neuer Backend-Endpunkt mit Vollobjekt-Semantik oder „effektivem Mapping“
* Reines Frontend-Modul für Auflösung und Patches, gemeinsamer Store und Dialog

## Entscheidung

Gewählt: ein frameworkfreies Frontend-Modul (`web/src/lib/assignment.ts`).

* **Zuweisung** als diskriminierte Union (`key`, `playback`, `encoder`,
  `modifier`, `none`) mit expliziten Feldern, einschließlich `transport`
  (ADR-0024).
* **Scope** ist `global` oder `Gerät + Bank`. Der Resolver kennzeichnet die
  Herkunft einer effektiven Belegung: `explicit-layer`, `explicit-global`,
  `inherited-global`, `inherited-offset`, `default`.
* **Resolver** spiegelt die Laufzeit: Merge pro Feld zwischen Bank-Override und
  globalem Ziel, Offset `(bank - 1) * bank_size` nur ohne eigenen Executor, ohne
  `ma_page` und bei vorhandenen Bank-Einstellungen. Er liefert das *konfigurierte*
  Ziel; die Executor-Topologie (breite Executoren) bleibt Laufzeit.
* **Vorrang** folgt der Laufzeit: Ein expliziter Layer-Key überspringt den
  Playback-Router und geht ans Mapping, wo ein Modifier jeden Key schlägt;
  sonst gewinnt ein Playback-Ziel vor globalem Key und Modifier. Wert-Controls
  kennen keinen Layer-Key-Vorrang.
* **Patch-Builder** schreiben ungenutzte Felder als `null`, ersetzen Encoder-
  und Bank-Arrays vollständig und leeren Screen-Encoder-Slots.
* **Bank 1**: ein vorhandener Layer-Eintrag gewinnt und wird bearbeitet, sonst
  die globale Ebene; beide Scopes bleiben wählbar.
* **Golden-Fixtures** (`tests/fixtures/assignment_golden.json`) laufen in
  pytest gegen die Daemon-Auflösung und in vitest gegen den UI-Resolver.

### Konsequenzen

* Gut, weil beide Tabs dieselbe Konfiguration schreiben und Abweichungen in
  Tests auffallen.
* Gut, weil kein Backend-Endpunkt und keine Konfigurationsmigration nötig sind.
* Schlecht, weil die Auflösung an zwei Stellen (Python, TypeScript) existiert;
  nur die Golden-Tests halten sie synchron.
* Schlecht, weil der Resolver bei neuen Laufzeitregeln (z. B. weitere
  Vorrangstufen) mitgezogen werden muss.

### Bestätigung

Golden-Tests grün in pytest und vitest, Parity-Matrix beider Tabs identisch und
ein Hardware-Smoke-Test auf dem Pi (Belegung aus beiden Tabs, Bankwechsel,
Offset, Löschen). Danach Status `Accepted`.

## Vor- und Nachteile der Optionen

### Getrennte Schreiblogik mit Reload-Abgleich

* Gut, weil kein Umbau nötig ist.
* Schlecht, weil die Divergenzen genau dadurch entstanden sind.

### Neuer Backend-Endpunkt

* Gut, weil die Auflösung nur einmal existiert.
* Schlecht, weil sie die Laufzeitlogik dupliziert oder neu kapselt und alle
  Clients betrifft.

### Frontend-Modul mit Golden-Tests

* Gut, weil beide Tabs dieselbe Logik teilen und die Referenz geprüft wird.
* Schlecht, weil zwei Implementierungen synchron zu halten sind.

## Weitere Informationen

* Verwandt: ADR-0022 (Bänke und Bank-Offset), ADR-0024 (Transport je Ziel)
* Change: `mapping-device-feature-parity`
