# Proposal

## Why

Der Core-Daemon ist ohne SSH und TOML-Handarbeit kaum einrichtbar: MA2-Zugangsdaten, Geräte-IDs und das Tasten-/Encoder-Mapping müssen heute in einer Datei gepflegt werden. Ein lokales Web-Interface macht aus dem Pi ein bedienbares Gerät: Zugangsdaten eintragen und testen, Tasten und Encoder per Learn-Modus zuweisen, den Verbindungszustand sehen und Änderungen ohne Dienstneustart anwenden. Das Interface ist nur im LAN erreichbar und hängt nicht am Internet.

## What Changes

- Eingebetteter HTTP-/WebSocket-Server im Daemon-Prozess (`aiohttp`), der eine statische Svelte-5-SPA und eine JSON-API ausliefert.
- Konfigurations-API: lesen, validieren, schreiben, sichern und wiederherstellen; MA2-Passwort ausschließlich write-only.
- Geräte- und Mapping-Editor mit Learn-Modus: Taste drücken bzw. Encoder drehen, Roh-Event sehen und Aktion zuweisen.
- Live-Status: Verbindungszustand, Session, Geräte, Rate-Limiter und letzte Frames.
- Hot Reload: validierte Änderungen werden atomar angewendet, gehaltene Tasten vorher freigegeben, bei geänderten Zugangsdaten wird neu verbunden. Kein Dienstneustart.
- Aktive Konfiguration zieht von `/etc/ma2pi` nach `/var/lib/ma2pi`, inklusive Backups und atomarem Schreiben mit `tomlkit` (Kommentare bleiben erhalten).
- Frontend-Build mit Node/npm (Svelte 5 + Vite + TypeScript), ausgeliefert werden nur statische Dateien; zur Laufzeit bleibt der Pi Python-only.
- UI im LAN erreichbar; eine optionale PIN-Sperre ist standardmäßig aus und in der Oberfläche setzbar; ohne PIN erscheint ein Warnbanner.
- Neue ADRs 0008–0013; ADR-0004 und ADR-0006 werden zu Config-Pfad bzw. Hot Reload ergänzt.

Nicht enthalten: Zugriff aus dem Internet, Mehrbenutzer-/Rollenverwaltung, Cloud-Synchronisation, Fernsteuerung der onPC über das UI hinaus, Parameter-Unlock.

## Capabilities

### New Capabilities

- `config-ui`: Im LAN erreichbare Weboberfläche und JSON-API für Zugangsdaten, Geräte, Mapping, Learn-Modus, Status und Konfigurations-Backups.
- `runtime-config`: Validierung, atomares Schreiben und Hot Reload der Konfiguration inklusive Freigabe gehaltener Tasten, Mapping-Tausch und Reconnect bei geänderten Zugangsdaten.

### Modified Capabilities

Keine. Die Core-Specs aus `add-ma2pi-core` sind noch nicht archiviert; dieses Change ergänzt sie um neue Capabilities, ohne bestehende Anforderungen umzuschreiben.

## Impact

- **Code:** neues Paket `ma2pi/web/` (API, statische Assets), `ma2pi/config_store.py`, Erweiterungen an `mapping.py` und `ma2_client.py` für Reload und Learn-Modus; Frontend unter `web/`.
- **Abhängigkeiten:** `aiohttp` und `tomlkit` (PyPI); Node/npm nur als Build-Werkzeug, nicht zur Laufzeit.
- **System:** `/var/lib/ma2pi` als beschreibbarer Config-/Backup-Pfad, `ReadWritePaths` in der systemd-Unit, neuer LAN-Port (Default 8080).
- **Sicherheit:** LAN-Exposition mit optionaler PIN-Sperre (standardmäßig aus, Warnbanner); Passwörter und PIN werden nie zurückgegeben; schreibende API-Aufrufe nur als JSON mit eigenem Header; PIN in der Oberfläche setzbar.
- **Migration:** bestehende `/etc/ma2pi/config.toml` wird beim Installieren einmalig nach `/var/lib/ma2pi` übernommen und gesichert.
- **Risiko:** Ein offenes LAN-Interface kann Mapping und Zugangsdaten verändern; das ist eine bewusste, dokumentierte Entscheidung für v1.
