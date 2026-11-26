# Proposal

## Why

Die Oberfläche trägt derzeit den technischen Namen `ma2pi` und sieht aus wie ein
Entwicklerwerkzeug: Systemschrift, blaugraue Flächen, hartkodierte Hex-Werte in
`app.css` und vier Komponenten. Das Projekt ist aber ein eigenständiges Produkt
mit einem Namen — **gMA2PiControl** — und soll optisch zu
[sustain-vt.de](https://www.sustain-vt.de) passen, der Website des Betreibers.
Ein einheitliches, dunkles Erscheinungsbild mit grünem Akzent und klarer
Typografie macht die Oberfläche im Bühnenalltag schneller erfassbar und ordnet
sie sichtbar der Marke zu.

## What Changes

- **Produktname:** `gMA2PiControl` erscheint in Browser-Titel, Topbar,
  PIN-Gate, CLI (`--version`, `--help`, Startlog), API-Dokumentation und
  systemd-Beschreibung. Die technischen Bezeichner — Python-Paket `ma2pi`,
  Entrypoint, Service-User/-Unit, State-Verzeichnis, Passwortdatei,
  Recovery-SSID, Modulpfade — bleiben unverändert, damit es keine Migration und
  keinen Deploy-Bruch gibt.
- **Design-Tokens:** `web/src/app.css` erhält eine zentrale Token-Schicht
  (Farben, Typografie, Radien, Fokusring, Abstände). Alle Komponenten beziehen
  Farben und Schriften ausschließlich daraus; hartkodierte Hex-Werte außerhalb
  der Token-Definition entfallen.
- **Sustain-Palette:** Anthrazit `#0A0A0A`, Flächen `#1A1A1A`/`#2A2A2A`,
  Text `#F5F5F0`, gedimmt `#888888`, Akzentgrün `#6CBB89` mit
  `#4A9A6A`/`#7DD49B`. Blau `#2F6F9F` entfällt vollständig als UI-Akzent.
- **Typografie:** Bebas Neue für Marke und Überschriften, DM Sans für Fließtext
  und Bedienelemente. Beide werden als WOFF2 **lokal gebündelt** (ADR-0011:
  keine externen Hosts, Offline-Betrieb im Bühnen-LAN); OFL-Lizenzen liegen bei.
- **Semantik:** Erfolg, Fehler, Warnung und Fokus bleiben unterscheidbar und
  werden in die neue Palette eingepasst; die Geräteaufkleber-Palette
  (`green/blue/red/yellow/…` aus `config.toml`) bleibt inhaltlich erhalten, weil
  sie reale Keycap-Farben abbildet.
- **Favicon:** lokales SVG-Zeichen aus Fader, Encoder und Himbeere in Akzentgrün.
- **README:** Titel und Kurzbeschreibung auf gMA2PiControl; kurze Erwähnung von
  [sustain-vt.de](https://www.sustain-vt.de) als optische Referenz.
- **Nicht enthalten:** Umbenennung von Paket/Service/State-Pfaden, Änderungen an
  API-Pfaden, Konfigurationsschlüsseln oder dem Recovery-WLAN, Light-Mode,
  neues Layout-Konzept, Änderungen an Funktionen oder Datenmodell.
- **Abhängigkeit:** baut auf dem aktuellen Frontend-Stand
  (`add-device-layout-visuals`, noch nicht archiviert) auf; die
  Komponenten-Dateien `DevicesPage.svelte`, `AssignDialog.svelte`,
  `LearnPanel.svelte` und `DeviceSurface.svelte` werden mitgezogen.

## Capabilities

### New Capabilities

Keine.

### Modified Capabilities

- `config-ui`: sichtbarer Produktname, zentrale Design-Tokens, Sustain-Palette,
  lokal gebündelte Schriften, semantische Zustandsfarben und Favicon.

## Impact

- **Code:** `web/src/app.css` (Token-Schicht, Grundstyles),
  `web/src/App.svelte`, `web/src/lib/PinGate.svelte`,
  `web/src/lib/DevicesPage.svelte`, `web/src/lib/AssignDialog.svelte`,
  `web/src/lib/LearnPanel.svelte`, `web/src/lib/DeviceSurface.svelte`,
  `web/index.html`, `web/src/lib/brand.ts` (neu, Produktname),
  `ma2pi/__init__.py` (`PRODUCT_NAME`), `ma2pi/__main__.py`,
  `deploy/ma2pi.service`, `docs/api.md`, `README.md`,
  `web/public/favicon.svg` und `web/public/fonts/*` (neu).
- **Build:** `web/dist` wird neu gebaut und eingecheckt; `npm run check:offline`
  muss weiterhin grün sein (keine externen Hosts).
- **Tests:** Vitest-Texte, die `ma2pi` prüfen, werden auf den Produktnamen
  umgestellt; keine Backend-Verhaltensänderung.
- **Daten:** keine. Bestehende Konfigurationen bleiben gültig.
- **Risiko:** Bebas Neue hat nur Versalformen und einen Schnitt (400) — es darf
  nur für kurze Überschriften verwendet werden, nicht für Fließtext. Der
  Kontrast der gedimmten Textfarbe auf `#1A1A1A` ist grenzwertig und wird im
  Design geprüft.
