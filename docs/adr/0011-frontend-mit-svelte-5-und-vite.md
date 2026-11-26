# 0011. Frontend mit Svelte 5 und Vite

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

## Kontext und Problemstellung

Die Oberfläche braucht Formulare für Zugangsdaten und Mapping, Tabellen für
Geräte und Controls, einen Learn-Modus mit Live-Events und Statusanzeigen. Zur
Laufzeit soll der Pi Python-only bleiben und keine Node-Anwendung betreiben.
Externe CDNs, Fonts oder Telemetrie sind ausgeschlossen. Ein Node-Buildschritt
ist ausdrücklich erlaubt.

## Entscheidungstreiber

* Gute UX für Mapping-Tabellen und Live-Learn
* Kleiner, statisch auslieferbarer Bundle
* Kein Node zur Laufzeit, keine SSR auf dem Pi
* Keine externen Assets oder Cloud-Abhängigkeiten
* Reproduzierbarer Build und klare Versionierung

## Betrachtete Optionen

* SvelteKit mit SSR/Node-Server
* SvelteKit mit `adapter-static`
* Svelte 5 + Vite als reine SPA
* React/Vue mit Vite
* Jinja2 + HTMX + SSE ohne Node-Build

## Entscheidung

Es wird Svelte 5 mit Vite und TypeScript als reine Single-Page-App verwendet.
Der Build erzeugt statische Dateien in `web/dist`, die der Python-Daemon
ausliefert. Es gibt kein SSR und keinen Node-Prozess auf dem Pi. `npm ci` und
`npm run build` laufen auf dem Entwicklungsrechner oder in CI; das Ergebnis wird
mit ausgeliefert. `package-lock.json` wird eingecheckt, Assets und Fonts liegen
lokal, es gibt keine CDN-Referenzen.

Die UI prüft beim Start `/api/version` und den Build-Stamp. Bei einer Abweichung
zeigt sie einen Hinweis und lädt neu, damit eine alte SPA nicht gegen eine neue
API arbeitet.

### Konsequenzen

* Gut, weil Svelte einen kleinen Bundle und reactive Formulare ohne Virtual DOM liefert.
* Gut, weil die Laufzeit auf dem Pi ausschließlich Python bleibt.
* Gut, weil Vite einen schnellen, reproduzierbaren Build mit Lockfile ermöglicht.
* Schlecht, weil ein Node/npm-Buildschritt und Frontend-Abhängigkeiten gepflegt werden müssen.
* Schlecht, weil ohne SSR die erste Anzeige clientseitig aufgebaut wird; für ein LAN-UI akzeptabel.
* Schlecht, weil Frontend- und Backend-Version gemeinsam ausgeliefert werden müssen.

### Bestätigung

Accepted, wenn die gebaute SPA ohne Internet vollständig lädt, keine externen
Netzwerkaufrufe macht, der Build mit `npm ci && npm run build` reproduzierbar
ist und die Versionsprüfung einen Mismatch erkennt.

## Vor- und Nachteile der Optionen

### SvelteKit mit SSR

* Gut, weil Routing und serverseitige Datenlogik komfortabel wären.
* Schlecht, weil ein Node-Server auf dem Pi liefe und dem Python-only-Ziel widerspricht.

### SvelteKit mit adapter-static

* Gut, weil Routing und statischer Export möglich sind.
* Schlecht, weil für eine einzelne Konfigurationsseite zusätzliche Komplexität ohne Nutzen entsteht.

### Svelte 5 + Vite SPA

* Gut, weil minimal, statisch und gut für interaktive Formulare.
* Gut, weil keine Server-Laufzeit nötig ist.
* Schlecht, weil Routing und Datenfluss selbst organisiert werden müssen.

### React/Vue mit Vite

* Gut, weil große Ökosysteme und viele Beispiele existieren.
* Schlecht, weil für diese Größe mehr Bundle und Boilerplate anfallen.

### Jinja2 + HTMX

* Gut, weil kein Node-Build und alles Python wäre.
* Schlecht, weil der interaktive Mapping-Editor und Live-Learn mehr clientseitige Logik erfordern und schneller unübersichtlich werden.

## Weitere Informationen

* Verwandt: ADR-0008, ADR-0012, ADR-0013
