# value-acceleration Specification

## Purpose

Beschreibt, wie absolute Encoderwerte optional beschleunigt werden: langsame
Drehung bleibt 1:1, schnelle Drehung verstärkt die Wertänderung über einen
virtuellen Wert. Die Beschleunigung ist je Control einschaltbar und wirkt nur
auf Fader-Ziele des Playback-Routers.

## Requirements

### Requirement: Beschleunigung nur auf Opt-in

Ein Playback-Ziel SHALL das optionale Feld `accelerated` tragen. Es MUST nur
bei `kind = "fader"` und nur für ein Control erlaubt sein, dessen Eintrag im
Geräteprofil `kind = "encoder"` hat. Ohne Angabe MUST `accelerated = false`
gelten. Physische Fader, relative Encoder und Controls ohne Playback-Ziel
MUST unverändert bleiben.

#### Scenario: Absoluter Encoder ist eingeschaltet

- **WHEN** ein Control im Profil `kind = "encoder"` hat und sein Fader-Ziel
  `accelerated = true` setzt
- **THEN** wird sein Wert beim Senden an den Executor beschleunigt

#### Scenario: Default ist aus

- **WHEN** ein Fader-Ziel kein `accelerated` angibt
- **THEN** wird der Rohwert unverändert gesendet

#### Scenario: Physischer Fader

- **WHEN** ein Control im Profil `kind = "fader"` hat und sein Playback-Ziel
  `accelerated = true` setzt
- **THEN** lehnt `ma2pi` die Konfiguration mit einer Meldung ab, die Control
  und Feld nennt

#### Scenario: Button-Ziel

- **WHEN** ein Playback-Ziel `kind = "button"` hat und `accelerated` setzt
- **THEN** lehnt `ma2pi` die Konfiguration ab

#### Scenario: Relativer Encoder

- **WHEN** ein relativer Encoder über die bestehende Encoder-Zuordnung
  verarbeitet wird
- **THEN** ändert die Wert-Beschleunigung sein Verhalten nicht

### Requirement: Virtueller Wert aus Rohwertänderungen

Der Playback-Router SHALL je beschleunigtem Control einen virtuellen Wert
führen. Das erste Wertereignis nach Router-Erzeugung oder Konfigurationswechsel
MUST ihn auf den normalisierten Rohwert setzen und diesen senden. Jedes weitere
Ereignis MUST die Differenz zum zuletzt gesehenen Rohwert mit dem
Raten-Multiplikator verstärken und zum virtuellen Wert addieren.

#### Scenario: Langsame Drehung bleibt 1:1

- **WHEN** aufeinanderfolgende Werte 0.0, 1/127 und 2/127 mit mehr als
  `window` Abstand eintreffen
- **THEN** sendet `ma2pi` 0.0, 1/127 und 2/127 ohne Verstärkung

#### Scenario: Schnelle Drehung wird verstärkt

- **WHEN** mehrere Wertänderungen innerhalb von `window` eintreffen
- **THEN** ist die Änderung des gesendeten Werts größer als die Rohwertänderung

#### Scenario: Erster Wert nach dem Start

- **WHEN** das erste Wertereignis den Rohwert 0.4 liefert
- **THEN** sendet `ma2pi` 0.4 und verwendet ihn als Ausgangspunkt

#### Scenario: Kurze schnelle Bewegung

- **WHEN** der Rohwert nur um wenige Schritte steigt und die Drehung dann stoppt
- **THEN** bleibt der virtuelle Wert auf dem verstärkten Zwischenwert stehen und
  wird nicht zurückgesetzt

### Requirement: Klemmung und unveränderte Werte

Der virtuelle Wert MUST auf 0.0–1.0 begrenzt werden. Eine Differenz von 0 MUST
keinen neuen Wert und keinen Frame erzeugen. Ein Konfigurationswechsel MUST
alle virtuellen Werte verwerfen.

#### Scenario: Klemmung am Bereichsende

- **WHEN** die verstärkte Änderung über 1.0 hinausführt
- **THEN** sendet `ma2pi` höchstens 1.0; weitere positive Änderungen bleiben bei
  1.0, bis die Drehrichtung wechselt

#### Scenario: Unveränderter Rohwert

- **WHEN** ein Ereignis denselben Rohwert wie zuletzt liefert
- **THEN** sendet `ma2pi` keinen weiteren Frame und der virtuelle Wert bleibt
  unverändert

#### Scenario: Konfigurationswechsel

- **WHEN** eine neue Konfiguration angewendet wird
- **THEN** verwirft der Router alle virtuellen Werte und das nächste Ereignis
  setzt den virtuellen Wert wieder auf den Rohwert

### Requirement: Vollständiger Weg bei kräftiger Drehung

Der Multiplikator MUST mindestens 1.0 betragen. Dadurch MUST der virtuelle Wert
in Drehrichtung mindestens so weit laufen wie der Rohwert. Erreichen des
Rohbereichs 0 beziehungsweise 127 MUST spätestens dann auch den virtuellen
Bereich 0.0 beziehungsweise 1.0 erreichen. Eine kräftige Drehung über den
gesamten mechanischen Weg SHALL daher den vollen Faderbereich abdecken.

#### Scenario: Kräftige Drehung nach oben

- **WHEN** der Rohwert in kleinen Schritten schnell von 0 bis 127 steigt
- **THEN** erreicht der gesendete Wert spätestens beim Rohwert 127 den Wert 1.0

#### Scenario: Kräftige Drehung nach unten

- **WHEN** der Rohwert in kleinen Schritten schnell von 127 bis 0 fällt
- **THEN** erreicht der gesendete Wert spätestens beim Rohwert 0 den Wert 0.0

### Requirement: Ratenfenster

Die Rate MUST die Anzahl der Wertänderungen des Controls innerhalb der letzten
`window` Sekunden einschließlich des aktuellen Ereignisses sein. Unveränderte
Wiederholungen MUST nicht zählen. `window` MUST größer 0 sein; ein Verstoß MUST
die Konfiguration mit Angabe des Feldes ablehnen.

#### Scenario: Nur Änderungen zählen

- **WHEN** ein Control innerhalb von `window` zwei geänderte Werte und mehrere
  unveränderte Wiederholungen sendet
- **THEN** beträgt die Rate 2

#### Scenario: Fenster ist abgelaufen

- **WHEN** die letzte Wertänderung länger als `window` zurückliegt
- **THEN** beträgt die Rate 1 und der Multiplikator 1.0

#### Scenario: Ungültiges Fenster

- **WHEN** `window <= 0` konfiguriert ist
- **THEN** lehnt `ma2pi` die Konfiguration ab und nennt das Feld

### Requirement: Multiplikatorkurve

Die Konfiguration SHALL `[mapping.value_acceleration]` mit `curve`
(`none`, `linear`, `exponential`), `slow_rate`, `fast_rate` und
`max_multiplier` erlauben. Bei `rate <= slow_rate` MUST der Multiplikator 1.0
sein, bei `rate >= fast_rate` MUST er `max_multiplier` sein. `linear` verläuft
geradlinig zwischen den Endpunkten, `exponential` ist `max_multiplier` hoch dem
normierten Fortschritt, `none` ist immer 1.0.

#### Scenario: Lineare Kurve

- **WHEN** `curve = "linear"`, `slow_rate = 2`, `fast_rate = 10` und
  `max_multiplier = 8` gilt und die Rate 6 beträgt
- **THEN** ist der Multiplikator 4.5

#### Scenario: Exponentielle Kurve

- **WHEN** `curve = "exponential"` und dieselben Grenzen gelten und die Rate 6
  beträgt
- **THEN** ist der Multiplikator 8^(4/8), also etwa 2.83

#### Scenario: Keine Beschleunigung

- **WHEN** `curve = "none"` gilt
- **THEN** ist der Multiplikator unabhängig von der Rate 1.0

### Requirement: Validierung der Beschleunigung

`max_multiplier` MUST mindestens 1, `slow_rate` mindestens 1 und `fast_rate`
größer als `slow_rate` sein. Verstöße MUST die Konfiguration mit Angabe des
Feldes ablehnen.

#### Scenario: Ungültige Multiplikatorgrenze

- **WHEN** `max_multiplier < 1` konfiguriert ist
- **THEN** lehnt `ma2pi` die Konfiguration ab und nennt `max_multiplier`

#### Scenario: Ungültige Raten

- **WHEN** `slow_rate < 1` oder `fast_rate <= slow_rate` konfiguriert ist
- **THEN** lehnt `ma2pi` die Konfiguration ab und nennt das fehlerhafte Feld

### Requirement: Standardwerte

Ohne eigenen Abschnitt MUST `curve = "linear"`, `window = 0.12`,
`slow_rate = 2`, `fast_rate = 10` und `max_multiplier = 8.0` gelten. Die
Standardwerte MUST auch dann greifen, wenn ein Control `accelerated = true`
setzt, ohne dass `[mapping.value_acceleration]` existiert.

#### Scenario: Nur das Control ist eingeschaltet

- **WHEN** ein Encoder-Ziel `accelerated = true` setzt und der Abschnitt
  `[mapping.value_acceleration]` fehlt
- **THEN** verwendet `ma2pi` die Standardwerte und beschleunigt das Control

#### Scenario: Abschnitt ohne einzelne Felder

- **WHEN** der Abschnitt nur `max_multiplier = 4` setzt
- **THEN** bleiben `curve`, `window`, `slow_rate` und `fast_rate` auf ihren
  Standardwerten
