# Design

## Context

Siehe `proposal.md` – Why. Der Encoder-Dispatch in `ma2pi/ma2_client.py` löst
bereits für Deltas das aktive Ziel auf: im Screen-Modus
`mapping.screen_encoders[slot]`, sonst `page.name_for(slot)`. Der
Auflösungspfad (`ToggleFine`) nutzt dagegen unbedingt die Page. Die
Mapping-Seite bearbeitet bisher nur `mapping.keys`, `mapping.encoders` und
`mapping.modifiers`; `mapping.screen_encoders` fehlt im Patch.

## Goals / Non-Goals

**Goals:**

* Ein einziger Auflösungshelfer, der das aktive Ziel eines Slots liefert, damit
  Delta- und Auflösungsframes nie auseinanderlaufen.
* Screen-Encoder-Namen in der bestehenden Mapping-Tabelle bearbeiten und leere
  Slots sauber entfernen.
* Bestehende Validierung (Slots 1–4) und Merge-Patch-Semantik wiederverwenden.

**Non-Goals:**

* Echte Screen-Encoder-Namen ermitteln oder fest verdrahten.
* Den Screen-Modus über Neustarts hinweg persistieren.
* Die Auflösungsstufen pro Ziel trennen; die bestehende Speicherung pro Slot
  bleibt.

## Decisions

### Gemeinsamer Ziel-Resolver im Client

`Ma2Client` erhält eine private Methode, die für einen Slot den aktiven Namen
zurückgibt: Screen-Name bei aktivem Screen-Modus, sonst Page-Attribut. Fehlt der
Name, loggt sie eine passende Warnung und liefert `None`. `EncoderSlot` und
`ToggleFine` verwenden denselben Resolver.

Alternative: Im `ToggleFine`-Zweig nur die Bedingung duplizieren. Verworfen,
weil dann zwei Stellen dieselbe Moduslogik pflegen und erneut auseinanderlaufen
können.

### Screen-Encoder als Spalte in der Encoder-Tabelle

Die Mapping-Seite zeigt pro physischem Encoder eine Auswahl (`— keiner —`,
Screen-Encoder 5–8). Beim Speichern entsteht daraus ein Objekt mit den belegten
Slots sowie `null` für zuvor belegte, jetzt leere Slots. Die
RFC-7386-Merge-Patch-Semantik des Config-Stores entfernt damit genau diese
Schlüssel; die vorhandene Validierung prüft weiterhin Bereich und Inhalt.

Die mitgelieferte Konfiguration belegt die Slots mit den onPC-Screen-Encodern
5–8 in umgekehrter Reihenfolge (Slot 1 → `"8"` … Slot 4 → `"5"`), weil die
physische Encoderreihenfolge sonst spiegelverkehrt zur onPC wäre. Die UI lädt
diese Werte direkt in die Auswahl und erlaubt eine Anpassung pro Encoder.

### Temporärer Screen-Modus per MA

Das Mapping-Engine erkennt, ob ein gehaltenes Control als `MA`-Hardkey aufgelöst
ist. Jeder Slot-Encoder merkt sich beim Start eines Delta-Blocks, ob MA gehalten
war (`EncoderState.screen`), und das erzeugte `EncoderSlot`-Action trägt dieses
Flag. Der Client löst damit unabhängig vom globalen `_screen_mode` den
Screen-Namen auf. Wechselt der MA-Zustand zwischen zwei Detents, wird der alte
Block vorher geflusht, damit Attribut- und Screen-Deltas nie in einem Frame
landen. Die Queue coalesciert deshalb getrennt nach `slot` und `screen`.

Die rechte ASL-Taste (`asl_button_3`, Note 11) ist als normaler Key auf den
verifizierten `NIPPLE`-Hardkey (Code 40) gelegt. Sie ist nicht Teil der
MA-Auswertung und wird wie jede andere Hardkey-Taste gesendet.

Alternative: Freie Key-Value-Tabelle. Verworfen, weil die Slots fachlich auf
1–4 begrenzt sind und feste Zeilen die Bedienung vereinfachen.

## Risks / Trade-offs

* **Falsche Namen werden erst an der onPC sichtbar** → Der Editor kennzeichnet
  die Namen als unverifiziert; die Validierung kann nur Syntax und Slotbereich
  prüfen.
* **Merge-Patch löscht nur explizit genullte Slots** → Der Patch erzeugt für
  jeden zuvor vorhandenen, jetzt leeren Slot ein `null`; ein Test prüft das.
* **Auflösungszustand bleibt slot-basiert** → Beim Moduswechsel kann die
  gewählte Stufe erhalten bleiben; das ist konsistent mit dem bisherigen
  Verhalten und wird nicht geändert.

## Migration Plan

Keine Datenmigration. Die Sektion bleibt optional; bestehende Konfigurationen
verhalten sich unverändert, solange sie `screen_encoders` nicht belegen.
