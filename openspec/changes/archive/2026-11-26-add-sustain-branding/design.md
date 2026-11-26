# Design

## Context

Die Oberfläche ist eine in den Daemon eingebettete Svelte-5-SPA
(`web/src/App.svelte`) mit fünf Seiten. Es gibt **keine Token-Schicht**: `app.css`
setzt `:root` auf Systemschrift und `#101418`, alle weiteren Farben stehen als
Hex-Werte über 432 Zeilen verteilt; vier Komponenten (`DevicesPage`,
`AssignDialog`, `LearnPanel`, `DeviceSurface`) führen zusätzlich eigene
`<style>`-Blöcke mit duplizierten Werten. Ein Wechsel der Optik ist heute nur
durch Suchen-und-Ersetzen an vielen Stellen möglich.

Zwei Randbedingungen sind bindend:

- ADR-0011 verbietet externe Assets und Schriften; `web/scripts/check-offline.mjs`
  prüft den Build auf fremde Hosts in `src`, `href` und `url()`.
- Die Oberfläche läuft im isolierten Bühnen-LAN ohne Internetzugang. Schriften
  müssen deshalb Teil des Builds sein.

Die Referenz `sustain-vt.de` verwendet: `#0A0A0A` (Basis), `#F5F5F0` (Text),
`#6CBB89`/`#4A9A6A`/`#7DD49B` (Grün), `#1A1A1A`/`#2A2A2A` (Flächen), `#888888`
(gedimmt), Bebas Neue (Display, 400) und DM Sans (Text, 300–500), harte Kanten
(2 px), dünne helle Rahmen, Versal-Labels mit weitem Letter-Spacing und grüne
Primärbuttons mit schwarzer Schrift.

## Goals / Non-Goals

**Goals:**

- Eine einzige Token-Schicht, aus der alle UI-Farben, Schriften und Radien
  kommen.
- Optik und Typografie erkennbar an sustain-vt.de, ohne die Informationsdichte
  einer Bedienoberfläche zu opfern.
- Produktname gMA2PiControl an allen sichtbaren Stellen, ohne technische
  Bezeichner zu brechen.
- Offline-Fähigkeit und bestehende Tests bleiben erhalten.

**Non-Goals:**

- Umbenennung von Python-Paket, Entrypoint, Service-User, StateDirectory,
  Konfigurationspfaden, API-Routen oder Recovery-SSID.
- Light-Mode oder Theme-Umschalter — die Vorlage ist dunkel, und ein zweites
  Theme ohne Gestaltungsgrundlage wäre halbfertig.
- Neues Seitenlayout, neue Komponenten, geänderte Interaktionsmuster.
- Änderung der Geräteaufkleber-Palette in `config.toml` (bildet reale Keycaps
  ab) und der LED-Farben (bilden reale Hardware ab).

## Decisions

### 1. Token-Schicht als CSS-Custom-Properties in `app.css`

`app.css` erhält einen `:root`-Block mit semantischen Tokens; Komponenten
verwenden ausschließlich `var(--…)`. Die Token-Namen sind Englisch (CSS-Konvention),
Kommentare Deutsch wie im restlichen Code.

| Token | Wert | Verwendung |
|---|---|---|
| `--bg` | `#0A0A0A` | Body, Seitenhintergrund |
| `--surface` | `#1A1A1A` | Topbar, Karten, Dialoge |
| `--surface-raised` | `#2A2A2A` | Buttons, Hover, aktive Zeilen |
| `--surface-inset` | `#111111` | Eingabefelder, Code, Listen |
| `--border` | `rgba(245,245,240,.14)` | Standardrahmen |
| `--border-strong` | `rgba(245,245,240,.28)` | Hover, ausgewählte Rahmen |
| `--text` | `#F5F5F0` | Standardtext |
| `--text-muted` | `#9C9C95` | Sekundärtext, Labels |
| `--accent` | `#6CBB89` | Primäraktion, aktiver Zustand |
| `--accent-dim` | `#4A9A6A` | Akzentrahmen, sekundärer Akzent |
| `--accent-hover` | `#7DD49B` | Hover, Fokusring, Mehrfachauswahl |
| `--on-accent` | `#0A0A0A` | Text auf Akzentfläche |
| `--success` / `--success-bg` | `#8FD3A0` / `#16261B` | Erfolgsmeldung |
| `--danger` / `--danger-bg` | `#E8958A` / `#2A1715` | Fehler |
| `--warning` / `--warning-bg` | `#E7CB84` / `#2A2413` | Warnung |
| `--radius` | `2px` | Buttons, Felder, Karten |
| `--font-display` | `"Bebas Neue", "DM Sans", sans-serif` | Marke, Überschriften |
| `--font-body` | `"DM Sans", system-ui, sans-serif` | Fließtext, Bedienelemente |
| `--tracking-label` | `.12em` | Versal-Labels |

`--text-muted` ist bewusst `#9C9C95` statt des Website-Werts `#888888`: auf
`--surface-raised` erreicht `#888888` nur 3,8:1, `#9C9C95` etwa 5,0:1.
`#888888` bleibt für dekorative, nicht zu lesende Elemente erlaubt.

### 2. Abbildung der Altfarben

| Alt | Neu | Bedeutung |
|---|---|---|
| `#101418` | `--bg` | Body |
| `#161c22`, `#1f242b`, `#12161b` | `--surface` | Topbar, Karten, Dialog |
| `#202932`, `#293542` | `--surface-raised` | Button, Hover |
| `#0c1116` | `--surface-inset` | Eingaben |
| `#2b333c`, `#2c333d` | `--border` | Rahmen |
| `#33404c`, `#39424e` | `--border-strong` | kräftige Rahmen |
| `#e7ecf1`, `#f4f4f4` | `--text` | Text |
| `#93a1af`, `#98a4b3`, `#b8c4d0` | `--text-muted` | Sekundärtext |
| `#2f6f9f`, `#4a8dc0`, `#16232d` | `--accent`, `--accent-dim` | Akzent, aktiv |
| `#8bd49c`, `#3ecf6e` | `--success` bzw. unverändert (LED) | Erfolg, LED |
| `#ff9c9c`, `#ffb4b4`, `#ff9b8f`, `#e35d5d` | `--danger` bzw. unverändert (LED) | Fehler, LED |
| `#f4d98a`, `#ffd2b3` | `--warning` | Warnung |
| `#17301f`, `#2f6f45` | `--success-bg` | Erfolgsfläche |
| `#341a1a`, `#4a2414`, `#7a3a3a`, `#8a3b3b` | `--danger-bg` | Fehlerfläche |
| `#2a2412`, `#4a3a14`, `#7a6220`, `#8a4a2a` | `--warning-bg` | Warnfläche |
| `#ffb347` | `--accent-hover` | Mehrfachauswahl |
| `#555` | `--border` | deaktivierter Rahmen |
| `#000a` | `rgba(10,10,10,.65)` | Overlay |

Ausnahmen bleiben hartkodiert und werden im Code kommentiert: die
Aufkleber-Palette in `DeviceSurface.svelte` (`green`, `blue`, `red`, `yellow`,
`grey`, `black`, `white`) und die LED-Farben (`#3ECF6E` grün, `#E35D5D` rot),
weil sie reale Hardware bzw. Keycaps abbilden und in `config.toml` als
semantische Namen referenziert werden.

### 3. Typografie: Bebas Neue nur als Display-Schrift

Bebas Neue hat ausschließlich Versalformen und einen Schnitt. Sie wird deshalb
 nur für Marke, Seiten- und Dialogtitel sowie Kartenüberschriften ab 1,4 rem
eingesetzt; Fließtext, Tabellen, Formulare und Buttons nutzen DM Sans.
Bedienelemente erhalten `font-weight: 500`, Versal-Labels
`text-transform: uppercase` und `letter-spacing: var(--tracking-label)`.

Der Produktname in der Topbar wird zweifarbig gesetzt (`gMA2` in `--accent`,
`PiControl` in `--text`), im PIN-Gate einzeilig in Bebas Neue.

### 4. Schriften lokal bündeln, keine externen Hosts

Die WOFF2-Dateien liegen unter `web/public/fonts/` und werden per `@font-face`
in `app.css` mit absoluten Pfaden (`/fonts/…`) eingebunden; Vite kopiert
`public/` unverändert in den Build. Es werden nur die tatsächlich genutzten
Schnitte gebündelt:

- Bebas Neue 400 (latin, latin-ext)
- DM Sans 400 und 500 (latin, latin-ext)

Der Schnitt 300 entfällt, weil DM Sans in der Bedienoberfläche bei 1 rem zu
dünn wirkt. Die OFL-Lizenztexte liegen als `web/public/fonts/OFL-bebas-neue.txt`
und `OFL-dm-sans.txt` bei und werden im README erwähnt. `check-offline` bleibt
unverändert und muss weiterhin grün sein.

### 5. Produktname als je eine Konstante pro Laufzeit

- Python: `PRODUCT_NAME = "gMA2PiControl"` in `ma2pi/__init__.py`; verwendet für
  `argparse(prog=…)`, `--version`, Startlog und die systemd-`Description`.
- Frontend: `web/src/lib/brand.ts` mit `export const PRODUCT_NAME`; verwendet in
  Topbar, PIN-Gate und `<title>` (Titel bleibt statisch in `index.html`, weil
  Vite ihn zur Buildzeit setzt).
- README, `docs/api.md` und `deploy/ma2pi.service` nennen den Produktnamen
  direkt; Unit-Name, User und Pfade bleiben `ma2pi`.

Alternative: das Paket umbenennen. Verworfen, weil Imports, Entrypoint,
Service-User, StateDirectory, Deploy-Skripte und bestehende Installationen
brechen würden, ohne dass der Nutzer etwas davon sieht. Die Entscheidung wird
als ADR festgehalten (Status Proposed).

### 6. Favicon als lokales SVG

`web/public/favicon.svg` (32×32): schematisches Kontrollpanel aus drei Motiven —
ein Fader mit Bahn und Kappe, ein Encoder als Ring mit Zeiger und darunter eine
Himbeere als Drupelet-Traube mit Stiel. Alles als Rechtecke, Kreise und Pfade —
kein `<text>`, damit keine Schrift zur Laufzeit nötig ist. Der Grund ist
`#0A0A0A`, die Formen sind `#6CBB89` (Bahn und Stiel `#4A9A6A`), damit das
Zeichen auf hellen wie dunklen Tab-Leisten funktioniert. Die Himbeere ist eine
eigene schematische Zeichnung, nicht das offizielle Raspberry-Pi-Logo. Bei 16 px
bleibt es ein kompaktes Zeichen, ab 32 px sind die drei Motive erkennbar.
`index.html` erhält
`<link rel="icon" type="image/svg+xml" href="/favicon.svg">` und
`<meta name="theme-color" content="#0A0A0A">`.

### 7. Semantik bleibt, Kontrast wird geprüft

Erfolg/Fehler/Warnung bleiben zusätzlich durch Text und Symbol erkennbar, nicht
nur durch Farbe. Für Text auf den jeweiligen Hintergründen gilt mindestens
4,5:1; der Fokusring (`2px solid var(--accent-hover)`, `outline-offset: 2px`)
ist auf allen Flächen sichtbar.

## Risks / Trade-offs

- **Dichte Oberfläche vs. Display-Typografie:** Bebas Neue ist schmal und hoch;
  bei zu häufiger Verwendung leidet die Lesbarkeit. Gegenmaßnahme: nur kurze
  Überschriften, nie Fließtext.
- **Kontrast gedimmter Texte:** `#888888` der Vorlage reicht auf `#2A2A2A` nicht;
  deshalb `#9C9C95`. Optisch bleibt der Unterschied gering.
- **Build-Artefakte:** `web/dist` ist eingecheckt; ohne Neubau zeigt der Daemon
  weiter die alte Optik. Der Neubau ist deshalb Pflichtteil der Tasks.
- **Tests:** Vitest-Assertions auf `ma2pi` und Python-Tests auf `--version`
  schlagen fehl, bis sie auf `PRODUCT_NAME` umgestellt sind.
- **Schriftlizenz:** OFL verlangt die Weitergabe des Lizenztexts; ohne
  Lizenzdateien wäre die Einbettung nicht sauber.
