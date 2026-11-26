# Tasks

## 1. Shutdown und Event-Stream

- [ ] 1.1 Geräte-Learn-Task im `finally` von `run_daemon()` abbrechen und
  erwarten. Verifikation: Test startet den Daemon im Dry-Run, löst das
  Stop-Signal aus und prüft, dass kein Task mit Namen `ma2pi-*` mehr läuft.
- [ ] 1.2 `EventBus` um ein „dropped“-Signal je Subscriber erweitern;
  `events_handler` schließt den WebSocket, sobald es gesetzt ist.
  Verifikation: `tests/test_web.py` — langsamer Client mit `queue_size=1`
  wird getrennt, ein zweiter Client erhält weiter Events, ein Reconnect
  bekommt den Anfangsstand.
- [ ] 1.3 Bestehender Test `test_events_slow_client_is_dropped` bleibt grün
  (`subscriber_count` sinkt, eingereihtes Event bleibt lesbar).
  Verifikation: Testlauf.

## 2. Hot-Reload der Hilfsdienste

- [ ] 2.1 `LearnManager.set_config` und `DeviceLearnManager.set_config` als
  Activate-Hooks einhängen; Poll-Zeile in `_device_learn_loop` entfernen.
  Verifikation: Test wendet über den `ConfigStore` eine Änderung an und prüft,
  dass beide Manager die neue Konfiguration halten.
- [ ] 2.2 `_led_loop` in `_led_step(config, client, holder)` und Schleife
  trennen, Schleife liest `engine.config` und startet immer.
  Verifikation: Unit-Tests mit Fake-`LedOutput`/Pfadauflösung für
  Deaktivieren, Aktivieren, geänderte Einstellungen, totes Handle und
  Leerlauf bei deaktivierter LED.
- [ ] 2.3 README-Abschnitt zur LED/Feedback um „wirkt ohne Neustart“ ergänzen.
  Verifikation: Text stimmt mit `runtime-config`-Spec überein.

## 3. Eingabe

- [ ] 3.1 `_held`, `_press_targets` und `_pending_hold` in `MappingEngine` nach
  `(device, control)` schlüsseln; Doppel-Press desselben Geräts bleibt
  ignoriert. Verifikation: `tests/test_mapping.py` — Gerät A hält, Gerät B
  sendet Release für denselben Control → Press von A bleibt bestehen;
  Einzelgerät-Tests laufen unverändert.
- [ ] 3.2 Halter-Zähler je Hardkey-Name und je Encoder-Slot (Klick):
  Press-Frame nur bei 0 → 1, Release-Frame nur bei 1 → 0, Hold-Upgrade
  höchstens einmal je Taste. Verifikation: Tests „zwei Geräte, gleiche
  Konsolen-Taste“ (ein Press, kein Release beim ersten Loslassen, ein Release
  beim letzten) für Hardkey und Encoder-Klick.
- [ ] 3.3 Modifier-Abfragen (`ultra`, `fine`, Auflösungs-Zyklus, MA für
  Screen-Encoder) und `modifier_hook` gerätübergreifend umstellen: gehalten,
  solange irgendein Gerät hält; Hook meldet beim ersten Halter „gedrückt“,
  beim letzten „losgelassen“. Verifikation: Test mit Fine auf Gerät A und
  Encoder auf Gerät B; Hook-Test mit zwei Haltern.
- [ ] 3.4 Aufräumpfade (`release_device`, `cleanup`, `on_connection_lost`,
  Apply-Tausch) je Eintrag, aber höchstens ein Release-Frame je Konsolen-Taste,
  Zähler anschließend leer. Verifikation: Tests für Geräteverlust,
  Verbindungsverlust, Apply und Shutdown mit geteilter Taste; danach
  `engine.held == {}` und kein offener Zähler.
- [ ] 3.5 `engine.held` auf Schlüssel `(device, control)` umstellen und die
  Abfragen in `tests/test_mapping.py`, `tests/test_runtime.py` und
  `tests/test_ma2_client.py` anpassen. Verifikation: gesamte Suite grün.
- [ ] 3.6 Beschleunigungs-Rohwerte in `PlaybackRouter` auf DEBUG.
  Verifikation: `tests/test_playback.py` prüft mit `caplog` auf INFO-Level
  keine Beschleunigungszeile.

## 4. Web-Schicht

- [ ] 4.1 `PinSessions` (Ablauf, Sperre, injizierbare Uhr) einführen und die
  Token-Menge ersetzen; `login` liefert `429 pin_locked` mit `Retry-After`;
  PIN-Vergleich auf UTF-8-Bytes. Verifikation: `tests/test_web_auth.py` —
  abgelaufene Session → `401`, fünf Fehlversuche → `429`, richtige PIN nach
  Sperrende funktioniert und setzt den Zähler zurück, Logout widerruft.
- [ ] 4.2 `PUT /api/config` mit PIN-Änderung leert Sessions und stellt eine
  neue aus (bisheriges Verhalten bleibt). Verifikation: bestehender Test
  bleibt grün.
- [ ] 4.3 `learn_start` nutzt `_json_body()`. Verifikation:
  `tests/test_learn_api.py` — Array/String-Body → `400 invalid_json`.
- [ ] 4.4 `PinGate` zeigt die Meldung bei `429 pin_locked` an.
  Verifikation: Vitest in `PinGate.test.ts`.

## 5. Abschluss

- [ ] 5.1 Gesamte Testsuite, `npm test` und `npm run build` in `web/`.
  Verifikation: `.venv/bin/pytest -q` und die Web-Befehle laufen grün.
- [ ] 5.2 Live-Smoke auf dem Pi: Daemon per `systemctl stop` beenden (sauberes
  Journal), `[led]` in der Oberfläche aus- und einschalten, falsche PIN
  mehrfach eingeben. Verifikation: Journal und Oberfläche protokolliert.

## Workflow follow-up

- Change nach Review archivieren und die Deltas in die Haupt-Specs übernehmen.
