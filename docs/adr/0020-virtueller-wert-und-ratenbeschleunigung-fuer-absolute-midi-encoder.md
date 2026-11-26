# 0020. Virtueller Wert und Ratenbeschleunigung für absolute MIDI-Encoder

* Datum: 2026-11-26
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Related to [0019. Absolute MIDI-Werte und Executor-Ziele über den Web Remote](0019-absolute-midi-werte-und-executor-ziele-ueber-den-web-remote.md)

## Kontext und Problemstellung

Der MIDICRAFT ENC sendet für seine fünf Encoder absolute Positionen 0–127.
Diese feine Auflösung ist für präzise Werte gut, aber für einen Executor-Fader
unpraktisch: Der volle Weg erfordert viele Umdrehungen. Der Playback-Router
sendet den normalisierten Rohwert derzeit direkt als `faderValue`. Für relative
Encoder existiert bereits eine Ratenbeschleunigung in der Mapping-Engine;
absolute Werte laufen nicht durch diesen Pfad.

Gewünscht ist: langsame Drehung bleibt 1:1 und feinfühlig, eine kräftige
Umdrehung bewegt den Fader über den vollen Bereich. Die Beschleunigung soll je
Encoder optional sein; physische Fader und relative Encoder bleiben unverändert.

## Entscheidungstreiber

* Feine Kontrolle bei langsamer Drehung erhalten
* Schnelle Drehung soll den vollen Faderbereich erreichen
* Beschleunigung pro Encoder ein- und ausschaltbar
* Keine Änderung an MIDI-Protokoll, Frame-Format oder MA-Konfiguration
* Physische Fader und bestehende Relativ-Encoder nicht verändern
* Verhalten ohne Hardware durch injizierbare Zeit testbar
* Kein Eingriff in den parallel bearbeiteten Geräte-Tab

## Betrachtete Optionen

* Fester Multiplikator je Encoder
* Kennlinie auf den absoluten Rohwert
* Delta pro Ereignis statt Rate über ein Zeitfenster
* Ratenbeschleunigung auf einen virtuellen Wert (gewählt)
* Flag im Geräteprofil statt am Playback-Ziel

## Entscheidung

Der Playback-Router führt je beschleunigtem Control einen virtuellen Wert. Das
erste Wertereignis setzt ihn auf den normalisierten Rohwert. Danach gilt:

```
virtual = clamp(virtual + (raw - last_raw) * multiplier, 0, 1)
```

Der virtuelle Wert wird als `faderValue` gesendet; der Rohwert dient nur noch
als Delta-Quelle. Die Rate ist die Anzahl der Wertänderungen desselben Controls
innerhalb der letzten `window` Sekunden, unveränderte Wiederholungen zählen
nicht. Der Multiplikator ist bei `rate <= slow_rate` genau 1.0 und erreicht bei
`rate >= fast_rate` höchstens `max_multiplier`; die Kurve ist linear oder
exponentiell.

Das Opt-in `accelerated = true` steht am Playback-Ziel mit `kind = "fader"` und
ist nur für Controls erlaubt, die im Profil `kind = "encoder"` haben. Default
ist `false`. Der Mapping-Editor zeigt dafür eine Checkbox. Die globale Kurve
steht in `[mapping.value_acceleration]` und bleibt in der Konfigurationsdatei.

Die Berechnung liegt im `PlaybackRouter` vor Klemmung und Dedupe. Ein separates
Modul `ma2pi/acceleration.py` enthält Kurve und Zustand. Die bestehende
Relativ-Encoder-Beschleunigung bleibt unverändert.

Weil der Multiplikator mindestens 1.0 beträgt, erreicht der virtuelle Wert die
Grenzen 0.0/1.0 spätestens dann, wenn der Rohwert 0/127 erreicht. Eine kräftige
Drehung über den mechanischen Gesamtweg deckt damit den vollen Faderbereich ab.

### Konsequenzen

* Gut, weil langsame Drehungen exakt 1:1 bleiben und schnelle Drehungen
  spürbar mehr Weg erzeugen.
* Gut, weil das Opt-in pro Encoder möglich ist, ohne physische Fader oder
  relative Encoder zu beeinflussen.
* Gut, weil Frame-Format und MA-Konfiguration unverändert bleiben.
* Gut, weil die Kurve ohne Hardware mit einem injizierten Zeitgeber geprüft
  werden kann.
* Schlecht, weil der virtuelle Wert nach einer schnellen Drehung von der
  physischen Knopfposition abweicht.
* Schlecht, weil ohne PickUp ein Neustart, ein Konfigurationswechsel oder ein
  Geräte-Reconnect einen Wertesprung am Executor auslösen kann.
* Schlecht, weil die Standardwerte von der Rastenzahl und Ereignisrate des
  Geräts abhängen und nachjustiert werden müssen.
* Schlecht, weil ein Encoder mit Wrap statt Klemmung als großer
  Rückwärtsschritt verstärkt würde; das ist nicht Teil dieser Entscheidung.

### Bestätigung

Accepted, wenn am Pi eine langsame Drehung den Fader fein und 1:1 bewegt, eine
kräftige Umdrehung den vollen Bereich erreicht, ein Encoder ohne Opt-in
unverändert bleibt und die physischen Fader sowie relativen Encoder kein
geändertes Verhalten zeigen.

## Vor- und Nachteile der Optionen

### Fester Multiplikator je Encoder

* Gut, weil einfach zu implementieren und zu erklären.
* Schlecht, weil langsame Drehungen die feine Kontrolle verlieren.

### Kennlinie auf den absoluten Rohwert

* Gut, weil kein Zustand nötig wäre.
* Schlecht, weil der Rohwert bei 127 endet und der maximale Weg nicht wachsen
  kann.

### Delta pro Ereignis statt Rate

* Gut, weil kein Zeitfenster nötig wäre.
* Schlecht, weil die Delta-Größe von Ereignisdichte und Gerät abhängt und stark
  schwankt.

### Ratenbeschleunigung auf einen virtuellen Wert

* Gut, weil langsam und schnell getrennt steuerbar sind und der volle Weg
  erreichbar bleibt.
* Schlecht, weil ein Zustand je Control nötig ist und der Wert vom Rohwert
  abweichen kann.

### Flag im Geräteprofil

* Gut, weil die Beschleunigung semantisch zum Encoder gehört.
* Schlecht, weil dafür der parallel bearbeitete Geräte-Tab und das Profilschema
  geändert werden müssten. Das Flag am Playback-Ziel hält den Change
  unabhängig; eine spätere Migration bleibt möglich.

## Weitere Informationen

* Verwandt: ADR-0019 (absolute MIDI-Werte und Executor-Ziele)
* Change: `add-value-acceleration`
* Messung: Encoder-Notes 60–64, absolut 0–127, an 0/127 geklemmt
