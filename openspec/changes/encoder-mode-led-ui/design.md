# Design

## Context

Siehe `proposal.md` für Motivation und Scope. Ausgangslage:

- `parse_config` validiert handgeschriebene Dataclasses; die Grenzen stehen als
  Literale in den Parsern (`encoder_press` 1–8, `screen_encoders` Slots 1–4 /
  Ziele 5–10, `[led]`-Farben 0–127).
- `redacted_config` liefert bereits `[led]`, `[mapping.encoder_resolution]`,
  `[mapping.encoder_acceleration]`, `[feedback]` und
  `[profiles.*.led_feedback]`; es fehlt jede Beschreibung, wie sie zu rendern
  sind. Jede Seite baut ihre Formulare von Hand.
- Die Laufzeit bindet den momentanen Screen-Modus an
  `SCREEN_ENCODER_MODIFIER = "MA"`, die Fine-LED an
  `resolution.cycle_modifier` und die Nipple-LED an den Hardkey `NIPPLE`.
- `mapping-device-feature-parity` führt einen gemeinsamen Config-Store,
  feldbezogene Fehler und Generationen ein; `add-per-device-led-protocols`
  führt LED-Protokolle, Farbtabellen und die Regel „eine LED-Note gehört einer
  Funktion“ ein. Beide Changes sind noch nicht umgesetzt.

## Goals / Non-Goals

**Goals:**

- Eine einzige Beschreibung, aus der Formular, Grenzen, Hilfe und Platzierung
  entstehen; neue Einstellungen brauchen keinen neuen Seitencode.
- Die heutigen Hartcodierungen werden zu benannten, validierten Bindungen.
- Die Oberfläche bleibt bei künftigen Feldern automatisch korrekt, ohne die
  bestehenden Spezialfälle (Secrets, Gerätebezug, Neustart) zu verlieren.

**Non-Goals:**

- Kein generischer Roh-Editor für `config.toml` und kein Schema für Plugins.
- Keine Hardware-Vorschau (LED-Testknopf) und kein neuer Schreib-Endpunkt.
- Keine Änderung an Merge-Semantik, Atomarität oder Backup-Verhalten.

## Decisions

### 1. Katalog als Deklaration im Backend, neben den Parsern

Der Katalog ist eine Liste von `FieldSpec`-Deskriptoren in `ma2pi/config.py`,
direkt bei den zugehörigen Parsern. Jeder Eintrag beschreibt Pfad, Gruppe,
Scope, Typ, Default, Grenzen, Einheit, Label, Hilfe, Sichtbarkeit und Flags
(`advanced`, `restart_required`, `secret`).

Grenzen werden als benannte Konstanten geführt und von Parser und Katalog
gemeinsam verwendet (z. B. `SCREEN_ENCODER_SLOTS`, `LED_COLOR_MIN/MAX`). Ein
Test prüft für jedes Feld: Der Katalog-Default wird akzeptiert, der Minimalwert
wird akzeptiert, `min − 1` wird abgelehnt, der Maximalwert wird akzeptiert.

**Warum:** Zwei getrennte Tabellen („UI-Schema“ und „Validierung“) laufen
auseinander; genau das ist der heutige Zustand. Die Nähe zum Parser hält die
Änderung an einer Stelle.

**Alternative:** Schema aus den Dataclasses generieren (Pydantic, `dataclasses`
+ Typannotationen). Verworfen, weil die Validierung nicht typ-, sondern
regelbasiert ist (Bereiche, wechselseitige Abhängigkeiten, Control-Referenzen)
und Pydantic die bestehenden Fehlermeldungen ersetzen würde.

### 2. `GET /api/config/schema`, kein Teil von `/api/config`

Der Katalog ist eine eigene, cachebare Antwort. Er ist unabhängig von Werten
und Geräten; aufgelöste Bindungen (`auto` → Control) kommen aus `/api/config`
und `/api/status`. Geheimnisse werden über das `secret`-Flag nie ausgeliefert.

Die Abdeckung sichere ich mit einer Ausnahmeliste ab: Jedes editierbare Feld
muss genau einmal vorkommen; nicht katalogisierte Felder brauchen einen Grund
(z. B. `ma2.password`, `pin`, rein interne Ableitungen).

**Warum:** `PUT /api/config` bleibt der einzige Schreibpfad; das Schema ist
reine Metainformation und kann aggressiv gecacht werden.

**Alternative:** Schema in die Config-Antwort einbetten. Verworfen, weil jede
Wertänderung dann auch die Metadaten neu überträgt und Client-Caches unnötig
invalidiert.

### 3. Ein Renderer, eine Registry, viele Feldtypen

Frontend: `web/src/lib/settings/` mit

- `SettingsSection.svelte` – rendert Gruppen aus dem Katalog,
- `Field.svelte` – wählt anhand des Typs die passende Feldkomponente,
- `fields/*` – `NumberField`, `TextField`, `ToggleField`, `SelectField`,
  `ColorField`, `ControlRefField`, `NoteField`, `NoteListField`,
  `PathField`,
- `registry.ts` – ordnet Katalog-Gruppen den Seiten und Abschnitten zu,
- `draft.ts` – baut aus geänderten Feldern einen RFC-7386-Patch.

Ein neues Feld derselben Gruppe erscheint ohne Änderung an einer Seite. Ein
neuer Typ ist eine neue Feldkomponente plus ein Eintrag in `Field.svelte`.

**Warum:** Genau das ist das Ziel „künftig in der UI bauen“. Ein Formular pro
Einstellung skaliert nicht und erzeugt wieder Drift.

**Alternative:** Ein generisches Schema-Formular ohne semantische Typen (nur
`string`/`number`). Verworfen, weil Farbindex, Notenbesitz und Control-Referenz
eigene Vorschauen und Validierung brauchen.

### 4. Scope entscheidet den Tab, die Parity-Regel die Ausnahmen

- `device` → Geräte-Tab (LED, Feedback je Profil).
- `mapping` → Mapping-Tab (Screen-Modus, Auflösung, Beschleunigung).
- `global` → gemeinsamer Abschnitt „Allgemein“.

Zuweisungsbezogene Felder (Screen-Modus einer Taste, Screen-Encoder, Modifier)
bleiben im gemeinsamen Zuweisungsmodell aus
`mapping-device-feature-parity`: Der Katalog beschreibt sie als `control-ref`
bzw. als Verweis, beide Tabs schreiben über denselben Serializer. Der Katalog
erzeugt keinen zweiten Schreibpfad.

Ein Test prüft, dass jede Katalog-Gruppe in genau den Tabs registriert ist, die
ihr Scope verlangt, und dass die LED-Gruppe im Mapping-Tab nur als Verweis
erscheint.

**Warum:** Sonst entstehen zwei Wahrheiten für dieselbe Belegung – genau der
Fehler, den die Parity-Spec behebt.

**Alternative:** Alles im Mapping-Tab bündeln. Verworfen, weil LED-Noten und
-protokolle Geräteeigenschaften sind und der Geräte-Tab bereits Profile,
Layouts und Bänke führt.

### 5. Bindungen statt Magic Strings: `auto | <control> | none`

Neue Felder:

```toml
[mapping.screen_mode]
momentary = "auto"       # auto | <control> | none

[led]
fine_control = "auto"    # auto | <control> | none
nipple_control = "auto"  # auto | <control> | none
```

`auto` bildet das heutige Verhalten exakt nach:

- `momentary`: erster Control, dessen Hardkey zu `MA` auflöst; keiner → aus.
- `fine_control`: `mapping.encoder_resolution.cycle_modifier`.
- `nipple_control`: Control, dessen Hardkey zu `NIPPLE` auflöst.

Ein Helfer `resolve_control_ref(config, ref, kind)` liefert den Control oder
`None`; Engine, LED-Schleife, Status und Katalog verwenden ihn. Ein benannter
Control muss existieren, darf aber Modifier oder normale Taste sein. `none`
schaltet die Funktion ab.

**Warum:** Der Benutzer kann MA auf eine andere Taste legen, ohne den Hardkey zu
missbrauchen; das Verhalten bleibt für bestehende Konfigurationen identisch.

**Alternative:** Pflichtfeld ohne `auto`. Verworfen, weil jede bestehende
Konfiguration dann migriert werden müsste (`BREAKING`).

### 6. Effektiver Modus wird einmal berechnet

`Ma2Client` hält `screen_mode` (fest) und `screen_modifier_held` (momentan) und
leitet `screen_encoder_active` daraus ab. Der Status liefert alle drei Werte;
die LED folgt `screen_encoder_active`. Rücksetzen bei `cleanup()`,
`release_device()`, Konfig-Tausch und Verbindungsverlust bleibt zentral.

**Warum:** LED, Encoder-Ziel und Statusanzeige dürfen nie auseinanderlaufen.

**Alternative:** Die UI rechnet aus drei Feldern selbst. Verworfen, weil dann
jede Anzeige die Regel erneut implementiert.

### 7. Notenbesitz wird angezeigt, nicht neu validiert

Die Besitzregel stammt aus `add-per-device-led-protocols` und bleibt dort
autoritativ (`--check-config`). Der Katalog markiert Notenfelder mit ihrer
Funktion; die Oberfläche berechnet daraus Konflikte und zeigt sie an, blockiert
das Speichern aber erst über den Backend-Fehler.

**Warum:** Zwei Validierungen derselben Regel driften.

**Alternative:** Konflikte im Frontend verbieten. Verworfen, weil das Backend
die Wahrheit hält und Feldbezug liefern kann.

### 8. Erweiterbarkeit ohne Formularwildwuchs

Der Abschnittskopf bietet eine Suche über Label, Pfad und Hilfe sowie einen
Schalter „Erweiterte Felder“. Abschnitte sind nach Scope gruppiert und
einklappbar. Ein Katalogeintrag ohne Registrierung fällt im Test auf, nicht erst
beim Benutzer.

**Warum:** Mit wachsendem Katalog wird Auffindbarkeit zum Problem.

**Alternative:** Keine Suche, nur Scrollen. Verworfen, weil `[led]` und
Feedback zusammen bereits über 20 Felder haben.

### 9. ADR für die Katalog-Architektur

Die Entscheidung „Konfigurationsoberfläche wird aus einem Backend-Katalog
gerendert“ hat langfristige Wirkung und wird als ADR mit Status `Proposed`
festgehalten (nächste freie Nummer beim Anlegen, derzeit 0026; 0024 und 0025 sind vergeben) und mit der
Deployment-/Konfigurations-ADR verlinkt.

**Warum:** Repo-Konvention für Architekturentscheidungen.

**Alternative:** Nur Design-Dokument. Verworfen, weil die Regel auch für
künftige Changes gelten soll.

### 10. Reihenfolge zu laufenden Changes

Der Change baut auf dem Store, den Feldfehlern und der Generation aus
`mapping-device-feature-parity` sowie auf den Protokollen und der Besitzregel
aus `add-per-device-led-protocols` auf. Er wird erst nach deren Archivierung
angewendet; die Aufgaben beginnen mit einem Abgleich der dann gültigen
Delta-Specs.

## Risks / Trade-offs

- **Katalog und Parser laufen auseinander** → gemeinsame Konstanten plus
  Grenzwert- und Deckungstest je Feld; ein neues Feld ohne Katalogeintrag
  bricht den Test.
- **Generische Felder verlieren Fachlogik** → semantische Feldtypen
  (Farbindex, Control-Referenz, Note, Notenliste) statt nur Skalar-Renderern;
  Snapshot-Tests je Typ.
- **Geheimnisse im Schema** → `secret`-Flag und Test, der Passwort und PIN in
  der Antwort ausschließt.
- **Zwei Schreibpfade für Zuweisungen** → Katalog beschreibt Zuweisungsfelder
  nur als Verweis; beide Tabs nutzen den gemeinsamen Store und Serializer;
  Parity-Test schreibt dieselbe Änderung aus beiden Tabs.
- **Merge-Fehler bei verschachtelten Feldern** → Patch-Builder schreibt nur die
  geänderten Blätter; `null` entfernt einen Schlüssel und stellt `auto` wieder
  her.
- **Neustartpflicht wird übersehen** → `restart_required` im Katalog und
  Hinweis vor dem Speichern; Test für `web.bind`/`web.port`.
- **Großer Katalog auf kleinen Displays** → einklappbare Abschnitte, Suche,
  erweiterte Felder standardmäßig zu.
- **Abhängigkeit von zwei offenen Changes** → Anwendung erst nach deren
  Archivierung; die Aufgaben enthalten einen Spec-Abgleich als ersten Schritt.

## Migration Plan

1. Neue Schlüssel sind optional und defaulten auf `auto`; bestehende
   Konfigurationen werden nicht umgeschrieben.
2. Katalog und Bindungen zuerst ohne UI ausliefern; Verhalten bleibt identisch.
3. Danach den Renderer einführen und die neuen Abschnitte ergänzen; bestehende
   Handformulare bleiben unverändert, bis die Abschnitte abgelöst sind.
4. Rollback: Frontend auf den vorherigen Build zurücksetzen; das Backend
   toleriert fehlende Katalog-Aufrufe und unbekannte Felder nicht (Schema ist
   additiv), die alten Formulare funktionieren weiter.

## Open Questions

Keine. Verbleibende Detailfragen (Reihenfolge der Felder innerhalb einer
Gruppe, genaue Hilfetexte) ändern weder Specs noch Aufgabenstruktur.
