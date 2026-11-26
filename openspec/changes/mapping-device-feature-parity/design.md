# Design

## Context

Siehe `proposal.md` für Motivation und Scope. Ausgangslage:

- Der Mapping-Tab arbeitet nur mit den globalen Ebenen `mapping.keys`,
  `mapping.playbacks`, `mapping.encoders`, `mapping.screen_encoders` und
  `mapping.modifiers`. Er liest weder `mapping.device_banks` noch das
  Control-Inventar der MIDICRAFT-Profile und zeigt deshalb bankgebundene
  Controls und Overrides nicht an.
- Der Geräte-Tab arbeitet mit Inventar, Bänken, Layout und effektiver
  Auflösung, kann aber keine Belegung löschen, keinen globalen Scope gezielt
  bearbeiten und schreibt bei Bank 1 am vorhandenen Layer vorbei.
- `PUT /api/config` arbeitet mit RFC-7386-Merge: Objekte werden rekursiv
  zusammengeführt, Arrays ersetzt, `null` löscht einen Schlüssel. Die
  Laufzeitauflösung in `mapping.py`/`playback.py` ist die Referenz, nicht die
  UI.
- `add-device-layout-visuals` liefert Bänke, Inventar und Geräteflächen, ist
  aber noch nicht archiviert. Dieser Change wird nach dessen Archivierung
  angewendet, damit die `config-ui`-Delta-Specs nicht übereinanderliegen.

## Goals / Non-Goals

**Goals:**

- Ein einziges Zuweisungsmodell mit Scope und Herkunft, das beide Tabs teilen.
- Identische Schreibresultate für dieselbe Aktion und denselben Scope.
- Vollständige Control- und Bankdaten in beiden Tabs.
- Löschen, Überschreiben und Aktionswechsel ohne versteckte Restfelder.
- Ein gemeinsamer Konfigurationszustand inklusive Konflikt- und Fehleranzeige.
- Zwei klar getrennte Lernwege mit gemeinsamem Status.

**Non-Goals:**

- Keine Änderung der Laufzeitauflösung oder der Prioritätsreihenfolge.
- Kein neuer Schreib-Endpunkt; `PUT /api/config` bleibt der einzige Pfad.
- Kein Drag-and-drop-Layouteditor und keine räumliche Mehrfachauswahl im
  Mapping-Tab; der Geräte-Tab bleibt die Flächen-Sicht.
- Kein Import/Export, Undo/Redo oder Freitext-JSON-Editor.
- Keine Migration bestehender Konfigurationen.

## Decisions

### 1. Zuweisung als gemeinsames Modell

Eine Zuweisung wird als diskriminierte Union modelliert:

```ts
type Scope =
  | { kind: 'global' }
  | { kind: 'bank'; device: string; bank: number };

type Assignment =
  | { kind: 'none' }
  | { kind: 'key'; hardkey?: string; command?: string; screenMode?: boolean;
      screen?: number; encoderPress?: number }
  | { kind: 'playback'; page: number | 'current'; executor: number;
      target: 'button' | 'fader'; button?: number; accelerated?: boolean }
  | { kind: 'encoder'; slot?: number; attribute?: string;
      screenEncoder?: number }
  | { kind: 'modifier'; hardkey?: string; local?: boolean };
```

Dazu liefert der Resolver `source`:

- `explicit-layer` – Eintrag in `mapping.device_banks[device][bank]`
- `explicit-global` – Eintrag in der globalen Mapping-Ebene, globaler Scope
- `inherited-global` – globaler Eintrag, im Bank-Scope geerbt
- `inherited-offset` – geerbt und um `(bank - 1) * bank_size` verschoben
- `default` – keine Belegung

**Warum:** Ohne gemeinsames Modell bleibt jede Tab-Logik eine eigene Wahrheit.
**Alternative:** Beide Tabs schreiben weiter getrennte Pfade und gleichen per
Reload ab – verworfen, weil die Divergenzen dann wieder entstehen.

### 2. Ein reines Resolver-/Serializer-Modul im Frontend

Das Frontend erhält ein frameworkfreies Modul, das die Laufzeitauflösung
spiegelt und Patches baut:

- `resolveAssignment(config, devices, scope, control)`
- `buildAssignPatch(config, scope, control, assignment)`
- `buildDeletePatch(config, scope, control)`
- `buildBankSettingsPatch(...)`

Der Serializer arbeitet bewusst mit vollständigen, expliziten Feldern:

- Key: alle fünf Aktionsfelder, ungenutzte als `null`.
- Playback: `page`, `executor`, `kind`, `button` (bei Fader `null`),
  `accelerated` (nur bei Encoder+Fader, sonst `null`).
- Encoder: die **komplette** `mapping.encoders`-Liste, weil Arrays ersetzt
  werden.
- Screen-Encoder: gewünschte Map plus `null` für entfernte Slots.
- Bänke: vollständige Bankliste, da das Profil-Array ersetzt wird.

**Warum:** Der Merge-Pfad verzeiht fehlende Felder nicht; ein Hardkey→Command-
Wechsel erzeugt sonst beide Felder und wird abgelehnt.
**Alternative:** Ein neuer Endpunkt mit Vollobjekt-Semantik – verworfen, weil
`PUT /api/config` bereits atomar validiert und alle Clients ihn nutzen.

### 3. Bank 1: Layer gewinnt, aber sichtbar

Existiert für Bank 1 ein Layer-Eintrag, bearbeitet der Geräte-Tab diesen Layer;
sonst die globale Ebene. Die UI kennzeichnet die Herkunft und bietet beide
Scopes an. Damit gibt es kein stilles „gespeichert, aber unsichtbar
überschrieben“ mehr.

**Warum:** Die Laufzeit bevorzugt den Layer; die UI muss dieselbe Regel
abbilden.
**Alternative:** Bank-1-Layer verbieten – verworfen, weil bestehende
Konfigurationen und die Laufzeit ihn unterstützen.

### 4. Offset bleibt geerbt, bis der Benutzer bewusst überschreibt

Im Bank-Scope zeigt der Dialog den effektiven Executor inklusive Offset und
markiert ihn als geerbt. „Global ändern“ schreibt den globalen Rohwert;
„nur diese Bank“ legt einen expliziten Layer-Eintrag an und weist darauf hin,
dass dieser nicht mehr dem Offset folgt. Ein geerbtes Ziel wird nie
automatisch als expliziter Eintrag gespeichert.

**Warum:** Sonst friert jede Anzeige den aktuellen Offset ein.
**Alternative:** Effektivwert immer als expliziten Wert speichern – verworfen,
weil spätere Bankgrößenänderungen dann nicht mehr wirken.

### 5. Ein gemeinsamer Dialog, zwei Einstiegspunkte

`AssignmentDialog` ersetzt den bisherigen Zuweisungsdialog und wird von beiden
Tabs verwendet. Er enthält:

- Aktionsauswahl inklusive Modifier (Hardkey/lokal) und „Belegung entfernen“.
- Scope-Auswahl (global / diese Bank) mit Herkunftsanzeige.
- Screen-Encoder-Slot 1–4 und Ziel 5–10, inklusive Leeren.
- Feldbezogene Fehler aus dem Backend.
- Vorschau bei Mehrfachzuweisung (nur Geräte-Tab).

Der Mapping-Tab rendert dieselben Aktionen als Tabellenzeilen, der Geräte-Tab
über die Fläche. Beide öffnen denselben Dialog.

**Warum:** Ein Dialog verhindert, dass Felder und Validierungsregeln erneut
auseinanderlaufen.
**Alternative:** Zwei Dialoge mit gemeinsamem Modell – verworfen, weil die
Darstellung dann wieder doppelt gepflegt werden müsste.

### 6. Gemeinsamer Konfigurationszustand

Ein Config-Store wird in `App.svelte` erzeugt und beiden Tabs übergeben. Er
hält Konfiguration, Geräte, Generation, Entwurf und Speicherstatus. Beide Tabs
lesen und schreiben ausschließlich darüber. Die API liefert eine Generation zu
`GET /api/config`; ein Speichern mit veralteter Generation wird abgelehnt und
im UI als Konflikt angeboten (neu laden oder verwerfen).

**Warum:** Zwei unabhängige Ladevorgänge erzeugen veraltete Drafts und
widersprüchliche Anzeigen.
**Alternative:** Weiterhin pro Tab laden – verworfen, weil ein Tab die
Änderung des anderen nicht sieht.

### 7. Zwei Lernwege, ein Status

- Control-Erkennung: bestehende `/api/learn/*`-Sitzung, liefert das logische
  Control.
- Noten-Anlernen: bestehende `/api/device-learn/*`-Sitzung, schreibt die
  physische Note einer Bank.

Beide Tabs können den passenden Weg starten; der jeweils andere Tab zeigt den
Status und verlinkt bei Bedarf auf die zuständige Ansicht. Der Store abonniert
`learn` und `device_learn` über den bestehenden WebSocket; Polling entfällt.
Timeout und Abbruch setzen den Status in beiden Tabs zurück.

**Warum:** Die zwei Lernbegriffe sind fachlich verschieden und dürfen nicht
vermischt werden, müssen aber überall sichtbar sein.
**Alternative:** Ein gemeinsamer Learn-Endpunkt – verworfen, weil die
Backend-Semantik unterschiedlich ist.

### 8. Vorrang sichtbar machen

Der Store berechnet pro Control den tatsächlichen Vorrang
(Layer-Key vor Playback vor Modifier/globalem Key) und zeigt bei Konflikten
ein Abzeichen mit Erklärung. Gespeichert wird weiterhin alles; die Anzeige
verhindert nur, dass der Benutzer eine wirkungslose Belegung für aktiv hält.

**Warum:** Die Laufzeit konsumiert Playback-Ereignisse vor dem Mapping; die UI
zeigte bisher nur eine scheinbare Priorität.
**Alternative:** Konflikte beim Speichern verbieten – verworfen, weil
mehrschichtige Konfigurationen bewusst möglich bleiben sollen.

### 9. Geräteauswahl

Beide Tabs filtern auf erkannte Geräte (Regel aus
`add-device-layout-visuals`). Die Auswahl von Gerät und Bank liegt im
gemeinsamen Store und bleibt beim Tab-Wechsel erhalten, solange das Gerät
erkannt ist.

**Warum:** Ein Gerät, das in einem Tab sichtbar und im anderen unsichtbar ist,
widerspricht der Parity-Anforderung.
**Alternative:** Im Mapping-Tab weiterhin alle Geräte zeigen – verworfen; die
aktive Layout-Spec hat die Sichtbarkeit bereits auf erkannte Geräte begrenzt.

### 10. Backend nur minimal ergänzen

- `field` in Validierungsfehlern, damit beide Tabs denselben Feldfehler
  anzeigen können.
- Generation/ETag zu `GET /api/config` und im `PUT`-Ergebnis.
- Keine Änderung an `mapping.py`/`playback.py`; die dortige Auflösung bleibt
  Referenz für die Golden-Tests.

**Warum:** Die Parity ist ein UI- und Zustandsproblem; die Laufzeit ist bereits
korrekt.
**Alternative:** Eine neue Effective-Mapping-API – verworfen, weil sie die
Laufzeitlogik duplizieren würde.

## Risks / Trade-offs

- **Resolver driftet von der Backend-Laufzeit ab** → Golden-Tests mit denselben
  Fixtures für Frontend-Resolver und `mapping.py`/`playback.py`; Abweichung
  bricht den Test.
- **Merge-Fehler bei Aktionswechseln** → zentraler Serializer mit expliziten
  `null`-Feldern und Tests für jeden Wechsel.
- **Bank-1-Layer bleibt unsichtbar** → Layer-Erkennung und Herkunftsanzeige
  sind Pflicht; Test mit vorhandenem Bank-1-Layer.
- **Offset wird eingefroren** → Dialog unterscheidet „global ändern“ und
  „diese Bank überschreiben“; kein automatisches Speichern des Effektivwerts.
- **Screen-Encoder-Reste** → Serializer sendet `null` für entfernte Slots;
  Test für Wechsel zu Attribut, anderen Slot und „keiner“.
- **Zwei Lern-Statusquellen** → ein Store, Event-basiert; Polling wird
  entfernt; Timeout-Test.
- **Spezifikationskonflikt beim Gerätefilter** → Anwendung erst nach
  Archivierung von `add-device-layout-visuals`; die dortige Regel „nur
  erkannte Geräte“ gilt.
- **Großer UI-Refactor** → schrittweise: erst Modell + Tests, dann Dialog, dann
  Mapping, dann Geräte, dann Learn; jeder Schritt hält die bestehenden Tests
  grün.

## Migration Plan

1. Gemeinsamen Store, Resolver und Serializer mit Golden-Tests einführen, ohne
   die Tabs umzustellen.
2. `AssignmentDialog` auf das gemeinsame Modell heben und beide Tabs darauf
   umstellen; alte Pfade entfernen.
3. Mapping-Tab auf Inventar/Bänke umstellen, Löschen und Scope ergänzen.
4. Geräte-Tab auf gemeinsamen Store/Dialog umstellen, Bank-1- und
   Screen-Encoder-Fehler beheben.
5. Learn-Status vereinheitlichen, Polling entfernen.
6. Backend um `field` und Generation ergänzen; Parity-Matrix ausführen.
7. README und Screenshots aktualisieren; Change archivieren und Delta-Specs
   übernehmen.

Rollback: Die Konfiguration bleibt unverändert; ein Revert der UI-Commits
stellt den alten Stand wieder her. Es gibt keine Datenmigration.

## Open Questions

Keine. Die verbleibenden Detailentscheidungen (z. B. genaue Beschriftung der
Herkunftsabzeichen) ändern weder Specs noch Aufgabenstruktur.
