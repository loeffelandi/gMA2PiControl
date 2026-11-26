# Tasks

## 1. Messung am Gerät

Dienst läuft normal; Frames gehen über ein kurzes Skript bei gestopptem Dienst
oder über die MA-Kommandozeile (`MidiNote`). Jeder Schritt notiert die
sichtbare Farbe und Helligkeit.

- [x] 1.1 ENC, Note 65: Velocity 1, 14, 15, 16, 17, 23, 30, 31, 32 je 3 s
  zeigen; danach alle 15 RGB-Noten (65–69, 75–79, 80–84) einzeln mit
  Velocity 1 und 17 bespielen. Encoder-Klick-Noten 55–59 bleiben außen vor
  (keine LED). Übernommen aus `add-midicraft-led-feedback` Task 1.2.
  Verifikation: Tabelle Velocity → Farbe im Design; erwartet 17 = hell weiß,
  15 = dunkel CTB, 23 = hell seegrün; `led_notes`-Liste in `config.toml`
  bestätigt oder korrigiert.
- [x] 1.2 ASL, eine Taste ohne `[led]`-Funktion oder kurzzeitig `[led]` aus:
  Farbindizes so wählen, dass jede Palettenfarbe (weiß bis pink, CTO, CTB)
  einen Kandidaten bekommt; Helligkeit 127 und 25 je Index. Verifikation:
  Tabelle Palettenname → Index im Design, mit Datum.

## 2. Palette und Midicraft-Kodierung

- [x] 2.1 Palette auf 15 Farben (`cto`, `ctb`) erweitern; `nearest_color`
  sucht nur unter den 13 Grundfarben; `fallback_color` akzeptiert alle 15.
  Verifikation: `tests/test_feedback.py` — `#ffb070` wird nicht CTO,
  `fallback_color = "ctb"` liefert Index 14; `tests/test_config.py` —
  `fallback_color = "ctb"` gültig.
- [x] 2.2 `midicraft-v2` auf `1 + Index` / `17 + Index` umstellen.
  Verifikation: `tests/test_feedback.py` — Szenarien helles Seegrün (23),
  dunkles Weiß (1), helles Weiß (17), dunkles CTB (15); bestehende Tests mit
  alten Werten angepasst.
- [x] 2.3 README-Abschnitt `[profiles.<name>.led_feedback]`: Tabelle der
  Velocity-Werte und Palette aktualisieren. Verifikation: README nennt 1–15 und
  17–31 und die 15 Farben.

## 3. Kodierer je Protokoll

- [x] 3.1 Kodierer mit `state`, `frame`, `preamble` einführen; Queue und
  `_last` speichern `LedState`; Midicraft-Kodierer liefert dieselben Bytes wie
  2.2. Verifikation: alle Tests aus `tests/test_feedback.py` grün, Test „zwei
  Geräte, zwei Protokolle“ mit Fake-MIDI.
- [x] 3.2 Präambel nach jedem (Wieder-)Öffnen genau einmal vor dem ersten
  Frame senden. Verifikation: Test — erster Frame an ein ASL-Fake beginnt mit
  `9F 7F 7F`, zweiter nicht; nach Gerätewechsel erneut.

## 4. ASL-Protokoll und Konfiguration

- [x] 4.1 `protocol = "asl-mk2"` mit `bright_level`, `dark_level` (0–127,
  Default 127/25) und `colors` (Palettenname → 0–127) parsen; Schlüssel nur
  bei `asl-mk2` erlaubt. Verifikation: `tests/test_config.py` — gültige Werte,
  `dark_level = 200`, unbekannter Farbname, `colors` an `midicraft-v2`.
- [x] 4.2 ASL-Kodierer: Frame `90 <Note> <Helligkeit>` + `91 <Note> <Index>`,
  Voreinstellung nach Messung 1.2 (alle 15 Palettenfarben).
  Verifikation: `tests/test_feedback.py` — Szenarien laufend rot, gestoppt
  dunkel, aus, Voreinstellung für Magenta (51), eigener Index für Blau, ein
  ASL-Frame je Takt.
- [x] 4.3 Besitzprüfung: `[led]`-Noten (`note`, `fine_note`, `nipple_note`) des
  `[led]`-Geräts dürfen keine LED-fähigen Feedback-Ziele sein, nur bei
  `led.enabled`. Verifikation: `tests/test_config.py` — Nipple-Taste als
  Playback-Ziel abgelehnt mit beiden Feldnamen, getrennte Noten gültig,
  `[led] enabled = false` erlaubt die Note.
- [x] 4.4 `config.toml` und README: `asl-mk2`-Beispiel (auskommentiert, ohne
  `[led]`-Noten), Farbtabelle, Besitzregel. Verifikation: `--check-config`
  grün mit `config.toml`; das auskommentierte Beispiel aktiviert ist ebenfalls
  gültig (Test lädt es).

## 5. Ein Port je Gerät

- [x] 5.1 Ein Port je Gerät: Beim Apply (2026-11-26) bereits vorhanden —
  `LedOutput` schreibt über `MidiManager.send` (`sender`), `_led_step` erkennt
  Replugs über `open_generations` und stellt Modus/Fine/Nipple wieder her; der
  Shutdown sendet `9F 7F 7E` vor dem Schließen. Eigene Rückrufe in
  `MidiManager` sind daher nicht nötig (Design D3 angepasst). Verifikation:
  bestehender Test `test_led_step_routes_through_midi_manager_and_hot_reloads`.
- [x] 5.2 Freigabe durch `[led]` meldet das Gerät an das Feedback
  (`on_release` → `ExecutorFeedback.resend_device`), damit Feedback-LEDs nach
  `9F 7F 7E` neu gesendet werden. Verifikation:
  `test_led_step_reports_every_release_of_the_buttons`,
  `test_resend_device_sends_the_full_state_again`.
- [x] 5.3 `[led]` und Feedback am selben ASL-Gerät. Verifikation:
  `test_fixed_leds_and_feedback_share_one_asl_device` — Moduswechsel ändert
  die Feedback-LED nicht, Feedback aus schreibt nichts.

## 6. Abschluss

- [x] 6.1 `pytest` komplett grün und `openspec validate
  add-per-device-led-protocols --strict` grün. Verifikation: Ausgaben.
- [x] 6.2 Auf dem Pi nach Deploy: Dienst startet ohne „duplex“-Meldung für die
  ASL, Modus-, Fine- und Nipple-LED funktionieren, ENC zeigt bei laufendem
  Executor die Appearance-Farbe hell. Verifikation: Journal-Auszug und
  Beobachtung im Design.
- [ ] 6.3 Live-Test mit onPC und ENC (übernommen aus
  `add-midicraft-led-feedback` Task 6.2): Exec 1–5 und Floating-Exec 101–105
  starten/stoppen, Buttons 2/3 der Exec 1–5 auslösen und Appearance-Farben
  ändern; LEDs folgen innerhalb von zwei Intervallen, auch nach einem
  Seitenwechsel. Verifikation: beobachtetes Verhalten im Design protokolliert.

## 7. Befunde aus dem Live-Test

- [ ] 7.1 `Ma2Client` meldet Zeitpunkt der letzten Live-Aktion und ob eine
  Live-Aktion wartet; `ExecutorFeedback` überspringt Abfragen, solange eine
  wartet oder die letzte < 300 ms her ist. Verifikation:
  `tests/test_feedback.py` (Fake-Client: keine Abfrage während Bewegung,
  Abfrage nach 300 ms Ruhe) und `tests/test_ma2_client.py` (Zeitstempel und
  Warteschlange).
- [x] 7.2 Dunkle LEDs: LED-fähige Noten ohne Playback-Ziel je Bank bekommen den
  Aus-Zustand bei Start, Reconnect, Gerätewechsel und Config-Wechsel;
  `[led]`-Noten ausgenommen. Verifikation: `tests/test_feedback.py` —
  unbelegte ENC-Taste erhält Velocity 0, entferntes Ziel geht aus, ASL-Note 9
  mit `[led]` bleibt unberührt.
- [ ] 7.3 README-Abschnitt `[feedback]` um beide Verhaltensweisen ergänzen.
  Verifikation: README nennt die 300 ms und das Ausschalten unbelegter Tasten.
- [x] 7.5 CTO/CTB nehmen am Farbabstand teil (Bezugswerte `#ffc882`,
  `#c8e1ff`); `#ffffff` bleibt weiß. Verifikation: `tests/test_feedback.py` —
  `#ffe0b0` → CTO, `#c0e0ff` → CTB, `#ffffff` → weiß, Grundfarben unverändert;
  README angepasst.
- [x] 7.6 Unbelegte Executoren erkennen (`isEmpty` oder leerer Titel ohne
  `bottomButtons`) und deren LEDs ausschalten. Verifikation:
  `tests/test_feedback.py` mit den echten Fixtures — `page1_button.json`:
  Exec 103–115 leer, 101/102 belegt; breiter Executor in
  `page3_fader_wide_exec6.json` bleibt belegt; Ziel auf leerem Executor
  erhält Velocity 0.
- [ ] 7.4 Deploy auf den Pi und 6.3 wiederholen: Fader laufen bei aktivem
  Feedback flüssig, unbelegte Tasten sind dunkel. Verifikation: Betreiber
  bestätigt, Journal ohne Stau-Warnung.

## Workflow follow-up

- `add-midicraft-led-feedback` vor diesem Change archivieren; sonst lehnt das
  Archiv die MODIFIED-Anforderungen ab (Ziel-Spec fehlt).
- Messwerte aus Gruppe 1 in die Voreinstellung der ASL-Farbtabelle übernehmen.
