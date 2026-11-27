# Tasks

## 1. Messung

- [x] 1.1 M1: RTP-MIDI vom Pi zum rtpMIDI-Treiber auf dem onPC-Rechner mit
  einem Wegwerf-Skript (AppleMIDI-Einladung, Clock-Sync, ein Note-On/Off ohne
  Journal) prüfen; MA-MIDI-Eingang auf den rtpMIDI-Port stellen und klären, ob
  das direkte MIDI-Gerät parallel weiter geht. Verifizieren: Protokoll in
  `verification.md` (Sitzung angenommen ja/nein, Latenz, MA zeigt die Note im
  MIDI-Monitor).
- [x] 1.2 M2: Telnet der onPC (`192.168.178.72`) aktivieren und die Syntax zum
  Lesen, Anlegen, Ändern und Löschen von MIDI-Remotes messen (Port, Anmeldung
  als `svt`, Ausgabeformat von List). Verifizieren: Befehle und Beispiel-
  Ausgaben in `verification.md`, als Fixtures unter `tests/fixtures/telnet/`.
- [x] 1.3 M3: Mit einer per Telnet angelegten Remote auf Kanal 16 messen:
  Note-Off als Release (Flash, Swop, Temp), Remote auf Executor ohne feste Page
  (`page = "current"`), verdeckter Slot eines breiten Executors (Page 2,
  Exec 115), Store/Assign/Edit mit LUA-Kommandozeile der Cherry. Ergebnis in
  `design.md` D5/D7 nachziehen; falls `page = "current"` nicht abbildbar ist,
  Spec-Nachtrag in `executor-playback` schreiben. Verifizieren: Protokoll in
  `verification.md`, Testeinträge danach aus der Show entfernt.
- [x] 1.4 M4: Fader über MIDI-Remote (Velocity oder CC) kurz anmessen, nur zur
  Bewertung von D1. Verifizieren: Ergebnis als Absatz in `design.md` D1.
- [x] 1.5 Portkonflikt aus M1 beheben: Screen-Helper von UDP 5005 (RTP-MIDI-
  Datenport) auf 5010 verlegen (Default, `config.toml`, Live-Config, Skript) und
  `docs/screen-helper.ahk` gegen Binärpakete absichern. Verifizieren: Tests in
  `tests/test_config.py` und `tests/test_screen_helper.py` grün, RTP-MIDI-Session
  vom Pi angenommen.

## 2. Konfiguration

- [x] 2.1 `[midi_remote]` mit `enabled`, `host`, `port`, `channels`, `sync`,
  `telnet_port` in `ma2pi/config.py` samt Defaults und Validierung ergänzen.
  Verifizieren: Tests für Defaults, ungültige Kanäle, ungültigen `sync` und
  `--check-config` mit Feldnennung.
- [x] 2.2 `transport` an Playback-Zielen ergänzen (Default nach Spec, Ablehnung
  bei `enabled = false` und bei Fadern) und in `ma2pi/web/serialize.py` und der
  Config-UI anzeigen/bearbeiten. Verifizieren: Tests in `tests/test_config.py`
  und Serialisierungs-Roundtrip.
- [x] 2.3 Adressvergabe (D3) als reine Funktion: Ziele → (Kanal, Note), stabil
  für gleiche Ziele, Ablehnung bei erschöpftem Bereich. Verifizieren: Tests für
  doppelte Ziele über Bänke, Sortierung mit `"current"`, 129 Ziele auf einem
  Kanal.

## 3. RTP-MIDI-Ausgang

- [x] 3.1 AppleMIDI-Initiator (D2) in asyncio: Einladung auf Control- und
  Datenport, Clock-Sync, Abmelden, RTP-MIDI-Pakete ohne Journal, Reconnect mit
  Backoff bis 10 s. Verifizieren: Tests mit Fake-UDP-Gegenstelle (angenommen,
  abgelehnt, stumm, Abbruch mitten in der Sitzung), Paket-Bytes gegen Referenz.
- [x] 3.2 Note-On/Off für Press/Release inkl. einmaliger Note-Off-Wiederholung
  nach 20 ms; Reihenfolge je Ziel erhalten. Verifizieren: Tests prüfen `9F 05
  7F`/`8F 05 00` und die Reihenfolge bei schnellem Tippen.
- [x] 3.3 Sitzungszustand in Status-API und Web-UI anzeigen. Verifizieren:
  Test der Status-Serialisierung; manuell in der UI.

## 4. Abgleich per Telnet

- [x] 4.1 Telnet-Client für die MA (Anmeldung, Befehl senden, Ausgabe bis zum
  Prompt lesen, Timeout) mit der in 1.2 gemessenen Syntax in einem eigenen
  Modul. Verifizieren: Tests gegen die Telnet-Fixtures.
- [x] 4.2 Abgleich (D4): Tabelle lesen, nur reservierte Kanäle auswerten,
  Differenz anlegen/ändern/entfernen; Modi `auto`, `check`, `off`; Ergebnis
  (angelegt, geändert, entfernt, fehlerhaft, Zeitpunkt) im Status. Verifizieren:
  Tests mit Fake-Telnet für neues Ziel, entferntes Ziel, fremden Eintrag auf
  Kanal 1, Teilfehler, `check` ohne Schreiben.
- [x] 4.3 Abgleich nach Konfigurationsaktivierung und nach Telnet-Neuaufbau
  auslösen; während des Abgleichs gelten geänderte Ziele als nicht abgeglichen.
  Verifizieren: Runtime-Test mit Config-Tausch.

## 5. Router-Weiche

- [x] 5.1 `PlaybackRouter` (D5) leitet Ziele mit `transport = "midi"` an den
  MIDI-Ausgang, `web` unverändert an `Ma2Client`; Topologie-Auflösung gemäß
  Ergebnis von 1.3. Verifizieren: Tests für beide Transporte, Bankwechsel und
  `page = "current"`; bestehende Playback-Tests bleiben grün.
- [x] 5.2 Kein stilles Ausweichen (D6): Verwerfen bei getrennter Sitzung oder
  nicht abgeglichenem Ziel, eine Warnung je Ausfall und Ziel. Verifizieren:
  Tests prüfen, dass weder MIDI noch `playbacks_userInput` gesendet wird und die
  Warnung nur einmal kommt.

## 6. Doku und Abnahme

- [x] 6.1 Neue ADR (D7) unter `docs/adr/` und README-Abschnitt zur Einrichtung
  (rtpMIDI auf dem onPC-Rechner, MA-MIDI-Eingang, Telnet, `[midi_remote]`).
  Verifizieren: Dateien vorhanden, ADR 0019 verweist auf die neue ADR.
- [x] 6.2 Deploy auf den Pi, `enabled = true`, `sync = "auto"`; Abnahme an der
  Hardware: Store, Assign und Edit von der Cherry plus ENC-Taste, normales
  Auslösen, Flash mit Release, LED-Feedback weiter aktiv, Fader weiter über den
  Web Remote. Verifizieren: Protokoll in `verification.md`, Bestätigung des
  Nutzers.

## Workflow follow-up

- Nach Abnahme: Change archivieren (`openspec archive add-midi-remote-executors`).
