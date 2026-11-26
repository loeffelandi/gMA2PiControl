# Tasks

## 1. Messung am ENC (vor jeder Umsetzung)

Voraussetzung: Dienst gestoppt, kein anderer Prozess hält `/dev/snd/midiC4D0`
(`/proc/asound/card4/midi0` zeigt keinen Owner). `journalctl -k -f` läuft
parallel. Jeder Schritt notiert: LED sichtbar (ja/nein/welche), Eingabe danach
weiter (ja/nein), Kernel-Log (`urb status -32`, `drain error`, Disconnect).

- [ ] 1.0 Firmware-Version des ENC feststellen (Geräte-Menü oder Hersteller-
  Tool) und festhalten, ob das Layout aus dem Handbuch (Abstand 14) oder aus
  dem Plugin (Abstand 16: 1, 17, 33, 49, 65) gilt. Verifikation: Version und
  gemessene Velocity-Werte 15, 16, 17 mit sichtbarer Farbe im Design.
- [ ] 1.1 Referenzverkehr auf dem Draht aufzeichnen: das Plugin
  (`test.lua`, `Plugin 18`) läuft in der MA2, ein MIDI-Monitor zeichnet auf
  dem Ausgangsport Kanal, Note, Velocity und Abstände auf. Das Plugin selbst
  ist als Quelle bereits bekannt (siehe Design, „Referenz“); die Aufzeichnung
  bestätigt, was die MA wirklich sendet (Kanal der MidiRemote-Zeile,
  Note-On gegen Note-Off, Bündelung). Verifikation: mindestens eine
  Aufzeichnung mit Startzustand und einer Änderung je LED-Gruppe.
- [ ] 1.2 Vergleich: Aufzeichnung gegen `90 <Note> <Vel>` auf Kanal 1
  (`midicraft-v2`) stellen. Abweichungen in Kanal, Note, Velocity-Tabelle
  oder Note-Off im Design festhalten und als Folge-Change an
  `add-midicraft-led-feedback` markieren (H1). Verifikation: Vergleichstabelle
  mit Plugin und Aufzeichnung.
- [ ] 1.3 Einzelframe-Test: je ein Frame (Note 65, Velocity 15), 2 s warten,
  Encoder drehen, Eingabe prüfen. Danach Velocity 0, 1, 21. Verifikation:
  LED-Verhalten und Eingabe je Schritt notiert.
- [ ] 1.4 Alle 15 Noten (65–69, 75–79, 80–84) einzeln mit Pause von 100 ms.
  Ergebnis als `led_notes`-Liste festhalten und Task 1.2 von
  `add-midicraft-led-feedback` abhaken. Encoder-Klick-Noten 55–59 bleiben
  außen vor. Verifikation: Liste im Design.
- [ ] 1.5 Burst-Test: dieselben 15 Frames ohne Pause (ein `write` je Frame in
  einer Schleife). Danach mit Abstand 5, 10 (wie das Plugin), 20 und 50 ms.
  Kleinsten stabilen Abstand festhalten (H2). Verifikation: Tabelle Abstand →
  Eingabe weiter, Kernel-Log sauber.
- [ ] 1.6 Dauertest mit dem gemessenen Abstand: 10 Minuten wechselnde Frames
  bei gleichzeitigem Drehen am Encoder. Verifikation: keine Stall-Welle, kein
  Disconnect, Eingabe durchgehend.
- [ ] 1.7 Bei Instabilität trotz Einzelframes: Gegenprobe H3 (anderer
  USB-Port) und H4 (nur lesend, nur schreibend öffnen). Verifikation:
  Tabelle mit Ergebnis je Variante.

## 2. Konfiguration

- [x] 2.1 `led_feedback.enabled` (Default `true`) und `frame_interval_ms`
  (1–500, Default 20) in `ma2pi/config.py` parsen und validieren; Fehler
  nennen das Feld. Verifikation: `tests/test_config.py` — gültige Werte,
  Grenzwerte 0, 1, 500, 501, falscher Typ.
- [x] 2.2 `build_feedback_targets` überspringt Profile mit `enabled = false`.
  Verifikation: `tests/test_feedback.py` — ENC aus ergibt weder Ziele noch
  Blöcke, kein Polling ohne Ziele. (Die ASL hat in `config.toml` kein
  `led_feedback`; das Szenario „ENC aus, ASL an“ ist daher nur über die
  gerätegetrennte Ausgabe in 3.1 belegt.)
- [x] 2.3 `config.toml` und `README.md`: neue Schlüssel dokumentieren,
  `midicraft-enc` mit `enabled = false` und Kommentar zur offenen Messung;
  Verifikation: `--check-config` läuft grün mit der Datei.
- [x] 2.4 Neue Felder über den Config-Store lesen und schreiben, ohne
  andere Schlüssel zu verlieren. Die Web-UI hat keinen Editor für
  `led_feedback` (kein Bezug in `web/`), der Weg läuft über den Store.
  Verifikation: `tests/test_config_api.py` — Roundtrip beider Felder.

## 3. Getaktete Ausgabe und Stau

- [x] 3.1 Ausgabe-Queue je Gerät in `ma2pi/feedback.py`: `_apply` reiht ein,
  ein Zeitgeber je Gerät sendet höchstens einen Frame pro `frame_interval_ms`,
  neuer Zustand ersetzt offenen für dieselbe LED. `_last` wird nur nach
  erfolgreichem Senden gesetzt. Verifikation: `tests/test_feedback.py` mit
  Fake-Clock — Abstand, Ersetzen, zwei Geräte unabhängig.
- [x] 3.2 Statusabfrage der Ausgabe in `RealMidiHandle` kapseln
  (`SNDRV_RAWMIDI_IOCTL_STATUS`, Rückgabe `pending: int | None`, `None` bei
  Fehler). Verifikation: `tests/test_midi_input.py` mit Fake-ioctl.
- [x] 3.3 Stau-Erkennung (2 s ausstehend → Pause je Gerät, eine Warnung,
  Eingabe läuft weiter, Wiederaufnahme nach Neuöffnen mit Vollzustand).
  Verifikation: Tests mit Fake-Handle, der nichts abnimmt — Warnung genau
  einmal, Eingaben weiter zugestellt, nach Neuöffnen alle LEDs neu gesendet.
- [x] 3.4 Dry-Run unverändert: Frames nur im Log, Takt wirkt nicht auf die
  Log-Ausgabe. Verifikation: bestehende Dry-Run-Tests bleiben grün.

## 4. Schließen

- [x] 4.1 `RealMidiHandle.close` ruft vor `os.close` `SNDRV_RAWMIDI_IOCTL_DROP`
  auf (nur schreibbar geöffnet), Fehler nur auf DEBUG. Verifikation:
  `tests/test_midi_input.py` — Drop vor close, Fehlerfall schließt trotzdem,
  read-only Handle ruft kein Drop auf.
- [x] 4.2 Dienststopp mit gestautem Gerät: Test mit Fake-Handle, dessen
  Drain blockiert, prüft, dass `stop()` ohne Wartezeit zurückkehrt.
  Verifikation: Test im selben File.

## 5. Abschluss

- [x] 5.1 Alle Tests grün: `pytest` komplett. Verifikation: Testlauf.
- [ ] 5.2 Auf dem Pi nach dem Deploy: ENC mit gemessenem Intervall aktivieren,
  Kernel-Log 10 Minuten beobachten, Dienststopp dauert unter 5 s.
  Verifikation: Journal- und Kernel-Auszug im Design.
- [x] 5.3 `openspec validate fix-midicraft-led-output --strict` bleibt grün;
  Abhängigkeit zu `add-midicraft-led-feedback` im Proposal geprüft.
  Verifikation: CLI-Ausgabe.
