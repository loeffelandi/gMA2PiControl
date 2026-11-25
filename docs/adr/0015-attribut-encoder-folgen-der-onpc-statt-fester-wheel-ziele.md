# 0015. Attribut-Encoder folgen der onPC statt fester Wheel-Ziele

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Ergänzt [0002. Wheel- und Encoder-Strategie](0002-wheel-und-encoder-strategie.md)

## Kontext und Problemstellung

Der ursprüngliche Plan aus ADR-0002 mappte die vier ASL-Encoder auf Wheel-Ziele
(`Feature $feature.N At …`) und hielt einen eigenen Bankzähler, den eine Taste
weiterdrehte. Zwei Dinge stimmten damit nicht:

1. Die von onPC ausgelieferte Web-Remote-JS kennt **keine** Wheel-Frames. Sie
   sendet ausschließlich `{"requestType":"encoder","name":"<Attribut>","value":…}`
   und für Auflösungswechsel `{"requestType":"encoder","name":…,"resolution":0|1|2}`.
   Ein Live-Mitschnitt bestätigte das Format (`PAN`, `TILT`, `DIM`, …).
2. In der onPC blättert man innerhalb eines Attributs (z. B. `Shapers`) durch
   weitere Encoder. Ein lokaler Bankzähler läuft dazu aus dem Tritt: Die
   physischen Encoder zeigen etwas anderes als der Bildschirm.

Zusätzlich gibt es in der onPC Screen-Encoder, die je nach Fokus für den
aktuellen Screen gelten. Der Benutzer möchte diese auf eine Taste legen und den
aktiven Modus über eine LED sehen (grün = Screen, rot = Attribut).

## Entscheidungstreiber

* Physische Encoder müssen zeigen, was die onPC zeigt.
* Nur verifizierte Frames senden (keine geratenen Wheel-Formate).
* Ein klarer, umschaltbarer Screen-Modus statt eines zweiten Bankzählers.
* Zustand muss im UI und an der LED sichtbar sein.

## Betrachtete Optionen

* Lokaler Bankzähler wie bisher (verworfen: läuft der onPC hinterher)
* Wheel-Ziele über CMD-Wrapper (verworfen: nicht das, was die onPC tut)
* Attribut-Fenster aus `presetTypes` ableiten (gewählt)
* Screen-Encoder über zusätzliche Wheel-Nummern (verworfen: kein Beleg im Protokoll)

## Entscheidung

Der Daemon liest die `presetTypes`-Antwort der onPC und leitet den sichtbaren
4er-Block aus dem **selektierten** Attribut ab:
`window_start = (selected_index // 4) * 4`. Die Encoder-Slots 1–4 adressieren
genau diesen Block. Die Seite wird jede Sekunde neu abgefragt
(`page_refresh_interval`), weil die onPC Auswahländerungen nicht zuverlässig
pusht.

Gesendet wird ausschließlich der native Frame
`{"requestType":"encoder","name":"<Attribut>","value":<Delta>}`. Ein Klick auf
einen Encoder zyklisiert dessen Auflösung Normal (0) → Fine (1) → Ultra (2) →
Normal (0) und sendet dazu einen eigenen Frame ohne `value`.

Eine konfigurierte Taste (`screen_mode = true`) schaltet zwischen Attribut- und
Screen-Encodern um. Die Namen der Screen-Encoder stehen in
`[mapping.screen_encoders]` (Slots 1–4). Fehlt die Sektion, bleibt der
Attribut-Modus aktiv und es wird gewarnt. Der aktive Modus steht als
`screen_mode` im Status; daraus leitet die Oberfläche den LED-Zustand ab
(grün = Screen, rot = Attribut).

### Konsequenzen

* Gut, weil die Encoder dem Bildschirm folgen, ohne dass jemand synchronisiert.
* Gut, weil nur das verifizierte native Format gesendet wird.
* Gut, weil der Screen-Modus explizit und notfalls abschaltbar ist.
* Schlecht, weil die onPC jede Sekunde abgefragt wird (geringe Last im LAN).
* Schlecht, weil die Screen-Encoder-Namen noch nicht verifiziert sind; ohne
  Konfiguration bleibt der Modus wirkungslos.
* Schlecht, weil die physische LED-Ansteuerung des ASL noch einen Mitschnitt
  des MIDI-LED-Protokolls braucht (Task 5.8).

### Bestätigung

Accepted, wenn das Attribut-Fenster bei Live-Umschaltung in der onPC innerhalb
einer Sekunde mitgeht, die drei Auflösungsstufen immediat greifen und der
Screen-Modus mit verifizierten Encoder-Namen Frames erzeugt. Bis dahin bleibt
der Status Proposed.

## Vor- und Nachteile der Optionen

### Attribut-Fenster aus `presetTypes` (gewählt)

* Gut, weil die Daten direkt von der onPC kommen.
* Gut, weil derselbe Poll auch Feature- und Preset-Wechsel abdeckt.
* Schlecht, weil die Antwort größer ist als ein einzelner Frame.

### Lokaler Bankzähler

* Gut, weil kein Polling nötig wäre.
* Schlecht, weil er nach jedem onPC-Wechsel manuell nachgezogen werden müsste.
* Schlecht, weil Taste und Bildschirm auseinanderlaufen.

### Wheel-Ziele über CMD-Wrapper

* Gut, weil es ohne Capture funktioniert.
* Schlecht, weil die onPC damit nicht dasselbe tut wie ihre eigenen Encoder.
* Schlecht, weil Attribute und Wheels unterschiedlich skaliert sind.

## Weitere Informationen

* Mitschnitt: `{"requestType":"encoder","name":"PAN","value":7.18}`,
  Auflösung `{"requestType":"encoder","name":"PAN","resolution":2}`
* Verwandt: ADR-0002 (Wheel-/Encoder-Strategie), ADR-0005 (Rate-Limiting),
  ADR-0014 (ASL als MIDI-Gerät)
