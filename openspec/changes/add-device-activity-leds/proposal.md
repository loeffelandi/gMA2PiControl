# Proposal

## Why

Die Statusseite zeigt bereits RX-/TX-Aktivitäts-LEDs. Auf der Geräte-Seite, auf
der Geräte bedient und belegt werden, fehlt diese Rückmeldung. Wer prüfen will,
ob ein Gerät gerade sendet oder empfängt, muss die Seite wechseln.

## What Changes

- Die Geräte-Seite zeigt je angezeigtem Gerät zwei pulsierende LEDs: RX (grün)
  für empfangene Eingaben, TX (gelb) für gesendete Ausgaben.
- Die LEDs werden aus dem bestehenden Status-/Aktivitäts-WebSocket gespeist.
  Es entstehen keine neuen Endpunkte und kein Polling.
- Die Puls-Logik wird in eine gemeinsame UI-Komponente gezogen, damit Status-
  und Geräte-Seite dieselbe Anzeige verwenden.
- Die Geräte-Seite erhält den Status-Store über `App.svelte`.
- Auf der Geräte-Seite erscheinen nur die LEDs, keine Zählertexte; die
  Statusseite bleibt funktional unverändert.
- **Nicht Teil**: Hardware-LEDs, neue Backend-Events, persistente
  Aktivitätshistorie.

## Capabilities

### New Capabilities

- Keine.

### Modified Capabilities

- `config-ui`: Die Geräte-Seite zeigt RX-/TX-Aktivitäts-LEDs je Gerät, live
  über den bestehenden Status-Stream.

## Impact

- `web/src/lib/DevicesPage.svelte`, `web/src/App.svelte`, neue Komponente
  `web/src/lib/ActivityLeds.svelte`, `web/src/lib/StatusPage.svelte` (Nutzung
  der Komponente), `web/src/app.css`, `web/src/lib/DevicesPage.test.ts`.
- Backend unverändert; nutzt die bestehende Aktivitätserfassung und den
  Status-Snapshot.
