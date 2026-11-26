# Tasks

## 1. Design-Tokens und Schriften

- [ ] 1.1 In `web/src/app.css` den `:root`-Block durch die Token-Schicht ersetzen (`--bg`, `--surface`, `--surface-raised`, `--surface-inset`, `--border`, `--border-strong`, `--text`, `--text-muted`, `--accent`, `--accent-dim`, `--accent-hover`, `--on-accent`, `--success`, `--danger`, `--warning` samt `-bg`-Varianten, `--radius`, `--font-display`, `--font-body`, `--tracking-label`); `color-scheme` auf `dark` setzen und Grundstyles (Body, Topbar, Buttons, Inputs) auf Tokens umstellen.
- [ ] 1.2 Bebas Neue 400 und DM Sans 400/500 als WOFF2 (latin, latin-ext) nach `web/public/fonts/` legen, `@font-face`-Regeln mit `font-display: swap` und `local`-freiem `src` in `app.css` ergänzen; OFL-Lizenztexte als `web/public/fonts/OFL-bebas-neue.txt` und `OFL-dm-sans.txt` beilegen.
- [ ] 1.3 Typografie-Regeln definieren: `h1`/`.section-title`/Dialogtitel in `--font-display`, Fließtext und Bedienelemente in `--font-body` (400/500), Versal-Labels mit `letter-spacing: var(--tracking-label)`; Mindestgröße für Bebas Neue auf 1,4 rem begrenzen.
- [ ] 1.4 Buttons und Formularfelder an die Vorlage anpassen: Primärbutton `--accent` auf `--on-accent`, Versal mit `.1em` Laufweite, `border-radius: var(--radius)`, Hover `--accent-hover` mit leichtem `translateY(-2px)`; Sekundärbutton mit `--border-strong` und Hover in `--accent`; Fokusring `2px solid var(--accent-hover)` mit `outline-offset: 2px`.

## 2. Komponenten auf Tokens umstellen

- [ ] 2.1 `web/src/lib/DeviceSurface.svelte`: Rahmen, Flächen, Beschriftungen und Auswahl auf Tokens umstellen; Auswahl-Outline von `#ffb347` auf `--accent-hover`; die Aufkleber-Palette (`green`, `blue`, `red`, `yellow`, `grey`, `black`, `white`) mit erklärendem Kommentar unverändert lassen.
- [ ] 2.2 `web/src/lib/DevicesPage.svelte`: alle Hex-Werte durch Tokens ersetzen, Tabellen, Karten und Zustandsflächen (Erfolg/Fehler/Warnung) auf die semantischen Tokens umstellen.
- [ ] 2.3 `web/src/lib/AssignDialog.svelte`: Dialogflächen, Rahmen, Fehlertexte und Buttonfarben auf Tokens umstellen.
- [ ] 2.4 `web/src/lib/LearnPanel.svelte`: Fortschritts-, Abbruch- und Hinweisflächen auf Tokens umstellen.
- [ ] 2.5 Übrige Seiten (`StatusPage`, `MappingPage`, `NetworkPage`, ggf. `ConfigPage`) auf verbleibende hartkodierte Hex-Werte prüfen und auf Tokens umstellen; LED-Farben (`#3ECF6E`, `#E35D5D`) bleiben mit Kommentar erhalten.

## 3. Branding gMA2PiControl

- [ ] 3.1 `PRODUCT_NAME = "gMA2PiControl"` in `ma2pi/__init__.py` ergänzen und in `ma2pi/__main__.py` für `prog`, `--version` und die Startlog-Zeile verwenden.
- [ ] 3.2 `web/src/lib/brand.ts` mit `PRODUCT_NAME` anlegen; `App.svelte` (Topbar zweifarbig, `gMA2` in `--accent`) und `PinGate.svelte` (Überschrift in `--font-display`) darauf umstellen.
- [ ] 3.3 `web/index.html`: `<title>gMA2PiControl</title>`, `theme-color` `#0A0A0A`, Verweis auf `/favicon.svg`.
- [ ] 3.4 `deploy/ma2pi.service` (nur `Description`) und `docs/api.md` (Titel) auf den Produktnamen umstellen; Unit-Name, User und Pfade unverändert lassen.
- [ ] 3.5 Tests anpassen: Vitest-Assertions auf `ma2pi` durch `PRODUCT_NAME` ersetzen; Python-Tests, die `--version` oder den Startlog prüfen, auf den neuen Namen umstellen (`tests/test_ma2_client.py`, `tests/test_config.py` o. a. gezielt suchen).

## 4. Favicon und README

- [ ] 4.1 `web/public/favicon.svg` als 32×32-SVG mit Fader, Encoder und Himbeere in `#6CBB89` auf `#0A0A0A` anlegen (nur Rechtecke/Kreise/Pfade, kein `<text>`); Entwurf liegt bereits im Repo und wird in 16/32/64 px geprüft.
- [ ] 4.2 README: Titel und Einleitungssatz auf gMA2PiControl umstellen, kurz die optische Referenz [sustain-vt.de](https://www.sustain-vt.de) und die verwendeten Schriften (Bebas Neue, DM Sans, OFL) nennen; Installations- und Pfadangaben nicht ändern.

## 5. Verifikation

- [ ] 5.1 `cd web && npm run check` läuft ohne Fehler.
- [ ] 5.2 `cd web && npm test` läuft grün (angepasste Branding-Assertions).
- [ ] 5.3 `cd web && npm run build` erzeugt neuen `web/dist`-Stand inklusive `fonts/` und `favicon.svg`.
- [ ] 5.4 `cd web && npm run check:offline` meldet keine externen Ressourcen.
- [ ] 5.5 `pytest -q` läuft grün.
- [ ] 5.6 Sichtprüfung im Browser: Topbar, PIN-Gate, Status, Mapping, Geräte (inkl. Aufkleberfarben), Zuweisungsdialog, Learn-Modus und Netzwerk; Fokusring per Tastatur prüfen; Kontrast von `--text-muted` auf `--surface` und `--surface-raised` stichprobenartig messen.

## 6. ADR

- [ ] 6.1 ADR `Produktname gMA2PiControl bei technischem Paketnamen ma2pi` per `adr new` anlegen (Status Proposed): Kontext, Entscheidung, Konsequenzen, Alternativen (vollständige Umbenennung, Alias-Paket).
- [ ] 6.2 Im neuen ADR auf `0011-frontend-mit-svelte-5-und-vite.md` (lokale Assets und Schriften) verweisen; `docs/adr/README.md` wird durch `adr` gepflegt.
