# Design

## Context

Die Statusseite hält für jedes Gerät RX-/TX-Zähler aus dem Status-Store und
lässt bei jedem Anstieg die zugehörige LED 400 ms pulsieren; die Logik liegt
inline in `StatusPage.svelte`. Die Geräte-Seite erhält derzeit nur den
API-Client, lädt ihre Geräteliste einmalig und kennt keine Aktivität. Sie zeigt
je Gerät einen Eintrag („Kasten“) in der Seitenleiste und rechts die
Gerätefläche.

## Goals / Non-Goals

**Goals:**

- RX-/TX-Pulsanzeige je Gerät auf der Geräte-Seite, ohne neuen Backend-Pfad.
- Eine gemeinsame Implementierung für Status- und Geräte-Seite.
- Bestehende Tests und das optionale Store-Muster der Mapping-Seite beibehalten.

**Non-Goals:**

- Zählertexte oder Aktivitätshistorie auf der Geräte-Seite.
- Hardware-LEDs oder Änderungen am Feedback-Pfad.
- Anzeige nicht angeschlossener Geräte (bleibt Sicht der Geräteflächen-Spec).

## Decisions

### D1: Gemeinsame Komponente `ActivityLeds`

Die Puls-Logik (Vergleich der letzten Zähler, 400-ms-Puls, Timer-Aufräumen) wird
in `ActivityLeds.svelte` gezogen. Die Komponente erhält den Gerätenamen und die
aktuellen Zähler und rendert die zwei LEDs. Status- und Geräte-Seite verwenden
sie identisch.

*Alternative:* Logik in beiden Seiten duplizieren. Verworfen, weil Pulsdauer
und Timer-Aufräumen sonst auseinanderlaufen.

### D2: Optionaler `statusStore`-Prop für die Geräte-Seite

`DevicesPage` bekommt `statusStore?: StatusStore` (wie `MappingPage` mit
`learnStore`). `App.svelte` übergibt den bestehenden Store. Ohne Store bleiben
die LEDs dunkel; dadurch bleiben die vorhandenen Tests ohne Store-Mock gültig.

*Alternative:* Pflicht-Prop. Verworfen, weil dann alle bestehenden Render-Tests
angepasst werden müssten, ohne dass sie Aktivität prüfen.

### D3: Nur LEDs, keine Zähler

Die Geräte-Seite zeigt ausschließlich die beiden LEDs. Zählertexte bleiben der
Statusseite vorbehalten.

*Alternative:* Zähler wie auf der Statusseite anzeigen. Für später offen, aber
nicht Teil dieses Changes.

### D4: Platzierung in den Geräteeinträgen der Seitenleiste

Die LEDs sitzen in jedem Eintrag der Geräteliste, weil dort das Gerät als Ganzes
repräsentiert wird. Die Gerätefläche zeigt Belegungen je Control und bleibt
unverändert.

*Alternative:* LEDs in der Gerätefläche. Verworfen, weil die Fläche Control-
Zustände und keine Geräteaktivität darstellt.

## Risks / Trade-offs

- [WebSocket getrennt] → LEDs bleiben dunkel, Seite bleibt bedienbar; der
  bestehende Reconnect des Status-Stores stellt die Anzeige wieder her.
- [Timer nach Seitenwechsel] → `ActivityLeds` räumt seine Timer beim Unmount auf.
- [Store in Tests fehlt] → optionaler Prop, LEDs bleiben dunkel; neue Tests
  decken den Store-Fall ab.

## Migration Plan

Reine Frontend-Änderung, ausgeliefert mit dem regulären Build und
`deploy/install.sh`. Rollback durch Zurücknehmen des Commits; keine
Konfigurations- oder Datenmigration nötig.
