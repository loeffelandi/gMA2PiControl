# Tasks

> Status: Umsetzung freigegeben. Software-Tasks sind abgehakt, sobald sie auf
> dem Entwicklungsrechner verifiziert wurden. Hardware-/Pi-abhängige Tasks
> bleiben offen; siehe `review.md` und README-Abschnitt „Open hardware
> acceptance“.

## 1. Projektgerüst und Konfiguration

- [x] 1.1 Paket `ma2pi/` mit `__main__.py`, `config.py`, `hid_input.py`, `ma2_client.py`, `mapping.py`, `wheel_protocol.py`, `hardkeys.py` sowie `pyproject.toml` (Python `>=3.13`, Laufzeit `evdev`/`websockets`, Dev `pytest`/`pytest-asyncio`) anlegen; verifizieren mit `python -m ma2pi --help`.
- [x] 1.2 Strukturiertes Logging mit Zeitstempel, Richtung, Frame-Typ und Session-ID sowie `--log-level` implementieren; Test prüft Format und dass Passwort/Hash nie im Log erscheinen.
- [x] 1.3 Strikte TOML-Validierung in `config.py` mit Dataclasses implementieren (Schema-Version, unbekannte Keys, Passwortquelle, Wheel-Bereich, Encoder-IDs, Referenzen); Tests für jeden Fehlerfall.
- [x] 1.4 `config.toml` als vollständiges Beispiel mit Cherry-/ASL-Profilen, Modifiern, wichtigsten Hardkeys, Number-Block und Encodern anlegen; `python -m ma2pi --check-config` endet mit 0, Test prüft die geforderten Key-Abdeckungen.
- [x] 1.5 Hardkey-Katalog in `hardkeys.py` aus den Chataigne-IDs ableiten (MA, Fix, Store, Clear, At, Thru, Please, Go +/-, Pause, 0–9, X1–X20); Test prüft Eindeutigkeit und Pflichtnamen.
- [ ] 1.6 `--list-devices` und `--dump-input` implementieren; auf dem Pi zeigen sie Name, Vendor-/Product-ID und normalisierte Events der angeschlossenen Geräte.

## 2. MA2-Client

- [x] 2.1 Frame-Builder für Login, `command`, natives/LUA-Hardkey, `encoder`, Keepalive und `closeConnection` zentral implementieren; Tests vergleichen die erzeugten JSON-Objekte exakt.
- [x] 2.2 Session-Handshake als Zustandsmaschine gegen `tests/mock_ma2.py` implementieren (server ready → session 0 → sessionInformation → Login → loginResponse); Test für Erfolg und `result: false`.
- [x] 2.3 Keepalive-Task mit konfigurierbarem Intervall < 10 s implementieren; Test mit 12 s Leerlauf prüft mindestens zwei Keepalive-Frames.
- [x] 2.4 Reconnect mit exponentiellem Backoff, Jitter, Obergrenze und Leeren des Tastenzustands implementieren; Test simuliert onPC-Neustart und prüft neuen Login ohne Replay.
- [x] 2.5 Send-Queue mit globalem Token-Bucket, Priorität für Steuer-Frames und „Releases nie verwerfen“ implementieren; Tests für 200 Frames in 100 ms, Queue-Überlauf und Prioritätsreihenfolge.
- [x] 2.6 Dry-Run-Transport implementieren, der Frames nur loggt und keine Verbindung öffnet; Test startet ohne Mock-Server und prüft null Socket-Verbindungen.
- [x] 2.7 Graceful Shutdown für SIGINT/SIGTERM implementieren (Releases, `closeConnection`, FD-Freigabe, Exit 0); Integrationstest mit gehaltener Taste und Timeout.
- [x] 2.8 Backpressure-Wache implementieren (Halbierung der Rate bei vollem Puffer/Queue); Test prüft Auslösen, Erholung und Logeintrag.

## 3. HID-Input

- [x] 3.1 Geräte-Enumeration, Vendor-/Product-/Namensfilter und Interface-Scoring implementieren; Unit-Tests mit Fake-Geräteinfo prüfen Auswahl und Ignorieren unbekannter Geräte.
- [x] 3.2 Geräteprofile aus `[profiles.*]` laden und validieren (Controls, Encoder-IDs, Richtung, Referenzen); Tests für gültige und ungültige Profile.
- [x] 3.3 evdev-Reader implementieren, der Key-Down/Key-Up normalisiert, Autorepeat unterdrückt und unbekannte Codes einmalig loggt; Tests mit synthetischen evdev-Events.
- [x] 3.4 Encoder-Decoding für absolute und relative Achsen inklusive Überlauf, Richtung und Rauschschwelle implementieren; Tests für +3, −2, Wrap-around und Sub-Threshold.
- [x] 3.5 Hotplug-Polling (1 s), Freigabe gehaltener Keys bei Geräteverlust und erneutes Öffnen implementieren; Tests mit entfernter und wieder auftauchender Fake-Quelle.
- [x] 3.6 Fehlende Geräteberechtigung als eindeutigen Fehler mit udev-Hinweis und Backoff behandeln; Test prüft Meldung und dass der Daemon weiterläuft.
- [x] 3.7a ASL als USB-MIDI-Gerät (`04d8:e817`, `/dev/snd/midiC3D0`) erkennen, MIDI-Backend mit inkrementellem Notenparser und Profilfeldern `notes`/`midi_encoders` implementieren; Tests decken Parser, Tasten, Encoder, Hotplug und Rechtefehler ab.
- [x] 3.7 Geführten ASL-Capture auf dem Pi durchführen: jede Taste und jede Encoder-Richtung genau einer Note zuordnen und das Profil damit bestätigen; verifizieren, dass alle vier Encoder saubere Detents liefern. Ergebnis: Noten 1–4 = Encoder 1–4 (Velocity `127` = rechts, `1` = links), Noten 5–8 = Encoder-Clicks, Noten 9–11 = Tasten; `--dump-input` liefert `encoder.1..4 ±1` und `key fine`/`asl_click_1` mit `1/0`.
- [ ] 3.8 Cherry G86-63400 auf dem Pi verifizieren: nur das Keyboard-Interface wird geöffnet, jede Taste erzeugt genau ein Paar, keine Doppel-Events aus weiteren Interfaces; Scancodes den gedruckten Tasten zuordnen.

## 4. Mapping-Engine

- [x] 4.1 Geordnetes Held-Key-Register mit Press/Release, Duplikat-Unterdrückung und Release-ohne-Press-Ignoranz implementieren; Unit-Tests für Tap, Hold, Doppel-Press und verwaistes Release.
- [x] 4.2 Modifier-Stack implementieren, der Modifier-Press hält und Chord-Reihenfolgen korrekt sendet; Test prüft MA-Press → Fix-Press → Fix-Release.
- [x] 4.3 CMD-Keys implementieren (genau ein `command`-Frame beim Press, keiner beim Release, String unverändert); Tests für Einzel- und Semikolon-Sequenz.
- [x] 4.4 Cleanup bei Shutdown, Verbindungsverlust und Geräteverlust in umgekehrter Press-Reihenfolge implementieren; Tests prüfen Reihenfolge und Zustandsleerung nach Reconnect.
- [x] 4.5 Auflösung logischer Controls auf Hardkey, CMD oder lokalen Modifier inklusive numerischem Hardkey-Override implementieren; Tests für gültige und unbekannte Referenzen.
- [x] 4.6 Unmappte Controls dürfen keinen Frame erzeugen und erscheinen nur im Debug-Log; Test prüft leere Send-Queue.
- [x] 4.7 Akzeptanztest auf Engine-Ebene: MA halten + Fix tippen erzeugt exakt die vier erwarteten Frames und die onPC-Semantik „Desk Lock“ ist im Test dokumentiert.

## 5. Encoder-Control

- [x] 5.1 Encoder-Zielmapping (Slot 1–8 oder festes Attribut) mit Eindeutigkeits- und Bereichsprüfung implementieren; Tests für Slot, Attribut, ungültigen Slot und doppelte ID.
- [x] 5.2 Delta-Akkumulation, 40-ms-Flush, Idle-Flush und Null-Delta-Unterdrückung implementieren; Tests für 10 Detents in 10 ms, langsame Drehung, Cancellation und letzten Detent.
- [x] 5.3 Beschleunigungskurven `none`/`linear`/`exponentiell` mit Fenster und Kappung implementieren; Tests prüfen 1:1 bei langsam, größeren Delta bei schnell, Vorzeichen und „nie 0“.
- [x] 5.4 Auflösung per Encoder-Klick zyklisch umschalten (Normal → Fine → Ultra → Normal) und als eigenen `encoder`-Frame mit `resolution` senden; Test prüft alle drei Stufen und dass der Pending-Delta verworfen wird.
- [x] 5.5 Nativen Attribut-Encoder-Frame (`requestType: "encoder"`, `name`, `value`) implementieren; Test prüft Name, Wert und Session. CMD-Wrapper für Encoder entfällt.
- [x] 5.6 Attribut-Fenster aus der onPC ableiten: `presetTypes` liefert das selektierte Attribut, der 4er-Block folgt ihm; Polling jede Sekunde (`page_refresh_interval`). Tests prüfen Fensterwechsel, kurze Features und Feature-Wechsel.
- [x] 5.7 Screen-Modus per Taste: `screen_mode` schaltet zwischen Attribut- und Screen-Encodern, `mapping.screen_encoders` liefert die Namen für Slots 1–4, der Modus steht als `screen_mode` im Status (grün/rot für die Oberfläche). Test prüft Umschalten, fehlende Konfiguration und Status.
- [ ] 5.8 Physische LED-Ansteuerung des ASL: MIDI-LED-Protokoll per Mitschnitt ermitteln (Note/CC je Taste), Ausgabe im Daemon implementieren und den Modus grün/rot anzeigen; Test mit aufgezeichnetem Fixture.
- [x] 5.9 Encoder-Stresstest gegen den Mock-Server: 100 Detents/s über 10 s bleiben unter dem Limit, die kumulierte Delta-Summe stimmt bis zur Obergrenze, der Puffer bleibt begrenzt.
- [x] 5.10 Nicht mehr benötigte Wheel-Ziele und CMD-Wrapper entfernen (`wheel_protocol.py` bleibt nur als dokumentierter, ungenutzter Baustein); ADR-0002 wird mit dem verifizierten Attribut-Format aktualisiert.

## 6. Deployment

- [ ] 6.1 `deploy/install.sh` implementieren: System-User `ma2pi`, Verzeichnisse, venv unter `/opt/ma2pi/.venv`, `pip install`, idempotent; zweimaliger Lauf auf Trixie endet fehlerfrei.
- [ ] 6.2 `deploy/ma2pi.service` mit `Restart=always`, `After=network-online.target`, `User=ma2pi`, `ProtectSystem=strict`, `PrivateTmp=true`, `PrivateDevices=false`, `DeviceAllow`, `NoNewPrivileges` anlegen; `systemd-analyze verify` ist grün, Start/Stop funktioniert.
- [ ] 6.3 udev-Regeln für Cherry (0x046a) und ASL (ermittelte ID) mit `GROUP="ma2pi"`, `MODE="0660"` anlegen; `udevadm test` und Lesetest als `ma2pi` bestätigen den Zugriff.
- [ ] 6.4 README für Installation, Update und Rollback schreiben; die dokumentierten Befehle werden auf dem Pi einmal vollständig ausgeführt.
- [ ] 6.5 Dienst nach Reboot, onPC-Neustart und Geräte-Replug prüfen; er startet automatisch, verbindet sich neu und nimmt beide Geräte wieder auf.

## 7. Integration und Hardware-Abnahme

- [x] 7.1 `tests/mock_ma2.py` um konfigurierbare Fehlerfälle (falsches Passwort, Trennung, Verzögerung) erweitern und einen End-to-End-Test von Fake-Input über Mapping bis zu aufgezeichneten Frames bauen.
- [x] 7.2 Dry-Run mit der Beispielkonfiguration end-to-end ausführen und die erwartete Frame-Folge für einen typischen Programmiervorgang dokumentieren.
- [ ] 7.3 Hardware-Smoke-Test durchführen: MA+Fix → Desk Lock, Store halten → Store Options, Clear halten → ClearAll, Go+/Go−, Number-Block; Ergebnis protokollieren.
- [ ] 7.4 Hardware-Stresstest durchführen: vier Encoder gleichzeitig schnell drehen plus Hardkey-Spam über zehn Minuten; onPC bleibt bedienbar, kein Release geht verloren.
- [ ] 7.5 Reconnect-Abnahme: onPC neu starten und Keyboard/ASL im Betrieb trennen und wieder anstecken; keine hängenden Modifier, kein Daemon-Neustart nötig.
- [ ] 7.6 ADR-Status anhand der Nachweise aktualisieren: 0001, 0003, 0004, 0005, 0007 auf Accepted bei bestandener Prüfung; 0002 auf Accepted oder dokumentierten CMD-Fallback; 0006 auf Accepted bei grüner Validierung.

## 8. Dokumentation und Abschluss

- [x] 8.1 README-Abschnitt „Wheel-Protokoll-Capture“ mit exakten Chrome-DevTools-Schritten, Filter, Wheel-View und Copy-Anleitung schreiben; eine zweite Person kann den Ablauf ohne Rückfragen durchführen.
- [x] 8.2 Konfigurationsreferenz mit allen Schlüsseln, Wertebereichen und Beispielen schreiben; Abgleich mit `config.py` ist vollständig.
- [x] 8.3 `openspec validate --strict` für `add-ma2pi-core` ausführen; keine Fehler oder Warnungen.
- [x] 8.4 Vollständige Testsuite `pytest` auf dem Pi und auf dem Entwicklungsrechner ausführen; alle Tests grün.
- [x] 8.5 Abschlussreview gegen alle vier Specs durchführen und offene Abweichungen dokumentieren; jede Anforderung hat einen Nachweis oder eine begründete Ausnahme.

## Workflow follow-up

- Proposal, Specs, Design und ADRs wurden für die Umsetzung freigegeben.
- Software-Tasks sind umgesetzt und auf dem Entwicklungsrechner verifiziert.
- Offen bleiben ausschließlich Hardware-/Pi-Nachweise; der Change wird erst nach
  deren Abschluss archiviert und die Haupt-Specs synchronisiert.
