# Design

## Context

Siehe `proposal.md`. Ausgangslage im Code:

- `run_daemon()` (`ma2pi/__main__.py`) startet Encoder-, HID-, MIDI-, Input-,
  Learn-, Geräte-Learn- und Feedback-Task. Das `finally` bricht alle außer dem
  Geräte-Learn-Task ab und wartet auf sie.
- `EventBus.publish()` entfernt eine Queue bei `QueueFull` aus der
  Subscriber-Menge. Der WebSocket-Handler wartet danach weiter auf
  `queue.get()` und erfährt davon nichts.
- `ConfigStore` ruft nach jedem Apply die Activate-Hooks auf (`hid`, `midi`,
  `feedback`). `LearnManager.set_config` existiert, ist aber nirgends
  eingehängt. `_led_loop` bekommt die Start-`AppConfig` und läuft nur, wenn
  `led.enabled` beim Start `true` war.
- `MappingEngine._held` ist nach Control-Name geschlüsselt; `_release` prüft
  das Gerät nicht.
- PIN-Tokens liegen als `set[str]` im App-State. Die Cookie-Lebensdauer wird
  nur vom Browser durchgesetzt.

## Goals / Non-Goals

**Goals:**

- Jede Laufzeit-Konfigurationsänderung wirkt in allen Hilfsdiensten ohne
  Neustart.
- Kein Task und keine Verbindung bleibt nach Shutdown beziehungsweise
  Überlauf als Zombie bestehen.
- Kleine, lokale Änderungen ohne neue Konfigurationsschlüssel.

**Non-Goals:**

- Kein Schutz für das offene Internet. Offener Zugriff im Show-Netz ist
  Absicht (ADR-0013); `bind = "0.0.0.0"` und `pin_enabled = false` bleiben
  Default.
- Kein Redacting des Rettungs-WLAN-Passworts: Wer die Oberfläche erreicht, soll
  es sehen können.
- Kein Hashing der PIN in der TOML und keine pro-IP-Verwaltung.
- Keine neuen Funktionen für Mehrgeräte-Bedienung über die Held-Key-Korrektur
  hinaus (siehe D4).

## Decisions

### D1: Geräte-Learn-Task im Shutdown

Der Task wird wie `learn_task` abgebrochen und mit
`contextlib.suppress(CancelledError, Exception)` erwartet, vor
`engine.cleanup()`. Alternative „Task in eine Liste und generisch abbrechen“
wäre sauberer, ändert aber mehr Zeilen als nötig; die Liste ist ein
möglicher Folge-Refactor.

### D2: Überlauf als Signal statt Sentinel

Ein Sentinel in der Queue scheitert, weil sie bei Überlauf voll ist. Stattdessen
hält der Bus je Subscriber ein `asyncio.Event` („dropped“). `publish()` setzt es
bei `QueueFull` und entfernt den Subscriber aus der Auslieferung; der Handler
wartet zusätzlich auf dieses Event und schließt den WebSocket. Der Client
verbindet sich neu und erhält den Anfangsstand über `initial`. Bestehendes
Verhalten (`subscriber_count` sinkt, bereits eingereihte Events bleiben
lesbar) bleibt für direkte Queue-Nutzer erhalten.

### D3: Hilfsdienste über Activate-Hooks

`LearnManager.set_config` und `DeviceLearnManager.set_config` werden als
Activate-Hook eingehängt. Die zusätzliche Poll-Zeile in `_device_learn_loop`
kann entfallen. Die LED-Schleife wird in einen reinen Schritt
`_led_step(config, client, holder)` und die Schleife `_led_loop(engine, ...)`
getrennt, damit der Abgleich ohne Hardware testbar ist:

- `led.enabled = false` und LED offen: schließen (sendet `DISABLE`),
  `client.set_led(None)`.
- Offen, aber `settings` ungleich `config.led` oder Handle tot: schließen und
  neu öffnen.
- `led.enabled = true`, nichts offen: Pfad auflösen und öffnen.

Die Schleife läuft immer (Intervall 2 s, kostet im deaktivierten Fall nichts).

### D4: Held-Keys je `(device, control)`, Frames je Konsolen-Taste

Die Review-Annahme „hängende Tasten“ war überzogen: Heute wird ein zweiter
Press mit gleichem Control als Doppel-Press ignoriert, und das Release des
fremden Geräts gibt die Taste zu früh frei. Der eigentliche Fehler ist die
Schlüsselung nach Control-Name. Dieser Change behebt ihn an der Wurzel, damit
zwei Geräte unabhängig voneinander bedienbar sind.

Umfang im Code (`ma2pi/mapping.py`):

- `_held`, `_press_targets` und `_pending_hold` werden nach
  `(device, control)` geschlüsselt. Ein Doppel-Press desselben Geräts bleibt
  ignoriert.
- **Frames nach Konsolen-Taste**: Zwei Geräte können auf denselben Hardkey
  abgebildet sein. Würde jedes Gerät sein eigenes Press/Release senden, ließe
  das erste Release die Taste auf der Konsole los, obwohl das zweite Gerät noch
  hält. Deshalb führt die Engine je Hardkey-Name (und je Encoder-Slot für den
  Klick) einen Zähler der Halter: Press-Frame bei 0 → 1, Release-Frame bei
  1 → 0, Hold-Upgrade höchstens einmal je Taste.
- **Modifier bleiben gerätübergreifend**: `ultra`, `fine`, der Auflösungs-Zyklus
  und die MA-Abfrage prüfen heute `control in self._held` beziehungsweise
  den Keynamen. Sie wechseln auf einen Hilfsaufruf „von irgendeinem Gerät
  gehalten“. Die LED-Rückmeldung (`modifier_hook`) meldet beim ersten Halter
  „gedrückt“ und beim letzten „losgelassen“.
- `release_device`, `cleanup`, `on_connection_lost` und der Apply-Tausch
  arbeiten je Eintrag, geben aber je Konsolen-Taste höchstens ein Release-Frame
  aus; die Reihenfolge (umgekehrte Press-Reihenfolge) bleibt.
- Öffentliche Introspektion `engine.held` liefert künftig Schlüssel
  `(device, control)`. Sie wird nur von Tests benutzt (`tests/test_mapping.py`,
  `tests/test_runtime.py`, `tests/test_ma2_client.py`); die Abfragen wie
  `"ma" in engine.held` werden angepasst.

Verworfene Alternative: nur ein Release mit abweichendem `device` ignorieren.
Das ist kleiner, lässt aber den zweiten Press verloren gehen und das Release
des ersten Geräts die Taste trotzdem loslassen, während das zweite noch hält.

Risiko: Der Zähler ist neuer Zustand in einer sicherheitsrelevanten Stelle
(hängende Tasten auf der Konsole). Mitigation: ein Aufräumpfad gibt bei
Geräteverlust, Verbindungsverlust, Apply und Shutdown immer alles frei und
setzt die Zähler zurück; Tests prüfen, dass nach jedem dieser Pfade kein Zähler
übrig ist.

### D5: PIN-Sessions mit Ablauf und Sperre

Neue kleine Klasse `PinSessions` im Web-Modul statt `set[str]`:

- `issue()` vergibt einen Token mit Ablauf (`SESSION_TTL = 12 h`, gleich
  Cookie-`max_age`) und entfernt abgelaufene.
- `valid(token)` prüft Existenz und Ablauf; `revoke`/`clear` wie bisher.
- Sperre: Ab 5 aufeinanderfolgenden Fehlversuchen gilt eine Sperre von 15 s,
  die sich mit jedem weiteren Fehlversuch verdoppelt (Obergrenze 300 s). Eine
  richtige PIN setzt den Zähler zurück. Während der Sperre antwortet
  `/api/auth/login` mit `429 pin_locked` und `Retry-After`; Versuche zählen
  währenddessen nicht weiter.
- Die Sperre ist global, nicht pro IP: Das Netz ist klein und geschützt, und
  eine IP-Verwaltung hinter NAT oder Proxy wäre fehleranfällig.
- Die Uhr ist injizierbar (`time.monotonic`), damit Tests ohne Warten laufen.
- Der Vergleich nutzt `hmac.compare_digest` auf UTF-8-Bytes, damit Nicht-ASCII
  in der PIN keinen `TypeError` auslöst.

Risiko: Ein Bediener tippt im Stress fünfmal falsch und ist 15 s gesperrt.
Das ist für eine Show-Konsole akzeptabel; die PIN bleibt optional.

#### Kontext zur PIN-Sperre

**Ist-Zustand.** Ein falscher Login wird nur mit `asyncio.sleep(0.2)` beantwortet.
Das verzögert die Antwort, begrenzt aber nichts: Mehrere Anfragen laufen
parallel, jede wartet für sich 0,2 s. Die PIN hat laut `config.toml` 4–12
Ziffern; eine 4-stellige PIN (10⁴ Möglichkeiten) ist so in Sekunden bis
wenigen Minuten durchprobiert, eine 6-stellige in Stunden.

**Wirkung der Sperre.** Die ersten fünf Fehlversuche sind frei, dann gilt
15 s, 30 s, 60 s, 120 s, 240 s und ab dem zehnten Fehlversuch dauerhaft 300 s
je Versuch (maximal etwa 288 Versuche pro Tag). Eine 4-stellige PIN hält damit
im Mittel etwa 17 Tage, eine 6-stellige mehrere Jahre. Das ist keine
Absicherung gegen gezielte Angriffe, sondern verhindert, dass jemand im
Netz die PIN ohne Aufwand erraten kann.

**Was die Sperre nicht tut.**
- Sie trifft nur `/api/auth/login`, nicht bestehende Sessions: Ein bereits
  angemeldeter Bediener bleibt während einer Sperre voll arbeitsfähig.
- Sie liegt nur im Speicher: Ein Daemon-Neustart (`systemctl restart ma2pi`)
  hebt sie auf, ebenso eine PIN-Änderung in der `config.toml`.
- Sie betrifft die Datei-Konfiguration und die Rettungs-WLAN-Funktion nicht.

**Typische Reibung im Show-Betrieb.**
- Zwei Kollegen mit vergessener PIN sperren gemeinsam den Login für alle
  neuen Anmeldungen (globale Sperre). Bei laufender Show bleibt das ohne
  Auswirkung auf die angemeldete Konsole.
- Die Session läuft nach 12 h ab. Das entspricht dem Cookie-`max_age`, das der
  Browser schon heute durchsetzt; neu ist nur, dass der Server es ebenfalls
  prüft. Ein Mehr-Tage-Aufbau mit offener Seite muss sich also täglich neu
  anmelden.
- Die Sperrmeldung muss die Restzeit nennen (`Retry-After`), sonst wirkt die
  Oberfläche „kaputt“.

**Optionen.**

| Option | Vorteil | Nachteil |
|---|---|---|
| A: feste Konstanten (aktueller Stand der Spec) | Keine neuen Schlüssel, keine Migration, weniger Testmatrix | Nicht abschaltbar, nicht anpassbar |
| B: `web.pin_max_failures` und `web.pin_lockout_seconds` in der Config, `0` schaltet ab | Show-Teams können die Sperre lockern oder abschalten | Zwei neue Schlüssel mit Validierung, UI-Feld auf der Erweitert-Seite, README, Tests |
| C: Sperre je Client-IP statt global | Ein vertippender Kollege sperrt nicht alle | Zustand je IP (Speicherwachstum begrenzen), hinter NAT oder Proxy wirkungslos, Pi hängt aber meist direkt im LAN |
| D: Ablauf gleitend (Session verlängert sich bei Aktivität) statt fix 12 h | Kein Rauswurf bei langer Show | Session lebt bei Dauerbetrieb unbegrenzt; passt nicht zum festen Cookie |

Empfehlung: **A mit absolutem Ablauf**. Die Sperre ist ein Komfort-Schutz im
geschützten Netz; die Konstanten sind in einem Satz erklärbar. Wenn im
Betrieb Reibung entsteht, ist B der nächste Schritt, weil es die Konstanten
nur durch Konfigurationswerte ersetzt.

### D6: Log-Level und Body-Prüfung

`DEBUGACCEL` wird zu einer DEBUG-Zeile mit deutscher Beschreibung. Der
Learn-Start nutzt wie alle anderen Endpunkte `_json_body()`.

## Risks / Trade-offs

- [LED-Schleife läuft ohne `led.enabled`] → Mitigation: Der Schritt kehrt sofort
  zurück; Test deckt den Leerlauf ab.
- [Schließen des WebSockets bei Überlauf kann eine Reconnect-Schleife
  erzeugen, wenn der Client dauerhaft zu langsam ist] → Mitigation: Die UI
  reconnectet mit ihrem bestehenden Backoff; die Queue hat 200 Plätze und wird
  nach dem Anfangsstand geleert.
- [Globale PIN-Sperre sperrt auch legitime Nutzer] → in D5 bewusst akzeptiert.

## Migration Plan

Keine Konfigurationsmigration. Rollback: Commit zurücknehmen; es gibt keine
persistierten Zustände (Sessions und Sperrzähler liegen nur im Speicher).

## Open Questions

Keine. Entschieden am 2026-11-26:

- PIN-Sperre: feste Konstanten (Option A), keine neuen Config-Schlüssel.
  Konfigurierbar (Option B) ist ein möglicher Folge-Change, falls die Sperre im
  Betrieb stört.
- PIN-Session: fester Ablauf nach 12 h (kein gleitender Ablauf, Option D
  verworfen).
