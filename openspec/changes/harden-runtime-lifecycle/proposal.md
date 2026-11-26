# Proposal

## Why

Ein Code-Review des gesamten Repos hat mehrere Lücken in Lebenszyklus,
Hot-Reload und Web-Schicht gefunden. Keine davon betrifft die Auslegung als
Werkzeug für geschützte Show-Netze (offenes LAN-Modell, Klartext-Anzeige des
Rettungs-WLAN-Passworts und Default `0.0.0.0` ohne PIN sind bewusst so und
bleiben unverändert). Die übrigen Funde sind echte Fehler oder
Inkonsistenzen:

- Beim Shutdown wird der Geräte-Learn-Task weder abgebrochen noch erwartet.
- Der Event-Bus meldet „trenne Verbindung“, trennt den WebSocket aber nicht;
  der Client hängt als Zombie ohne weitere Events.
- `LearnManager` und die LED-Schleife bekommen eine Konfigurationsänderung
  nicht mit, obwohl `runtime-config` „kein Dienstneustart“ verspricht.
- Die Engine führt gehaltene Tasten nur nach Control-Name. Haben zwei Geräte
  denselben Control, wird der zweite Press verschluckt und das Release des
  einen Geräts lässt die Taste los, obwohl das andere sie noch hält.
- PIN-Sessions laufen serverseitig nie ab, und falsche PINs werden nur um
  200 ms verzögert.
- Der Playback-Router schreibt bei jedem beschleunigten Wert eine
  Debug-Zeile auf Level INFO.
- `POST /api/learn/start` liefert bei einem Nicht-Objekt-Body `500` statt `400`.

## What Changes

- **Geordneter Shutdown**: Alle Hintergrund-Tasks des Daemons, auch der
  Geräte-Learn-Task, werden beim Beenden abgebrochen und erwartet.
- **Event-Stream schließt langsame Clients**: Läuft die Queue eines Clients
  über, schließt der Server dessen WebSocket; die Oberfläche verbindet sich neu
  und gleicht den Stand über `/api/status` ab.
- **Hilfsdienste folgen der aktiven Konfiguration**: `LearnManager` wird beim
  Apply mit der neuen Konfiguration versorgt. Die LED-Schleife liest die
  aktive Konfiguration, läuft immer und öffnet, schließt oder öffnet neu, wenn
  sich `[led]` ändert oder `led.enabled` umgeschaltet wird.
- **Held-Keys je Gerät**: Die Engine führt gehaltene Tasten nach
  `(Gerät, Control)`. Frames richten sich nach der Konsolen-Taste: Press beim
  ersten Halter, Release beim letzten. Modifier wirken weiter
  gerätübergreifend.
- **PIN-Sessions**: Serverseitiges Ablaufdatum je Session (gleich dem
  Cookie-`max_age`) und eine zeitlich wachsende Sperre nach aufeinanderfolgenden
  Fehlversuchen (`429 pin_locked` mit `Retry-After`).
- **Logging**: Beschleunigungs-Rohwerte werden auf Level DEBUG protokolliert.
- **Learn-API**: `POST /api/learn/start` prüft wie die anderen Endpunkte, dass
  der Body ein JSON-Objekt ist (`400 invalid_json`).
- **Nicht enthalten**: Absicherung für das offene Internet, PIN-Hashing in der
  TOML, Redaction des Rettungs-WLAN-Passworts, neue Authentifizierung.
- **BREAKING**: keine. Die PIN-Sperre ändert nur das Verhalten bei
  wiederholt falscher Eingabe.

## Capabilities

### New Capabilities

Keine.

### Modified Capabilities

- `runtime-config`: Hilfsdienste (Learn, LED) und Shutdown folgen dem Apply
  beziehungsweise sind vollständig.
- `config-ui`: Event-Stream bei Überlauf, PIN-Session-Ablauf und -Sperre,
  Body-Prüfung der Learn-API.
- `mapping-engine`: Schutz vor hängenden Tasten gilt je Gerät; neues
  Requirement für dieselbe Konsolen-Taste auf mehreren Geräten.
- `value-acceleration`: Rohwert-Protokollierung nur auf DEBUG.

## Impact

- **Code**: `ma2pi/__main__.py` (Shutdown, LED-Schleife, Hooks),
  `ma2pi/web/events.py` (Überlauf-Signal), `ma2pi/web/__init__.py`
  (PIN-Sessions, Learn-Body), `ma2pi/mapping.py` (Held-Keys je Gerät),
  `ma2pi/playback.py` (Log-Level), `ma2pi/learn.py` (nur Verdrahtung).
- **Konfiguration**: keine neuen Schlüssel; Sperrzeiten sind Konstanten.
- **Web-UI**: `PinGate` zeigt die Meldung bei `429 pin_locked` an
  (bestehende Fehleranzeige reicht, Test ergänzen).
- **Tests**: `tests/test_web.py` (Überlauf), `tests/test_web_auth.py`
  (Ablauf, Sperre), `tests/test_learn_api.py` (Body), `tests/test_mapping.py`
  (Held-Keys je Gerät, geteilte Konsolen-Taste), `tests/test_runtime.py` und
  `tests/test_ma2_client.py` (Anpassung an `engine.held`), `tests/test_cli.py` bzw. neu `tests/test_daemon_lifecycle.py`
  (Shutdown, LED-Reconcile), `tests/test_playback.py` (Log-Level).
- **Review-Bezug**: Findings 3–10 des Repo-Reviews vom 2026-11-26; Findings 1
  und 2 sind bewusst ausgenommen.
