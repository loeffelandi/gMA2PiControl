# 22. Geraete-Baenke als MIDI-Kanaele und Bank-Offset

* Datum: 2026-11-26
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

References [0014. ASL MK2 E4B3 als MIDI-Gerät hinter der Input-Schnittstelle](0014-asl-mk2-e4b3-als-midi-geraet-hinter-der-input-schnittstelle.md)

References [0019. Absolute MIDI-Werte und Executor-Ziele über den Web Remote](0019-absolute-midi-werte-und-executor-ziele-ueber-den-web-remote.md)

## Kontext und Problemstellung

Die MIDICRAFT-Controller belegen bis zu 16 Bänke. Ein Bankwechsel ändert am
Gerät den MIDI-Kanal und die Notenbelegung gemeinsam; der Wechsel selbst sendet
kein Ereignis. Die Noten sind frei einstellbar, unterscheiden sich also je Gerät
und Bank. Gleichzeitig sollen Bänke ohne manuelle Umbauten auf derselben
MA-Page nutzbar sein, ohne für jede Bank ein eigenes Mapping-Duplikat zu pflegen.

## Entscheidungstreiber

* Bänke müssen ohne zusätzliches Geräte-Event erkennbar bleiben.
* Dieselbe Note darf auf verschiedenen Bänken vorkommen.
* Bestehende Profile ohne Bänke müssen unverändert gültig bleiben.
* Bänke sollen standardmäßig auf der aktuellen MA-Page verteilt werden, ein
  MA-Page-Wechsel bleibt aber konfigurierbar.
* Mapping-Daten sollen nur Abweichungen enthalten, nicht 16 Kopien.

## Betrachtete Optionen

* Bank ausschließlich über die Note bestimmen.
* Bank über Kanal und Note bestimmen, Editorauswahl separat.
* Jede Bank auf eine eigene MA-Page legen.

## Entscheidung

Eine Bank besteht aus einem eindeutigen MIDI-Kanal und einer Notenbelegung. Der
Kanal wird je Profil eindeutig vergeben (Default = Banknummer). Ereignisse werden
zuerst über den Kanal der Bank und dann über die Note dem Control zugeordnet.
Die Bank wird beim Lernen und Mappen zusätzlich explizit in der Oberfläche
gewählt; diese Auswahl ist reiner Editorzustand und wird nicht an Gerät oder MA
gesendet. Dieselbe Note ist damit auf verschiedenen Bank-Kanälen zulässig.

Mappings liegen als Overlay in `[mapping.device_banks.<device>]`. Fehlt ein
Eintrag, wird das globale Ziel verwendet und die Executor-Nummer um
`(bank - 1) * bank_size` verschoben. Nur Executor-Ziele werden verschoben;
Button-Nummern bleiben unverändert. Ist für eine Bank eine MA-Page hinterlegt,
entfällt der Offset und der Daemon sendet beim ersten Ereignis dieser Bank
einmalig `Page <n>`.

### Konsequenzen

* Gut, weil dieselbe physische Fläche für alle Bänke gilt und nur die Belegung
  je Bank variiert.
* Gut, weil Bänke ohne eigene MA-Page auf derselben Page nutzbar sind.
* Gut, weil bestehende Profile ohne Bänke als Bank 1 auf Kanal 1 weiterlaufen.
* Schlecht, weil Noten über Kanäle hinweg eindeutig bleiben müssen und die
  Kanalvergabe Teil der Profilpflege ist.
* Schlecht, weil ein Bankwechsel erst mit dem nächsten Bedienvorgang sichtbar
  wird; eine „aktive Bank“ kann nicht angezeigt werden.

### Bestätigung

Die Hardware-Abnahme zeigt für den MIDICRAFT ENC: Bank 2 sendet auf Kanal 2,
Encoder-Klick 1 als Note 0 und Fader 1 als Note 15; der Bank-Offset erreicht
Executor 6–10 und eine hinterlegte MA-Page schaltet genau einmal.

## Vor- und Nachteile der Optionen

### Option A: Bank nur über die Note

* Gut, weil kein Kanalmodell nötig wäre.
* Schlecht, weil dieselbe Note auf mehreren Bänken vorkommen kann und dann
  nicht mehr eindeutig zuordenbar ist.

### Option B: Kanal und Note, Editorauswahl separat

* Gut, weil der Kanal die Bänke eindeutig trennt und die UI unabhängig bleibt.
* Schlecht, weil Kanal und Note gemeinsam gepflegt werden müssen.

### Option C: Jede Bank auf eine MA-Page

* Gut, weil die MA-Struktur die Bänke direkt abbildet.
* Schlecht, weil ein Wechsel der MA-Page Nebenwirkungen auf andere Controller
  hat und der Benutzer die Bänke bewusst auf einer Page verteilen will.

## Weitere Informationen

* Change: `add-device-layout-visuals`
* Verwandt: ADR 0014 (ASL als MIDI-Gerät), ADR 0019 (absolute MIDI-Werte und
  Executor-Ziele über den Web Remote)
