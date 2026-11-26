# Design

## Context

Siehe `proposal.md` für Motivation und Scope. Aufbauend auf `add-ma2pi-core`
existiert ein headless Daemon mit TOML-Konfiguration unter `/etc/ma2pi`, ohne
Schreibzugriff und ohne Hot Reload. Das UI ändert drei Randbedingungen:

1. Der Dienst braucht einen beschreibbaren Config-Pfad.
2. Konfigurationsänderungen müssen im laufenden Betrieb sicher angewendet werden.
3. Es entsteht eine LAN-Schnittstelle, die Zugangsdaten und Mapping verändert.

Die Core-Specs bleiben gültig; dieses Design ergänzt sie.

## Goals / Non-Goals

**Goals:**

* Bedienung ohne SSH: Zugangsdaten, Geräte und Mapping im Browser.
* Learn-Modus für Tasten und Encoder mit echten Geräte-Events.
* Hot Reload ohne Dienstneustart und ohne hängende Modifier.
* Kommentare in der TOML-Datei bleiben bei Änderungen erhalten.
* Eine statische Svelte-Oberfläche ohne Laufzeit-Abhängigkeit von Node oder CDN.
* Klare Trennung zwischen UI, Config-Store und laufender Runtime.

**Non-Goals:**

* Internet-Exposition, TLS-Terminierung, Mehrbenutzerbetrieb oder Rollen.
* PIN-Login als vollständige Benutzerverwaltung; die einfache PIN-Sperre
  schützt nur den LAN-Zugriff.
* Bearbeitung beliebiger MA2-Objekte (Cues, Presets, Executor-Layouts).
* Live-Fernsteuerung der onPC über das UI hinaus.
* Ein zweiter Dienst, nginx oder eine Datenbank.

## Decisions

### Eingebetteter HTTP-Server im Daemon

`aiohttp` läuft im selben asyncio-Loop wie HID, Mapping und MA2-Client. Der
Server liefert die statische SPA aus `web/dist` und die JSON-API unter `/api`.
Ein WebSocket unter `/api/events` verteilt Status-, Learn- und Log-Ereignisse.

Alternative: separater FastAPI/uvicorn-Dienst. Verworfen, weil zwei Prozesse,
zwei Lifecycles und eine zusätzliche Schnittstelle für Geräte-/Session-Zugriff
nötig wären. `aiohttp` deckt HTTP, Static Files und WebSocket in einer
Abhängigkeit ab.

### Konfigurationsspeicherung

Die aktive Konfiguration liegt unter `/var/lib/ma2pi/`:

```
/var/lib/ma2pi/
  config.toml                 # 0640 ma2pi:ma2pi
  ma2pi.password              # 0600 ma2pi:ma2pi
  backups/
    config-20261125-153000.toml
    last-good.toml
```

`/etc/ma2pi` bleibt nur für die Erstinstallation und systemweite Dateien. Die
systemd-Unit erhält `StateDirectory=ma2pi` (legt `/var/lib/ma2pi` mit den
richtigen Rechten an) und `ReadWritePaths=/var/lib/ma2pi`. `ProtectSystem=strict`
bleibt bestehen.

Schreiben erfolgt atomar:

1. `tomlkit` lädt das bestehende Dokument und wendet einen JSON-Merge-Patch an.
2. Das Ergebnis wird mit demselben Validator wie beim Start geprüft.
3. Die aktuelle Datei wird nach `backups/config-<timestamp>.toml` und
   `backups/last-good.toml` kopiert.
4. Die neue Datei wird als temporäre Datei im selben Verzeichnis geschrieben,
   `flush`, `fsync`, `chmod 0640`, dann `os.replace`.
5. Das Verzeichnis wird `fsync`t.

`tomlkit` erhält Kommentare und Formatierung an unveränderten Stellen. Werden
Arrays wie `[[mapping.encoders]]` komplett ersetzt, gehen Kommentare innerhalb
dieses Arrays verloren; das ist dokumentiert und akzeptiert. Die letzten 20
Backups werden aufbewahrt.

### Hot-Reload-Ablauf

Ein `ConfigStore` hält die aktive `RuntimeConfig` und einen monotonen
`generation`-Zähler. Ein `asyncio.Lock` serialisiert Apply-Aufrufe.

```
validate candidate
      │
      ├─ credentials changed? ──► test_connection(candidate)
      │                                │ fail ──► 422, alte Config bleibt
      ▼
persist atomically (backup + replace)
      ▼
release held keys (reverse order), cancel encoder deltas
      ▼
swap RuntimeConfig + Mapping in-memory
      ▼
credentials changed? ──► close old session, connect new
      │ no
      ▼
keep session, generation++, resume input
```

Während des Apply werden neue Eingabeereignisse verworfen und im UI als
„busy“ angezeigt. Das verhindert halbe Chords über die Umschaltgrenze. Die
Freigabe gehaltener Tasten erfolgt über den alten Zustand, bevor der neue
Zustand aktiv wird. Schlägt das Schreiben fehl, bleibt die alte Konfiguration
aktiv. Schlägt die Verbindung nach erfolgreichem Apply fehl, bleibt die neue
Konfiguration aktiv (die Zugangsdaten wurden vorher getestet) und der normale
Reconnect greift.

### Learn-Modus

Ein `LearnManager` hält höchstens eine Sitzung mit Timeout (Default 15 s).

* **Taste:** Der nächste Key-Down wird samt Rohcode und logischem Namen
  erfasst; das zugehörige Key-Up wird geschluckt. Während des Learn-Modus werden
  **alle** Mapping-Aktionen unterdrückt, damit keine halben Kombinationen an die
  onPC gehen.
* **Encoder:** Über ein kurzes Fenster (Default 2 s) werden Achse, Richtung und
  Detents gesammelt und als Vorschlag angezeigt.
* **Ende:** Erfolg, Timeout oder Abbruch stellen den normalen Betrieb wieder
  her. Es gibt keine dauerhafte Änderung, solange der Benutzer nicht speichert.

Die erfassten Events werden über `/api/events` an alle UI-Clients gesendet.

### API

| Methode | Pfad | Zweck |
| --- | --- | --- |
| GET | `/api/status` | Verbindung, Session-Ziel, Geräte, Rate, letzte Frames, Generation |
| GET | `/api/config` | Redigierte Konfiguration (ohne Passwort) |
| PUT | `/api/config` | JSON-Merge-Patch validieren, speichern, anwenden |
| POST | `/api/config/validate` | Patch prüfen, ohne zu speichern |
| POST | `/api/test-connection` | Zugangsdaten testen (Passwort optional) |
| GET | `/api/devices` | Erkannte Geräte und Controls |
| POST | `/api/learn/start` | Learn-Sitzung für `key` oder `encoder` starten |
| POST | `/api/learn/cancel` | Learn-Sitzung abbrechen |
| GET | `/api/backups` | Backups auflisten |
| POST | `/api/backups` | Backup anlegen |
| POST | `/api/backups/{id}/restore` | Backup validieren und anwenden |
| WS | `/api/events` | Status, Learn-Events, Logzeilen |
| GET | `/api/version` | API- und UI-Version für Kompatibilitätsprüfung |

Die API arbeitet mit einem JSON-Modell der Konfiguration, nicht mit rohem
TOML-Text. `PUT` erwartet einen Merge-Patch (RFC 7386), damit unveränderte
Bereiche und ihre Kommentare erhalten bleiben.

### Zugriffsmodell

* Bind-Adresse und Port sind konfigurierbar (`[web] bind`, `port`), Default
  `0.0.0.0:8080` für LAN-Zugriff.
* Eine einfache PIN-Sperre ist optional und standardmäßig aus
  (`[web].pin_enabled = false`, `[web].pin = ""`). Ist eine PIN gesetzt, besteht
  sie aus 4–12 Ziffern, wird nie zurückgegeben und ist in der Oberfläche unter
  **Erweitert** änderbar. Ohne PIN zeigt die Oberfläche einen Warnbanner.
* Nach korrekter PIN setzt der Daemon ein `HttpOnly`-Cookie mit einer
  In-Memory-Session. Alle `/api/`-Pfade außer Health, Version und den
  Auth-Endpunkten verlangen diese Session. Ein Dienstneustart beendet alle
  Sessions.
* Schreibende Aufrufe müssen `Content-Type: application/json` und den Header
  `X-Ma2pi-Request: 1` tragen; einfache Formular-POSTs werden abgelehnt. Das ist
  kein Auth-Ersatz, verhindert aber triviale CSRF-Versuche aus dem Browser.
* Das MA2-Passwort wird nur geschrieben, nie gelesen. `GET /api/config` liefert
  `password_set: true|false` und `pin_set: true|false` statt der Werte.
  Fehler und Logs redigieren beide Felder.
* Keine CORS-Freigabe; die SPA wird same-origin ausgeliefert.
* Keine externen Assets, Fonts, Icons oder Telemetrie.

### Verbindungstest

Ist bereits eine Session zum selben Ziel aktiv, prüft der Test die bestehende
Verbindung (Keepalive/`getdata` mit Antwort-Timeout) und öffnet keine zweite
Session. Für ein anderes Ziel wird eine kurzlebige Verbindung geöffnet,
eingeloggt und sofort mit `closeConnection` geschlossen. Ein
Verbindungslimit der onPC wird als verständlicher Fehler gemeldet. Der Test
verändert nie die aktive Konfiguration.

### Frontend

* Svelte 5 + Vite + TypeScript als reine SPA, kein SvelteKit-SSR.
* Seiten: Status, MA2, Geräte, Mapping (Tasten/Encoder), Erweitert, Backups.
* Ein zentraler API-Client mit typisierten Antworten, ein WebSocket-Store für
  Live-Daten, Formulare mit Server-Validierung.
* Keine UI-Bibliothek mit CDN-Zwang; systemnahe Fonts und inline SVG.
* Build mit `npm ci && npm run build`; das Ergebnis `web/dist` wird von Python
  ausgeliefert. Node wird zur Laufzeit nicht benötigt. `package-lock.json` wird
  eingecheckt; der Build läuft auf dem Entwicklungsrechner oder in CI, nicht
  zwingend auf dem Pi.
* `GET /api/version` und ein Build-Stamp verhindern, dass eine alte SPA gegen
  eine neue API läuft; bei Mismatch zeigt die UI einen Hinweis.

### Deployment-Änderungen

* Unit: `StateDirectory=ma2pi`, `ReadWritePaths=/var/lib/ma2pi`; der Rest des
  Hardings aus ADR-0004 bleibt.
* `install.sh` legt `/var/lib/ma2pi` an, migriert eine vorhandene
  `/etc/ma2pi/config.toml` einmalig (mit Backup), setzt Rechte und startet den
  Dienst.
* Neuer LAN-Port 8080; die Firewall des Pi bleibt unangetastet, die
  Erreichbarkeit wird im README dokumentiert.
* Backups liegen unter `/var/lib/ma2pi/backups` und werden nicht von
  `ProtectSystem=strict` blockiert.

## Risks / Trade-offs

* **Offenes LAN-UI ohne Internet** → PIN optional (standardmäßig aus, Banner
  warnt); nur LAN, keine Internet-Exposition, JSON+Header-Pflicht, Passwort und
  PIN nie lesbar. Die PIN ist ein einfacher Schutz, kein TLS- oder Rollenersatz.
* **Passwort über HTTP im LAN** → Risiko akzeptiert; keine Cloud, keine
  Internet-Route; bei Bedarf später TLS oder Reverse Proxy.
* **Hot Reload trifft gehaltene Tasten** → Apply-Lock, Freigabe in umgekehrter
  Reihenfolge, Verwerfen von Events während des Apply, Tests mit MA+Store.
* **Config-Datei beschädigt** → atomarer Replace, `fsync`, Backup vor jedem
  Schreiben, `last-good`-Kopie, Restore über die UI.
* **Kommentarverlust in ersetzten Arrays** → mit `tomlkit` nur innerhalb
  ersetzter Arrays; im README dokumentiert, Tests prüfen unveränderte Bereiche.
* **Zwei Prozesse schreiben gleichzeitig** → nur der Daemon schreibt; die UI
  spricht ausschließlich über die API. Manuelle Editor-Änderungen werden beim
  nächsten Apply erkannt und validiert.
* **MA2-Verbindungslimit beim Test** → bestehende Session wiederverwenden,
  temporäre Session sofort schließen, Limitfehler klar melden.
* **Frontend-Build-Supply-Chain** → Lockfile, `npm ci`, Build auf Entwickler-
  rechner/CI, ausgeliefertes `dist` ohne CDN; keine Runtime-Abhängigkeit.
* **UI/API-Versionsmismatch nach Update** → `/api/version` plus Build-Stamp,
  UI zeigt Hinweis und lädt neu.

## Migration Plan

1. Neue Version installieren, Dienst stoppen.
2. `install.sh` legt `/var/lib/ma2pi` an, migriert eine vorhandene
   `/etc/ma2pi/config.toml` nach `/var/lib/ma2pi/config.toml` und sichert die
   alte Datei.
3. Unit auf `StateDirectory`/`ReadWritePaths` umstellen, `daemon-reload`.
4. Dienst starten, UI im LAN öffnen, Verbindung testen, Mapping prüfen.
5. Erste Änderung anwenden und Generation/Status kontrollieren.

Rollback: Dienst stoppen, alte Unit und `/etc/ma2pi/config.toml` wiederherstellen,
`daemon-reload`, alte Version starten. Die Backups unter
`/var/lib/ma2pi/backups` bleiben erhalten.

## ADR-Übersicht

| ADR | Thema | Status |
| --- | --- | --- |
| 0008 | Eingebettete Web-UI-Architektur | Proposed |
| 0009 | Config-Speicherung, Schreibrechte und Backups | Proposed |
| 0010 | Hot-Reload-Semantik | Proposed |
| 0011 | Frontend-Stack Svelte 5 + Vite | Proposed |
| 0012 | Learn-Modus und Live-Event-Stream | Proposed |
| 0013 | LAN-Zugriffsmodell mit einfacher PIN-Sperre | Proposed |
