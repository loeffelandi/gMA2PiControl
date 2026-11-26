# Design

## Context

Geräte sind datengetrieben: `[devices.*]` matcht Hardware über Vendor-/Product-ID
und Namensfilter, `[profiles.*]` bildet Rohdaten auf logische Controls ab, und
alle Eingaben laufen als `InputEvent` mit den Arten `key`, `encoder` und `value`
durch dieselbe Pipeline. Die Oberfläche kennt nur Tabellen in `MappingPage`; die
Seite „Geräte“ ist ein Platzhalter. Layouts und Bänke existieren nicht.

Am MIDICRAFT ENC gemessen: Bank 2 sendet andere Noten als Bank 1 (Encoder-Klick
1 = Note 0 statt 55, Fader 1 = Note 15 statt 70, Werte absolut 1–127). Der
Bankwechsel selbst sendet nichts. Die Noten sind am Gerät frei einstellbar, und
mehrere MIDICRAFT-Geräte können parallel laufen.

Siehe `proposal.md` für Motivation und Umfang sowie `specs/` für die
Anforderungen.

## Goals / Non-Goals

**Goals:**

- Ein Layout-Schema, das unregelmäßige Flächen ohne Frontend-Hardcoding abbildet.
- Bänke als explizite Editorauswahl, ohne Laufzeiterkennung am Gerät.
- Physische Control-Belegung einmalig per geführtem Learn-Modus erfassen.
- Bänke standardmäßig auf derselben MA-Page verteilen, mit konfigurierbarem
  Offset und optionalem MA-Page-Wechsel.
- Direktzuweisung und Mehrfachzuweisung auf der Gerätefläche mit atomarem
  Speichern.

**Non-Goals:**

- LED-Feedback, PickUp und Executor-Rückmeldung.
- Drag-and-drop-Layouteditor oder freies Zeichnen.
- Pixelgenaue Nachbildung von Gehäuse, Schrift oder Beleuchtung.
- MIDI-CC-Betrieb; Profile gehen vom Note-Modus der Geräte aus.
- ASL-Modelle außer MK2-E4B3, MIDICRAFT-Vorgängerserie.

## Decisions

### 1. Layout hängt am Profil, nicht an einer Geräteinstanz

`[layouts.<name>]` referenziert `profile = "<profil>"`. Mehrere Geräte mit
demselben Profil teilen sich das Layout, und mitgelieferte Layouts sind auch
ohne angeschlossene Hardware gültig. Die API hängt das Layout beim Ausliefern an
jedes konfigurierte Gerät seines Profils.

Alternative: Layout direkt am Gerätenamen. Verworfen, weil dann jedes
mitgelieferte MIDICRAFT-Layout eine Geräteinstanz in der Beispielkonfiguration
bräuchte und die Validierung ohne Hardware fehlschlägt.

### 2. Rasterdaten statt SVG

```toml
[layouts.cherry]
profile = "cherry-g86"
columns = 21
[[layouts.cherry.rows]]
cells = [
  { label = "Ch Pg+", control = "ch_pg_plus", color = "blue", row = 1, col = 1 },
  { label = "Pause", control = "pause_big", color = "green", col_span = 4, row_span = 2, row = 1, col = 2 },
  { label = "", col_span = 1, row = 1, col = 6 },
]
```

- `columns` ist die Bezugsbreite, `col_span`/`row_span` bilden große Tasten ab.
- `row`/`col` positionieren eine Zelle absolut im Raster; beide Angaben sind
  gemeinsam erforderlich und belegte Felder dürfen sich nicht überlappen.
- `color` ist ein optionaler Palettenname; die Darstellung mappt ihn auf CSS.
- Zellen ohne `control` sind reine Beschriftung.
- Das Layout ist bankunabhängig, weil es logische Controls referenziert, die auf
  allen Bänken dieselben bleiben.

Alternative: SVG je Gerät. Verworfen, weil nicht validierbar, nicht per
Learn-Modus befüllbar und jede Änderung ein Asset-Build wäre.

### 3. Control-Inventar getrennt von der Notenbelegung

```toml
[[profiles.midicraft-enc.controls]]
id = "mc_fader_1"
kind = "fader"
label = "Fader 1"

[[profiles.midicraft-enc.banks]]
number = 2
channel = 2

[profiles.midicraft-enc.banks.notes]
0 = "mc_click_1"      # Encoder-Klick 1 in Bank 2
15 = "mc_fader_1"     # Fader 1 in Bank 2
```

- `kind` bestimmt die Ereignisart: `button` → Taste, `fader`/`poti`/`encoder` →
  absoluter Wert, `relative-encoder` → Delta.
- Das Inventar ist die Wahrheit für Layout, Validierung und Learn; Noten sind
  Belegung und dürfen fehlen.
- Bestehende Profile ohne Inventar leiten die Controls aus `notes`,
  `midi_encoders` und `midi_values` ab; die Konfiguration bleibt gültig.
- Flache Noten gelten als Bank 1.

Alternative: Controls weiterhin nur aus Noten ableiten. Verworfen, weil ein
frisches MIDICRAFT-Profil sonst unsichtbar wäre und der Learn-Modus kein Ziel
hätte.

### 4. Bank besteht aus Kanal und Noten; die Editorwahl ist unabhängig

- Maximal 16 Bänke je Profil. Jede Bank hat einen eigenen MIDI-Kanal (Default =
  Banknummer). Kanäle müssen je Profil eindeutig sein; Noten müssen nur
  innerhalb einer Bank eindeutig sein und dürfen sich zwischen Bänken
  wiederholen.
- Ein Page-Wechsel am MIDICRAFT ändert Kanal und Notenbelegung gemeinsam.
- Die Oberfläche wählt die Bank zum Lernen und Mappen. Diese Auswahl wird nicht
  an das Gerät oder die MA gesendet und nicht als „aktiv“ angezeigt.
- Ein Ereignis wird zuerst über den Kanal der Bank und dann über die Note dem
  Control zugeordnet. Es gibt keinen Zustand „aktuelle Bank“, der die Anzeige
  steuert; die zuletzt verarbeitete Bank wird nur für die optionale
  MA-Page-Bindung gemerkt.
- Ein Bankwechsel am Gerät erzeugt kein eigenes Ereignis. Das erste bediente
  Control danach trägt über Kanal und Note die neue Bank.

Alternative: Bank nur über die Note bestimmen. Verworfen, weil derselbe
Notenwert auf mehreren Kanälen vorkommen kann und der Kanal der eigentliche
Unterschied zwischen den Pages ist.

Alternative: Bank in den Control-Namen kodieren (`mc_fader_1_b2`). Verworfen,
weil Layouts und Inventar dann pro Bank dupliziert würden.

### 5. Mapping-Ebenen und Bank-Offset

```toml
[mapping.device_banks.midicraft]
bank_size = 5

[mapping.device_banks.midicraft.2]
ma_page = 2

[mapping.device_banks.midicraft.2.playbacks.mc_fader_1]
executor = 20          # explizit, ohne Offset
kind = "fader"
```

Auflösung je Ereignis:

1. Expliziter Eintrag der Bank-Ebene für `(Gerät, Bank, Control)`.
2. Sonst globales Ziel; bei Executor-Zielen wird die Executor-Nummer um
   `(Bank - 1) * bank_size` erhöht.
3. Ist für die Bank eine MA-Page hinterlegt, entfällt der Offset und es wird
   beim ersten Ereignis dieser Bank einmalig `Page <n>` gesendet.

`bank_size` ist pro Gerät konfigurierbar; Default ist die Anzahl der
Fader-Controls, ersatzweise die Anzahl der Tasten-Controls. Nur Executor-Ziele
werden verschoben, Button-Nummern bleiben gleich. Explizite Einträge werden nie
zusätzlich verschoben.

Alternative: Jede Bank schaltet zwingend eine MA-Page. Verworfen als Default,
weil der Benutzer die Bänke auf der aktuellen MA-Page verteilen will; die
Bindung bleibt pro Bank konfigurierbar.

### 6. Geführter Learn-Modus

Ablauf:

1. Oberfläche wählt Gerät und Bank und startet die Sitzung.
2. Der Daemon bildet die Liste der Controls ohne Notenbindung in dieser Bank in
   Layout-Reihenfolge.
3. Das erste Control wird aktiv; die Oberfläche hebt es hervor.
4. Das nächste Roh-Ereignis auf dem Kanal der gewählten Bank wird abgefangen,
   bevor es normalisiert oder gemappt wird. Note und Control werden gepaart.
5. Danach rückt die Sitzung zum nächsten Control vor; Überspringen ist möglich.
6. Abschluss schreibt alle Belegungen in einem `PUT /api/config`; Abbruch
   verwirft sie.

Details:

- Ereignisse während des Lernens erzeugen keine Frames.
- Ereignisse auf einem anderen Kanal werden abgelehnt; Bank und erwarteter Kanal
  werden in der Oberfläche angezeigt.
- Ein Timeout pausiert die Sitzung; bereits erfasste Belegungen bleiben.
- Bei Geräteverlust pausiert die Sitzung und wird nach dem Reconnect am selben
  Control fortgesetzt.
- Eine bereits in derselben Bank vergebene Note wird abgelehnt; dieselbe Note
  auf einem anderen Bank-Kanal bleibt zulässig.
- Es gibt höchstens eine Sitzung gleichzeitig; ein zweiter Start wird abgelehnt.
- Der Learn-Zustand lebt nur im Speicher und wird nicht persistiert.

Alternative: Noten weiterhin vorab messen und in Profile schreiben. Verworfen,
weil die Noten gerätespezifisch frei belegt sind (Bank 1 trägt bereits einen
Offset durch andere Controller).

### 7. MIDICRAFT-Familie mit getrennten Namenspräfixen

Die sechs Modelle teilen Firmware und Bank-Schema, unterscheiden sich aber in
der Control-Anzahl. Präfixe: `mc_` bleibt `ENC`, dazu `mcp_` (`PUSH²`), `mcf_`
(`FADE²`), `mct_` (`TURN²`), `mcm_` (`MIX²`), `mcs_` (`SPOT`). Die
Konfigurationsvalidierung erzwingt globale Eindeutigkeit der Control-Namen.

Wo die Product-ID nicht bekannt ist, wird sie als `0` (beliebig) mit
`name_contains` je Modell konfiguriert; die Messung ersetzt das später durch
die exakte ID.

### 8. Geräte-Seite wird Fläche, Mapping-Tabellen bleiben

Neue Svelte-Komponenten `DeviceSurface` (CSS Grid, Spannen, Farben, Auswahl),
`AssignDialog` (Aktion, Felder, Startwert, Schrittweite, Vorschau) und
`LearnPanel` (Bank, aktives Control, Fortschritt, Überspringen, Abbrechen,
Speichern). Die Auswahl ist ein Array in Klick-Reihenfolge. Dialog und Learn
schreiben über den bestehenden `PUT /api/config`; die serverseitige Validierung
entscheidet atomar.

Alternative: eigener Bulk-Endpunkt. Verworfen, weil er dieselbe
Validierungslogik ein zweites Mal bräuchte.

Die Bankauswahl im Editor ist reine Ansicht und schaltet weder Gerät noch MA.

### 9. Beschleunigung bleibt eine Eigenschaft des Playback-Ziels

Der Schalter in der Geräteansicht liest und schreibt ausschließlich das Feld
`accelerated` des effektiven Playback-Ziels, das `add-value-acceleration`
einführt. Es gibt keine geräteweite oder bankweite Beschleunigungseinstellung.

- Sichtbar ist der Schalter nur, wenn das Control im Inventar `kind = "encoder"`
  hat und das Ziel `kind = "fader"` ist.
- Bei gewählter Bank größer 1 schreibt der Schalter den Eintrag der Bank-Ebene.
  Existiert dort noch kein Eintrag, wird einer mit dem effektiven Ziel und dem
  Schalterwert angelegt; der globale Eintrag bleibt unverändert.
- Bei Mehrfachzuweisung gilt der Schalter für alle erzeugten Fader-Ziele.
- Die bestehende Backend-Validierung aus `add-value-acceleration` bleibt
  maßgeblich; die Oberfläche zeigt Fehler am betroffenen Control.
- Ein Konfigurationswechsel wird wie bisher per Hot Reload übernommen und
  verwirft die virtuellen Werte.

Alternative: ein globaler Beschleunigungs-Schalter pro Gerät. Verworfen, weil
die Beschleunigung bewusst je Encoder gilt und physische Fader unberührt bleiben
sollen.

### 10. Change-Name bleibt

Das Change heißt weiterhin `add-device-layout-visuals`; der Kern – Geräte
schematisch zeigen und direkt belegen – bleibt unverändert. Bänke, Bank-Offset
und Learn erweitern dieses Ziel.

## Risks / Trade-offs

- **Frei belegbare Noten** → Profile starten ohne Noten; Learn-Modus füllt sie.
  Validierung lässt deklarierte, aber ungebundene Controls zu.
- **Notenkollision innerhalb einer Bank** → Validierung verbietet doppelte
  Noten je Bank; derselbe Notenwert auf einem anderen Bank-Kanal ist erlaubt.
- **Doppelter Kanal** → Validierung verlangt eindeutige Kanäle je Profil, weil
  der Kanal die Bank bestimmt.
- **Falsche Bank im Editor gewählt** → der Learn-Modus erwartet den Kanal der
  Bank und meldet Ereignisse auf anderen Kanälen, statt sie zu übernehmen.
- **Bankgröße ist eine Annahme** → Default aus Fader-/Tastenzahl; explizite
  Bank-Einträge überschreiben den Offset, `bank_size` ist konfigurierbar.
- **Editor zeigt nicht, welche Bank das Gerät gerade sendet** → bewusst; die
  Bank wird beim Bearbeiten gewählt, nicht angezeigt.
- **Falsche Zuordnung beim Lernen** → aktives Control hervorgehoben, Note
  sichtbar, Re-Learn möglich; doppelte Note wird abgelehnt.
- **`Page <n>` legt auf der MA eine leere Page an, falls sie fehlt** → nur
  explizit konfigurierte Bindungen senden den Befehl; README weist darauf hin.
- **Mehrfachzuweisung in falscher Reihenfolge** → sichtbare Nummerierung in
  Klick-Reihenfolge und Vorschau vor dem Speichern.
- **Layout weicht von der Hardware ab** → rein kosmetisch; Validierung prüft
  nur Control-Referenzen, nicht die Geometrie.
- **Namenskollisionen zwischen Geräten** → Präfixe plus globale
  Eindeutigkeitsprüfung.
- **Kopplung an `add-value-acceleration`** → der Schalter schreibt nur das dort
  definierte Feld; solange das Change nicht umgesetzt ist, lehnt das Backend die
  Kombination ab und die Oberfläche zeigt den Fehler.
- **Bank-Eintrag beim Schalten** → beim ersten Schalten in einer Bank wird ein
  Eintrag mit dem effektiven Ziel angelegt; die Vorschau zeigt das resultierende
  Ziel vor dem Speichern.

## Migration Plan

1. Neue Sektionen sind optional; bestehende `config.toml` lädt unverändert,
   flache Profile gelten als Bank 1.
2. Beispielkonfiguration um Inventar, Layouts und eine auskommentierte
   Bank-Ebene ergänzen; MIDICRAFT-Geräte mit Wildcard-PID und Namensfilter.
3. Nach dem Deploy einmalig den Learn-Modus je MIDICRAFT-Gerät und Bank
   ausführen, um die gerätespezifischen Noten zu erfassen.
4. Rollback: neue Sektionen entfernen oder Backup über die bestehende
   Backup-Funktion einspielen; vor dem Ausrollen ein Backup anlegen.
5. Keine Datenmigration, keine Umbenennung bestehender Controls.

## Open Questions

- Ob die Bankgröße später je Control-Art unterschiedlich sein soll (Fader 5,
  Tasten 20). Das Schema erlaubt heute nur einen Wert pro Gerät; explizite
  Bank-Einträge decken Sonderfälle ab.
- Ob eine automatische MA-Page-Bindung überhaupt genutzt wird oder die Bänke
  ausschließlich über den Offset verteilt werden. Die Bindung ist optional und
  kann später entfernt werden.
