# Tasks

> Status: Proposal zur Review. Es werden noch keine Tasks abgehakt, bis
> Proposal, Specs, Design und ADRs freigegeben sind.

## 1. Backend und API-Grundlage

- [x] 1.1 `aiohttp` und `tomlkit` als Laufzeitabhängigkeiten ergänzen, `ma2pi/web/` mit App-Factory, Static-File-Serving und `/api/health`/`/api/version` anlegen; Test startet den Server auf einem freien Port und ruft beide Endpunkte ab. Ergebnis: `ma2pi/web/__init__.py` mit `create_app()`, `[web]`-Sektion (`bind`, `port`, `pin_enabled`), SPA-Fallback aus `web/dist`; Server läuft im Daemon und meldet sich im Log.
- [x] 1.2 API-Middleware für JSON-Pflicht und `X-Ma2pi-Request` bei schreibenden Aufrufen, einheitliche Fehlerantworten, Secret-Redaktion und deaktiviertes CORS implementieren; Tests prüfen 415/403, Redaktion und fehlende CORS-Header. Ergebnis: `request_guard` und `no_cors` als aiohttp-Middleware; Status-Endpunkt liefert nur Laufzeitdaten ohne Zugangsdaten.
- [x] 1.3 Event-Bus und WebSocket `/api/events` für Status-, Learn- und Log-Ereignisse implementieren; Test verbindet zwei Clients, sendet ein Ereignis und prüft Empfang sowie Reconnect nach Trennung. Ergebnis: `ma2pi/web/events.py` mit begrenzten Queues pro Client (langsame Clients werden getrennt), Status-Broadcast einmal pro Sekunde, Live-Test gegen den Daemon erfolgreich.

## 2. Config-Store und Hot Reload

- [x] 2.1 Config-Pfad auf `/var/lib/ma2pi/config.toml` und `/var/lib/ma2pi/ma2pi.password` umstellen, Migration aus `/etc/ma2pi` mit Backup implementieren; Test prüft Pfad, Rechte `0640`/`0600` und einmalige Migration. Ergebnis: `ma2pi/config_store.py` mit `ConfigPaths`, `ensure_layout()` (0750/0640/0600), `migrate()` (einmalig, Backup nach `backups/`, `password_file` wird per `tomlkit` umgeschrieben, Kommentare bleiben); `DEFAULT_CONFIG_PATHS` sucht zuerst unter `/var/lib/ma2pi`.
- [ ] 2.2 JSON-Merge-Patch über `tomlkit` anwenden, atomar schreiben (`fsync`, `os.replace`, Verzeichnis-`fsync`) und Backups (`last-good`, Zeitstempel, Rotation auf 20) anlegen; Tests für Kommentarerhalt, simulierten Abbruch und Backup-Inhalt.
- [ ] 2.3 Apply-Lock, Validierung, Freigabe gehaltener Tasten, Verwerfen offener Encoder-Deltas, Mapping-Tausch und Generationenzähler implementieren; Test mit gehaltenen MA+Store-Tasten prüft Release-Reihenfolge und neue Generation.
- [ ] 2.4 Verbindungstest und Reconnect bei geänderten Zugangsdaten implementieren (bestehende Session wiederverwenden, sonst kurzlebige Testsession); Tests für Erfolg, falsches Passwort, unerreichbaren Host und reine Mapping-Änderung ohne Session-Verlust.
- [ ] 2.5 Backup-API (auflisten, anlegen, wiederherstellen) implementieren; Tests prüfen Wiederherstellung, Validierung und dass ein ungültiges Backup die aktive Konfiguration nicht verändert.

## 3. Geräte- und Learn-API

- [ ] 3.1 `GET /api/devices` mit erkannten Geräten, Vendor-/Product-ID und logischen Controls implementieren; Test mit Fake-Geräteprofil prüft die Antwortstruktur.
- [ ] 3.2 `LearnManager` für Taste und Encoder implementieren: eine Sitzung, Timeout 15 s, Encoder-Fenster 2 s, Unterdrückung aller Mapping-Aktionen; Tests prüfen null gesendete Frames und korrekte Erfassung.
- [ ] 3.3 Learn-Start/-Abbruch und Learn-Events über WebSocket anbinden; Test prüft Event-Inhalt, Timeout-Rückkehr in den Normalbetrieb und Abbruch ohne Zustandsänderung.

## 4. Svelte-Frontend

- [ ] 4.1 Svelte 5 + Vite + TypeScript unter `web/` aufsetzen, `package-lock.json` einchecken, Build nach `web/dist` konfigurieren und alle Assets lokal halten; `npm ci && npm run build` läuft reproduzierbar durch.
- [ ] 4.2 Typisierten API-Client, Fehlerbehandlung und Versionsprüfung gegen `/api/version` implementieren; Vitest-Tests decken Erfolg, Validierungsfehler und Versionsmismatch ab.
- [ ] 4.3 Statusseite mit WebSocket-Store für Verbindung, Session, Geräte, Rate und letzte Frames bauen; Komponententest prüft Zustandswechsel und Reconnect-Anzeige.
- [ ] 4.4 MA2-Seite mit Host, Port, Benutzer, write-only Passwort und „Testen“-Funktion bauen; Test prüft, dass das Passwort nie angezeigt oder zurückgegeben wird.
- [ ] 4.5 Geräte- und Mapping-Editor mit Tabellen, Learn-Schaltflächen und Server-Validierung bauen; Komponententests decken Taste, Encoder, ungültiges Wheel und ungespeicherte Änderungen ab.
- [ ] 4.6 Backup-/Erweitert-Seite mit Backup-Liste, Restore-Bestätigung und Rate-/Logging-Einstellungen bauen; Test prüft Bestätigungsschritt und Fehleranzeige.
- [ ] 4.7 Build auf externe Netzwerkaufrufe prüfen (keine CDN-/Font-/Telemetrie-URLs) und Offline-Laden im Browser verifizieren; Ergebnis im README dokumentieren.

## 5. Deployment und Migration

- [ ] 5.1 systemd-Unit um `StateDirectory=ma2pi` und `ReadWritePaths=/var/lib/ma2pi` ergänzen; `systemd-analyze verify` ist grün und der Dienst schreibt nur in diesen Pfad.
- [ ] 5.2 `install.sh` um Verzeichnisanlage, Config-Migration, Rechte, Web-Dist-Prüfung und idempotente Wiederholung erweitern; zweimaliger Lauf auf Trixie endet fehlerfrei.
- [ ] 5.3 README für LAN-Port, UI-Zugriff, Sicherheitsmodell, Backup/Restore und Rollback schreiben; die dokumentierten Befehle werden auf dem Pi einmal ausgeführt.

## 6. Integration und Abnahme

- [ ] 6.1 API-Integrationstest mit `tests/mock_ma2.py`: Konfiguration lesen, ändern, anwenden und Status prüfen; dabei bleibt die Mock-Session bei reiner Mapping-Änderung bestehen.
- [ ] 6.2 Browser-Smoke-Test im LAN: Status, Zugangsdaten-Test, Taste/Encoder lernen, Mapping anwenden, Backup wiederherstellen; Ergebnis protokollieren.
- [ ] 6.3 Hot-Reload-Abnahme: Mapping bei gehaltener MA+Store-Taste anwenden, keine hängenden Modifier, gleiche Prozess-ID, kein systemd-Neustart.
- [ ] 6.4 Sicherheitsabnahme: Passwort erscheint in keiner Antwort und keinem Log, einfacher Formular-POST wird abgelehnt, UI ist aus dem LAN erreichbar und ohne Internet vollständig bedienbar.
- [ ] 6.5 ADR-Status nach Nachweis aktualisieren: 0008–0013 auf Accepted; die Links 0009→0004 und 0010→0006 bleiben als „Amends“ erhalten.

## 7. Dokumentation und Abschluss

- [ ] 7.1 API-Referenz mit Endpunkten, Payloads, Fehlercodes und Beispielen schreiben; Abgleich mit den implementierten Handlern ist vollständig.
- [ ] 7.2 `openspec validate --strict` für beide Changes ausführen; keine Fehler oder Warnungen.
- [ ] 7.3 Vollständige Testsuite (`pytest`, `npm run check`, `npm run build`) auf Entwicklungsrechner und Pi ausführen; alle Tests grün.
- [ ] 7.4 Abschlussreview gegen `config-ui` und `runtime-config`; jede Anforderung hat einen Nachweis oder eine begründete Ausnahme.

## Workflow follow-up

- Proposal, Specs, Design und ADRs zur Review vorlegen und Freigabe abwarten.
- Erst nach Freigabe implementieren und Tasks abhaken.
- Change nach bestandener Abnahme archivieren und Haupt-Specs synchronisieren.
