# Proposal

## Why

Das Executor-Feedback kennt nur ein LED-Protokoll, und das stimmt am MIDICRAFT
ENC nicht: Velocity 15 soll „hell weiß“ sein, der ENC zeigt am 2026-11-26 auf
Note 65 aber ein weiß-hellblaues Licht. Das passt genau zum Layout des
offiziellen Midicraft-Plugins (`dunkel = 1 + Farbe`, `hell = 17 + Farbe`,
15 Farben inklusive CTO und CTB): 15 ist dort „dunkel CTB“. Die Tabelle in
`midicraft-v2` stammt aus dem Handbuch (`hell = 15 + Farbe`, 13 Farben) und
war nie am Gerät gemessen. Laufende Executoren erscheinen deshalb in falscher
Farbe oder dunkel.

Die ASL MK2-E4B3 steuert ihre LEDs völlig anders (Freigabe-Sequenz, zwei
Note-On je LED: Kanal 1 Helligkeit, Kanal 2 Farbindex). Sie bekommt heute nur
die festen Funktionen aus `[led]`, kein Executor-Feedback. Die Kodierung muss
deshalb je Gerät wählbar sein und darf zwischen Herstellern nichts teilen außer
dem Executor-Zustand und der Palettenfarbe.

## What Changes

- **BREAKING** `protocol = "midicraft-v2"` sendet künftig das gemessene Layout:
  `0` aus, `1 + Farbe` dunkel, `17 + Farbe` hell, 15 Farben (die bisherigen 13
  plus CTO und CTB). Geräte mit dem Handbuch-Layout sind nicht bekannt; das
  alte Layout entfällt.
- Neues Feedback-Protokoll `asl-mk2` für `[profiles.<id>.led_feedback]`:
  laufend = Farbindex mit heller Helligkeit, gestoppt = derselbe Index mit
  dunkler Helligkeit oder aus. Freigabe-Sequenz und Frame-Form wie in
  `led_output.py`, über denselben geöffneten Port wie `[led]`.
- Farbtabelle je Profil: `asl-mk2` bildet Palettenfarben über eine
  konfigurierbare Tabelle (`colors`, Name → Index 0–127) auf ASL-Indizes ab;
  Voreinstellung sind nur am Gerät geprüfte Werte.
- Eine LED-Note gehört genau einer Funktion: Noten, die `[led]` belegt
  (Modus-, Fine-, Nipple-Taste), MUST kein Executor-Feedback bekommen; eine
  Überschneidung lehnt `--check-config` ab.
- Die getaktete Ausgabe und der Stau-Schutz aus `fix-midicraft-led-output`
  gelten für jedes Protokoll; ein ASL-Frame (Freigabe plus zwei Note-On) zählt
  als ein Frame.
- Ergänzt nach dem Live-Test (2026-11-26): Das Playbacks-Polling weicht
  Live-Eingaben (keine Abfrage, solange eine Live-Aktion wartet oder bis 300 ms
  nach der letzten), weil es sonst mit rund 6 Abfragen/s das Sendebudget von
  25 Nachrichten/s mit den Fadern teilt und diese ruckeln. LED-fähige Tasten
  ohne Playback-Ziel werden ausgeschaltet, statt ihren alten Zustand zu
  behalten.

Nicht Teil dieses Changes: blinkende oder komplementäre Midicraft-Modi,
Kanal- bzw. Bank-Logik der LED-Frames, LED-Feedback für weitere Hersteller,
Änderungen am Verhalten der festen `[led]`-Funktionen.

## Capabilities

### New Capabilities

Keine. `executor-feedback` entsteht mit `add-midicraft-led-feedback`; dieser
Change ergänzt sie als Delta.

### Modified Capabilities

- `executor-feedback`: Protokollwahl je Profil, korrigierte
  Midicraft-Kodierung mit 15 Farben, neues Protokoll `asl-mk2` mit
  Farbtabelle, Besitzregel für LED-Noten gegenüber `[led]`.

## Impact

- Code: `ma2pi/feedback.py` (Kodierung je Protokoll, Palette mit CTO/CTB),
  `ma2pi/config.py` (Protokollwerte, `colors`, Prüfung der Überschneidung mit
  `[led]`), `ma2pi/led_output.py` und `ma2pi/__main__.py` (ein Port je
  ASL-Gerät für `[led]` und Feedback).
- Konfiguration: `config.toml` und `README.md` (Protokolle, Farbtabelle,
  Besitzregel); bestehende Konfigurationen mit `midicraft-v2` bleiben gültig,
  senden aber andere Velocity-Werte.
- Tests: `tests/test_feedback.py`, `tests/test_config.py`,
  `tests/test_led_output.py`.
- Abhängigkeiten: setzt `add-midicraft-led-feedback` (Capability
  `executor-feedback`) und `fix-midicraft-led-output` (Takt je Gerät) voraus.
- Hardware: Messung am ENC (Velocity 16, 17, 31, 32) und an der ASL
  (Farbindizes der Palette) vor der Aktivierung.
