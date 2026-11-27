# Tasks

## 1. Gemeinsame Aktivitätsanzeige

- [ ] 1.1 `web/src/lib/ActivityLeds.svelte` mit Props für Gerätename und Zähler anlegen: RX-/TX-LEDs, 400-ms-Puls bei Zähleranstieg, Timer-Aufräumen beim Unmount. Verifikation: `npm test` und `npm run check` grün.
- [ ] 1.2 `StatusPage.svelte` auf `ActivityLeds` umstellen, ohne Zählertext und Layout zu verändern. Verifikation: bestehender StatusPage-Test zur Pulse-Assertion bleibt grün.

## 2. Geräte-Seite

- [ ] 2.1 `DevicesPage.svelte` um einen optionalen `statusStore`-Prop erweitern und die Aktivitätszähler aus dem Store lesen; `App.svelte` übergibt den Store. Verifikation: bestehende `DevicesPage`-Tests ohne Store bleiben grün; `npm run check` ohne Fehler.
- [ ] 2.2 In jedem Eintrag der Geräteliste die RX-/TX-LEDs einbauen, mit den bestehenden CSS-Klassen und ohne Zählertext. Verifikation: DOM-Test findet je Gerät `.activity-led.rx` und `.activity-led.tx`.

## 3. Tests und Abschluss

- [ ] 3.1 Test ergänzen: ein `activity`-Event mit steigendem RX-/TX-Zähler lässt die passende LED pulsieren; ohne Store bleiben die LEDs ohne Puls. Verifikation: `npm test` grün.
- [ ] 3.2 `npm run check`, `npm run build` und `openspec validate add-device-activity-leds --strict` ausführen. Verifikation: alle drei Befehle ohne Fehler.
