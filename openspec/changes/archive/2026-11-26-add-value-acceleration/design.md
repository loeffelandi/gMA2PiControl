# Design

## Context

Der MIDICRAFT ENC sendet für seine fünf Encoder absolute Werte 0–127
(Notes 60–64), die an 0 und 127 klemmen. Die Auflösung ist fein: Um einen
Executor-Fader über den Web Remote von 0 bis 1 zu bewegen, sind viele
Umdrehungen nötig. Der bestehende Playback-Router sendet den normalisierten
Rohwert direkt als `faderValue`. Für relative Encoder existiert bereits eine
Ratenbeschleunigung im Mapping-Engine; absolute Werte laufen nicht durch
diesen Pfad.

Der Change `add-midicraft-input` hat absolute Werte, Profilfelder
`midi_values` und Playback-Ziele eingeführt. Der Geräte-Tab und das Page-Modell
werden parallel in `add-device-layout-visuals` bearbeitet und bleiben hier
unberührt.

## Goals / Non-Goals

**Goals:**

- Langsame Drehung bleibt exakt 1:1 und feinfühlig.
- Schnelle Drehung verstärkt den Weg, sodass eine kräftige Umdrehung den
  gesamten Faderbereich erreicht.
- Beschleunigung ist je Encoder optional und standardmäßig aus.
- Physische Fader, relative Encoder und Button-Ziele bleiben unverändert.
- Verhalten ist ohne Hardware durch einen injizierbaren Zeitgeber testbar.

**Non-Goals:**

- LED-Feedback, PickUp und Executor-Polling.
- Automatische Erkennung, ob ein Control ein Encoder oder Fader ist; die
  Profilart bleibt die Quelle.
- Einstellen der globalen Kurve in der Oberfläche.
- Änderungen am Geräte-Tab oder am Page-Modell.

## Decisions

### Virtueller Wert statt absoluter Skalierung

Ein absoluter Encoder liefert eine Position, keine Geschwindigkeit. Eine
Beschleunigung ist nur möglich, wenn `ma2pi` die Rohwertänderungen als Deltas
auf einen eigenen virtuellen Wert addiert:

```
virtual = clamp(virtual + (raw - last_raw) * multiplier, 0, 1)
```

Der virtuelle Wert ist der gesendete `faderValue`. Der Rohwert dient nur noch
als Delta-Quelle. Dadurch kann eine schnelle Drehung mehr Weg erzeugen, als die
Rohwertdifferenz hergibt.

Weil `multiplier >= 1` gilt, wächst der virtuelle Wert in Drehrichtung
mindestens so schnell wie der Rohwert. Er erreicht 0.0 beziehungsweise 1.0
spätestens dann, wenn der Rohwert 0 beziehungsweise 127 erreicht. Eine kräftige
Drehung über den mechanischen Gesamtweg deckt damit den vollen Faderbereich ab,
ohne dass ein separater „Boost“-Modus nötig ist.

### Zustand und Lebenszyklus

- Der Zustand wird je Control geführt (`last_raw`, `virtual`, Zeitstempel).
- Das erste Wertereignis nach Router-Erzeugung oder Konfigurationswechsel setzt
  `virtual = raw` und sendet den Rohwert.
- Ein Ereignis ohne Rohwertänderung ändert nichts und sendet nichts.
- Es gibt keinen zeitbasierten Resync. Nach einer Pause läuft die nächste
  Bewegung vom virtuellen Wert weiter; das Fenster ist dann leer und der
  Multiplikator 1.0.
- Ein Konfigurationswechsel verwirft alle Zustände.
- Ein Geräte-Reconnect ohne Konfigurationswechsel wird nicht erkannt; der
  nächste Wert kann einen Sprung erzeugen. Das ist ohne PickUp bereits eine
  bekannte Einschränkung.

### Ratenfenster und Kurve

Die Rate ist die Anzahl der Wertänderungen desselben Controls innerhalb der
letzten `window` Sekunden, einschließlich des aktuellen Ereignisses.
Unveränderte Wiederholungen zählen nicht, damit ein Gerät, das seinen Wert
periodisch wiederholt, die Beschleunigung nicht auslöst.

Mit `t = clamp((rate - slow_rate) / (fast_rate - slow_rate), 0, 1)` gilt:

| `curve` | Multiplikator |
|---|---|
| `none` | `1.0` |
| `linear` | `1 + (max_multiplier - 1) * t` |
| `exponential` | `max_multiplier ** t` |

Bei `rate <= slow_rate` ist `t = 0`, bei `rate >= fast_rate` ist `t = 1`.
Der Multiplikator wird zusätzlich auf `[1, max_multiplier]` geklemmt.

Standardwerte: `curve = "linear"`, `window = 0.12`, `slow_rate = 2`,
`fast_rate = 10`, `max_multiplier = 8.0`. Bei einer Rate von 10 Rasten pro
0,12 s (etwa 83 Rasten/s) ist die Verstärkung voll. Eine langsame Drehung mit
zwei oder weniger Änderungen pro Fenster bleibt 1:1.

### Ablage in der Konfiguration

Das Opt-in liegt am Playback-Ziel, nicht am Geräteprofil:

```toml
[mapping.playbacks.mc_encoder_1]
page = "current"
executor = 1
kind = "fader"
accelerated = true
```

Gründe:

- Der Mapping-Editor bearbeitet bereits `[mapping.playbacks]`; es ist kein
  neuer Schreibpfad und kein Eingriff in den Geräte-Tab nötig.
- Die Beschleunigung ist eine Eigenschaft der Wertübertragung an einen
  Executor-Fader, nicht der physischen Taste.
- Ein Control hat genau ein Playback-Ziel; damit ist das Flag eindeutig pro
  Encoder.

Die Validierung prüft zusätzlich die Profilart: `accelerated` ist nur erlaubt,
wenn das Control im Profil `kind = "encoder"` hat und das Ziel
`kind = "fader"` ist. Physische Fader werden so auch bei einem Fehler in der
Konfiguration nicht beschleunigt.

### Ort der Berechnung

Die Beschleunigung gehört in den `PlaybackRouter`, nicht in den Frame-Builder
oder den MA-Client:

- Der Router sieht normalisierte Werte und das Playback-Ziel.
- Der Frame-Builder bleibt ein reiner Abbildner von Wert auf `faderValue`.
- Der Client bleibt für Queueing und Coalescing zuständig.
- Die Beschleunigung läuft vor Klemmung und Dedupe, damit der gesendete Wert
  exakt der virtuelle Wert ist.

Ein neues Modul `ma2pi/acceleration.py` enthält
`ValueAccelerationSettings`, die Kurvenfunktion und einen kleinen
`ValueAccelerator` mit dem Zustand je Control. Die bestehende
Relativ-Encoder-Beschleunigung in `ma2pi/mapping.py` bleibt unverändert; sie
hat eine andere Semantik (Rasten pro Fenster, feste Zielauflösung) und wird
nicht in das neue Modul gezwungen.

## Alternatives Considered

### Fester Multiplikator je Encoder

Einfach, aber zerstört die feine Kontrolle bei langsamer Drehung. Verworfen.

### Absolute Position direkt skalieren

Eine Kennlinie auf den Rohwert kann den maximalen Weg nicht vergrößern, weil
der Rohwert bei 127 endet. Verworfen.

### Delta pro Ereignis statt Rate

Die Delta-Größe hängt von der Ereignisdichte und vom Gerät ab und schwankt
stark. Die Rate über ein Zeitfenster ist stabiler und entspricht eher dem
Gefühl „schnell drehen“. Verworfen.

### Flag im Geräteprofil

Semantisch näher am Encoder, würde aber den parallel bearbeiteten Geräte-Tab
und das Profilschema ändern. Das mappingseitige Flag hält diesen Change
unabhängig. Eine spätere Migration in den Geräte-Tab bleibt möglich.

### Beschleunigung im Frame-Builder

Der Frame-Builder müsste Zustand und Zeit führen und wäre nicht mehr rein.
Verworfen.

## Risks / Trade-offs

- **Virtueller Wert driftet vom Rohwert.** Nach einer schnellen Drehung stimmt
  die Knopfposition nicht mehr mit dem gesendeten Wert überein. Das ist der
  Preis der Beschleunigung und ohne PickUp bewusst akzeptiert.
- **Rücksprung nach Neustart oder Konfigurationswechsel.** Der nächste Wert
  springt auf die Rohposition. Bekannt aus dem bestehenden Verhalten ohne
  PickUp.
- **Gerät mit Wrap statt Klemmung.** Gemessen ist Klemmung an 0/127. Ein
  Wrap von 127 auf 0 würde als großer Rückwärtsschritt verstärkt. Das wird in
  diesem Change nicht behandelt; bei beobachtetem Wrap ist ein eigener
  Resync-Fall nachzuziehen.
- **Abstimmung der Standardwerte.** Rasten pro Umdrehung und Ereignisrate sind
  gerätespezifisch. Die Werte sind konfigurierbar; die Hardware-Abnahme prüft,
  ob eine kräftige Umdrehung tatsächlich den vollen Weg schafft.
- **Ereignis-Coalescing.** Bei sehr hohen Raten kann ALSA Ereignisse
  zusammenfassen; dann sinkt die gemessene Rate. `fast_rate` ist entsprechend
  einstellbar.

## Migration / Rollout

Keine Migration nötig. Ohne `accelerated` bleibt das Verhalten identisch.
Bestehende Konfigurationen bleiben gültig. Der Beispielabschnitt
`[mapping.value_acceleration]` und ein beschleunigtes Encoder-Ziel werden in
`config.toml` dokumentiert, aber nicht automatisch in Live-Konfigurationen
geschrieben.

## Open Questions

- Entspricht eine kräftige Umdrehung am ENC eher 10 oder eher 20 Rasten pro
  0,12 s? Die Standardwerte `slow_rate = 2`, `fast_rate = 10` sind eine
  Annahme und werden bei der Hardware-Abnahme geprüft.
- Soll die globale Kurve später im Advanced-Tab einstellbar werden? In diesem
  Change bleibt sie in der Konfigurationsdatei.
