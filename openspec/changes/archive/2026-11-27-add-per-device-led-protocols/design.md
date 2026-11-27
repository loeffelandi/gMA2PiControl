# Design

## Context

Siehe `proposal.md` (Why). Ausgangslage im Code:

- `ma2pi/feedback.py` kennt eine Palette mit 13 Farben, `MODE_BASE`
  (`dark = 1`, `bright = 15`) und sendet je LED ein `90 <Note> <Velocity>`.
  Die Ausgabe-Queue je Gerät (aus `fix-midicraft-led-output`) speichert je
  Note eine Velocity und vergleicht gegen `_last`.
- `ma2pi/led_output.py` (`LedOutput`) öffnet den ASL-Port selbst mit
  `O_WRONLY`, sendet beim Öffnen `9F 7F 7F`, je LED Freigabe plus zwei Note-On
  und beim Schließen `9F 7F 7E`. Es erkennt einen Replug über den Inode-
  Vergleich (`still_attached`).
- Weil `LedOutput` den Port hält, öffnet `MidiManager` die ASL nur lesend
  (Journal: „lässt sich nicht duplex öffnen … Device or resource busy;
  Ausgabe deaktiviert“). Ein Feedback-Frame an die ASL über `MidiManager.send`
  würde heute verworfen.
- `[led]` belegt die Noten 9 (Modus), 10 (Fine) und 11 (Nipple). Das sind alle
  drei Tasten der ASL mit LED; die Encoder-Klicks 5–8 haben laut Profil keine
  LED-Deklaration.
- Gemessen am 2026-11-26: Velocity 15 zeigt am ENC weiß-hellblau (CTB). Das
  offizielle Plugin (`test.lua`, v1.3) nennt die Farbreihenfolge white, red,
  orange, yellow, ferngreen, green, seagreen, cyan, lavender, blue, violet,
  magenta, pink, CTO, CTB und die Basen 1 (dunkel), 17 (hell), 33, 49, 65.
- Die Capability `executor-feedback` existiert nur im nicht archivierten
  Change `add-midicraft-led-feedback`.

## Goals / Non-Goals

**Goals:**

- Die Kodierung eines LED-Zustands hängt nur am Profil-Protokoll; Feedback-
  Logik (Polling, Farbe, Takt, Stau) bleibt protokollunabhängig.
- Ein Gerät hat genau einen geöffneten Port, über den Eingabe, `[led]` und
  Feedback laufen.

**Non-Goals:**

- Farbabgleich der ASL über die drei geprüften Indizes hinaus ohne Messung.
- Ein allgemeines Plugin-System für Protokolle; zwei feste Kodierungen reichen.

## Decisions

### D1: `midicraft-v2` an Ort und Stelle korrigieren

Die Kodierung von `midicraft-v2` wird auf das gemessene Layout umgestellt
(`1 + Index`, `17 + Index`, 15 Farben). Bestehende Konfigurationen (Repo und
Pi) bleiben gültig und senden danach richtige Werte.

*Alternative:* neues Protokoll `midicraft-fw2` und `midicraft-v2`
unverändert lassen. Verworfen: Das alte Layout ist an keinem Gerät belegt, es
bliebe als Voreinstellung eine bekannte Fehlerquelle, und jede bestehende
Konfiguration müsste angefasst werden.

### D2: Kodierer je Protokoll

Je Protokoll gibt es einen Kodierer mit drei Aufgaben:

1. `state(running, color, off_state) → LedState` — ein vergleichbarer Wert
   (Midicraft: Velocity; ASL: Paar aus Helligkeit und Index). Queue und
   `_last` speichern `LedState` statt Velocity; Ersetzen und Deduplizieren
   bleiben unverändert.
2. `frame(note, state) → bytes` — ein Frame, der als Ganzes geschrieben wird
   (Midicraft 3 Bytes; ASL 6 Bytes: Kanal 1 Helligkeit, Kanal 2 Index).
3. `preamble() → bytes` — einmal vor dem ersten Frame nach jedem Öffnen
   (Midicraft leer; ASL `9F 7F 7F`).

Der Kodierer wird beim Bilden der LED-Ziele aus dem Profil gewählt. Der Takt
zählt Frames, nicht Bytes; ein ASL-Frame ist damit ein Takt.

*Alternative:* Freigabe vor jedem ASL-Frame mitsenden wie `LedOutput.set_button`
(9 Bytes). Verworfen für Feedback: Die Freigabe ändert keinen Zustand, und
kürzere Frames schonen die Firmware. `LedOutput` behält sein Verhalten.

### D3: Ein Port je Gerät, `MidiManager` besitzt ihn

`MidiManager` öffnet jedes Gerät duplex und bleibt alleiniger Besitzer.
`LedOutput` schreibt über `MidiManager.send`.

*Stand beim Apply (2026-11-26):* Das war bereits umgesetzt, ohne Rückrufe in
`MidiManager`: `_led_step` läuft jede Sekunde und bei jeder Config-Aktivierung,
erkennt einen Replug über `open_generations` und baut `LedOutput` dann neu auf
(`9F 7F 7F`, Modus, Fine, Nipple). Der Shutdown sendet `9F 7F 7E`, bevor der
MIDI-Task die Handles schließt. Das Feedback erkennt dieselben Generationen in
`_sync_devices` und sendet danach Präambel und Vollzustand.

Ergänzt wird nur der umgekehrte Fall: Baut `_led_step` `LedOutput` neu auf
oder schaltet `[led]` ab, geht vorher `9F 7F 7E` hinaus, und die ASL kann
dabei auch Feedback-LEDs zurücksetzen. `_led_step` meldet das Gerät deshalb
über `on_release` an `ExecutorFeedback.resend_device`, das den Gerätezustand
verwirft und im nächsten Zyklus vollständig neu sendet.

`[led]`-Frames umgehen die Feedback-Queue und gehen sofort hinaus (Tasten-
Rückmeldung beim Drücken).

*Alternative:* Feedback-Frames für das `[led]`-Gerät über `LedOutput` und
dessen eigenen `O_WRONLY`-Port leiten. Verworfen: zwei Ausgabewege, keine
Stau-Erkennung auf dem zweiten Port, Eingabe und Ausgabe des Geräts liefen
weiter über getrennte Öffner.

### D4: Besitz einer LED-Note wird bei der Konfigurationsprüfung entschieden

Nach dem Parsen von Profilen, Mapping und `[led]` prüft die Konfiguration: Für
das `[led]`-Gerät (nur bei `led.enabled`) dürfen `note`, `fine_note` und
`nipple_note` nicht unter den LED-fähigen Feedback-Zielen dieses Geräts
liegen. Der Fehler nennt das `[led]`-Feld und das Playback-Ziel. So kann zur
Laufzeit kein Wettstreit um eine LED entstehen.

*Alternative:* Laufzeit-Vorrang (`[led]` gewinnt). Verworfen: Das Verhalten
wäre für Betreiber unsichtbar und die LED würde flackern.

### D5: Palette mit 15 Farben, CTO und CTB als Warm- und Kaltweiß

Die Palette wächst um `cto` und `ctb` (Index 13, 14). `nearest_color` sucht
unter allen 15 Farben; CTO hat den Bezugswert `#ffc882` (Warmweiß), CTB
`#c8e1ff` (Kaltweiß). Reines Weiß bleibt weiß, warme Weiß- und helle
Orangetöne werden CTO, kühle Weißtöne CTB.

*Geändert nach dem Live-Test (2026-11-26):* Der erste Entwurf ließ CTO und CTB
beim Farbabstand weg. Ein warmweißer Executor erschien dadurch als Weiß, und
das Weiß des ENC ist kaltweiß; der Betreiber meldete „Warmweiß ist ein
Kaltweiß“. Die Messung (Velocity 14/30) zeigt, dass das Gerät Warmweiß kann.

### D6: ASL-Farbtabelle mit geprüfter Voreinstellung

Die Voreinstellung enthält nur am Gerät geprüfte Indizes. Nach der Messung
(siehe „Messung ASL“) sind das alle 15 Palettenfarben; Betreiber können per
`colors` einzelne Einträge überschreiben. `bright_level` und `dark_level` (0–127, Default 127/25) gibt es
nur bei `asl-mk2`; 25 entspricht der Ruhehelligkeit der festen `[led]`-Tasten.

*Alternative:* Indizes aus einem angenommenen Farbkreis berechnen. Verworfen:
drei Messpunkte reichen dafür nicht, falsche Farben wären schlechter als weiß.

### D7: Polling weicht Live-Eingaben (verworfen)

Gemessen im Live-Test (2026-11-26): rund 6,2 Playbacks-Abfragen/s, in der Spitze
22 Fader-Frames/s, Budget 25 Nachrichten/s. Die Abfragen stehen in der
`SendQueue` ganz hinten, verbrauchen aber ihr Token, sobald sie unterwegs sind.

Geplant war, dass `Ma2Client` den Zeitpunkt der letzten Live-Aktion meldet und
`ExecutorFeedback` Abfragen bis 300 ms danach überspringt (`LIVE_QUIET_SECONDS`).
**Das wurde nie umgesetzt** und ist auf Entscheidung des Betreibers
(2026-11-27) gestrichen. Der Betreiber hat danach getestet: Das Ruckeln der
Fader vom 2026-11-26 tritt nicht mehr auf (Poller mit zwei Blöcken je 250 ms,
Priorität in der `SendQueue`: Steuerung vor Encodern vor Playback-Fadern vor
Abfragen, Abfragen je Block zusammengefasst). Tritt es wieder auf, ist ein
eigener Change mit Messung der richtige Weg.

*Alternativen:* festes Teilbudget fürs Polling, `rate_limit` anheben. Beide
waren verworfen worden und bleiben es.

### D8: LEDs ohne Ziel aus

Neben den Zielen bildet das Feedback eine Liste „dunkler“ LEDs: je Bank (bzw.
Kanal 1 ohne Banks) jede Note aus `led_notes`, die in der Bank vorkommt und kein
Playback-Button-Ziel auflöst. Ausgenommen sind die `[led]`-Noten am
`[led]`-Gerät (dieselbe Ermittlung wie in der Besitzprüfung, D4). Zu Beginn
jedes Zyklus reiht das Feedback für jede dunkle LED den Aus-Zustand ein, wenn
`_last` ihn noch nicht kennt; weil `_last` bei Start, Reconnect,
Gerätewechsel und Konfigurationsänderung geleert wird, gehen die Aus-Frames
genau dann hinaus. Ohne `led_notes` gibt es keine dunklen LEDs, weil dann
nur Noten mit Ziel als LED-fähig gelten.

### D9: Unbelegte Executoren an der Antwort erkennen

Die echten Antworten der onPC (`tests/fixtures/playbacks/*.json`) enthalten
nie `isEmpty`. Ein unbelegter Executor kommt als Item mit `isRun = 0`, leerem
`tt`, `bC = #404040`, `bdC = #3D3D3D` und ohne `bottomButtons`. Der bisherige
Code wertete ihn als gestoppten grauen Executor; die LED leuchtete dunkel,
und die Regel „leere Page schaltet LEDs aus“ griff nie. `parse_playbacks`
zählt ein Item deshalb als leer, wenn `isEmpty` gesetzt ist oder der Titel
leer ist und `bottomButtons` fehlen. Nur auf die Farbe zu prüfen wäre
zerbrechlich (Theme der onPC); nur auf `bottomButtons` zu prüfen schlägt bei
breiten Fader-Executoren fehl, die ebenfalls keine haben.

## Live-Test (Tasks 6.2 und 6.3, 2026-11-26)

- 6.2: Nach dem Deploy (22:56) startet der Dienst ohne „duplex“-/„busy“-
  Meldung für die ASL; Modus-, Fine- und Nipple-LED verhalten sich wie
  spezifiziert (Betreiber bestätigt).
- 6.3 mit `[feedback] enabled = true` auf dem Pi: Start/Stop von Exec 1–5 und
  101–105, Appearance-Farben und Page-Wechsel folgen; die 15 Startframes
  wurden vom ENC abgenommen, keine Stau-Warnung, Kernel-Log sauber.
  Befunde: Fader ruckeln, wenn viel los ist (→ D7, später nicht mehr aufgetreten); Tasten
  ohne Belegung behalten ihren alten LED-Zustand (→ D8).
- Wiederholung am 2026-11-27 nach dem Deploy mit LEDs für alle Bänke und
  Auffrischen (`refresh_interval_ms = 1500`): Die LEDs folgen dem Executor-
  Zustand in allen drei Bänken, auch nach dem Bankwechsel am Gerät, und
  Farbänderungen kommen ohne Aus- und Wiedereinschalten an (Betreiber bestätigt).
  Nach dem letzten ENC-Neustart (01:13:28) blieb das Kernel-Log 15 Minuten
  sauber; ein Dienstneustart dauert 0,36 s. Stau-Warnungen gab es nicht.

## Risks / Trade-offs

- [Risiko] Ein Midicraft-Gerät mit Handbuch-Layout existiert doch → falsche
  Farben dort. *Mitigation:* Messung am ENC belegt das Layout; tritt ein solches
  Gerät auf, wird ein eigener Protokollwert ergänzt.
- [Risiko] Duplex-Öffnen der ASL ändert ihr Verhalten (H4 aus
  `fix-midicraft-led-output` für den ENC). *Mitigation:* Vor dem Deploy mit dem
  Dienst prüfen, dass Eingabe, Modus-LED und Nipple-LED weiter funktionieren;
  vor `LedOutput` lief die ASL bereits duplex über `MidiManager`.
- [Risiko] Umbau von `LedOutput` bricht die festen Funktionen. *Mitigation:*
  bestehende Tests in `tests/test_led_output.py` bleiben grün; neue Tests für
  Öffnen/Schließen über `MidiManager`.

## Migration Plan

1. `add-midicraft-led-feedback` archivieren (oder dessen Spec vorher nach
   `openspec/specs/executor-feedback/` übernehmen), sonst lehnt das Archiv die
   MODIFIED-Teile dieses Changes ab.
2. Code umsetzen, Tests grün, Deploy der Python-Dateien wie bisher.
3. Pi-Konfiguration bleibt bei `midicraft-v2`; die Velocity-Werte ändern sich
   ohne Konfigurationsänderung. ASL-Feedback erst nach der Farbmessung und nur
   auf Noten ohne `[led]`-Funktion einschalten.
4. Rollback: vorherige Python-Dateien aus dem Backup unter `/opt/ma2pi`
   zurückkopieren; die Konfiguration ist abwärtskompatibel, solange kein
   `asl-mk2`-Profil eingetragen ist.

### D10: Bänke und Auffrischen (2026-11-27)

`led_notes` nennt die Noten der ersten Bank. Weil jede Bank ihre eigene
Notenbelegung hat (ENC: Bank 1 Noten 55–84, Bank 2/3 `0–29`), werden die
LED-fähigen *Controls* aus Bank 1 bestimmt (`led_notes_by_bank`) und je Bank auf
deren Noten abgebildet; Controls ohne Note in einer Bank entfallen dort.
`build_feedback_targets` und die Liste dunkler LEDs laufen darüber.

Das ENC nimmt LED-Noten nur für die angezeigte Bank (= Kanal) an und sendet
beim Bankwechsel nichts (Mitschnitt vom 2026-11-27: nur Note-On/Off, weder
Program Change noch Control Change). Weil `ma2pi` nur Änderungen sendet, blieben
die Farben der neuen Bank aus, bis sich ein Executor änderte. Ein Bankwechsel
lässt sich nicht erkennen; deshalb sendet `_queue_refresh` pro Gerät mit
`refresh_interval_ms` reihum einen Bank-Kanal komplett neu (Takt = Intervall /
Zahl der Kanäle, nur bei leerer Ausgabe, `setdefault`, damit geänderte Zustände
Vorrang behalten). Beim ersten Versuch löschte `_apply` unveränderte, noch nicht
gesendete Frames aus der Ausgabe und damit die Auffrischung; es verwirft jetzt
nur noch Frames mit einem anderen, veralteten Zustand.

*Alternativen:* Bank aus der Eingabe-Note ableiten (greift erst nach der ersten
Bedienung), Neusenden bei jedem Poll (belastet die Ausgabe). Verworfen.


## Messung ENC (Task 1.1, 2026-11-26)

Statisch gesetzt über `midiC4D0` bei gestopptem Dienst, Abstand 150 ms; alle
Frames sofort abgenommen (`pending = 0`), Kernel-Log sauber. Beobachtung des
Betreibers plus Foto:

| Velocity | Erwartet (Plugin-Layout) | Gesehen |
|---|---|---|
| 0 | aus | aus |
| 1 | dunkel weiß | gedimmt weiß, deutlich dunkler als 17 |
| 14 | dunkel CTO | warmweiß |
| 15 | dunkel CTB | kaltweiß (weiß-hellblau) |
| 16 | unbelegt | dunkel |
| 17 | hell weiß | hell weiß |
| 18–22 | hell rot, orange, gelb, gelbgrün, grün | rot, orange, blassgelb, grün, grün |
| 23 | hell seegrün | türkis |
| 30 | hell CTO | warmweiß, wärmer als 31 |
| 31 | hell CTB | kaltweiß |
| 32 | unbelegt | dunkel |

Alle 15 RGB-Noten (65–69, 75–79, 80–84) leuchten mit Velocity 17 hell weiß und
mit Velocity 1 gedimmt weiß; die `led_notes`-Liste in `config.toml` ist damit
bestätigt. Das Handbuch-Layout ist widerlegt (dort wäre 18 orange und 23 cyan).

## Messung ASL (Task 1.2, 2026-11-26)

Dienst gestoppt, je Runde `9F 7F 7F` und auf den Noten 9, 10, 11 Helligkeit
127 plus Index; alle Frames abgenommen. Ergebnis: Der Farbindex ist RGB mit
2 Bit je Kanal (`16·R + 4·G + B`), Bit 6 wird ignoriert.

| Index | Erwartet | Gesehen |
|---|---|---|
| 0 | aus | aus |
| 16, 32 | rot schwach, rot mittel | beide rot, kaum Unterschied |
| 3 / 12 / 63 | blau / grün / weiß | blau / grün / weiß |
| 52 / 60 / 44 | orange / gelb / gelbgrün | passt |
| 14 / 15 / 43 | seegrün / cyan / lavendel | passt |
| 35 / 51 / 59 | violett / magenta / pink | passt |
| 62 / 63 / 47 | CTO / weiß / CTB | warm / neutral / kalt |

Die bekannten Werte passen ins Schema: 8 = grün (G = 2), 48 = rot (R = 3),
127 = weiß, 121 und 116 aus `[led]` = orange-Töne. Die Voreinstellung deckt
damit alle 15 Palettenfarben ab; die Regel „Farben ohne Index weiß“ aus dem
ersten Entwurf von D6 entfällt, die Spec nennt die vollständige Tabelle.

## Open Questions
