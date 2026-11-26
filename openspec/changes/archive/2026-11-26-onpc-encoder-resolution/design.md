# Design

## Kontext
Verifiziert gegen die onPC: nativer `resolution`-Frame setzt, `presetTypes.encoder_resolution`
meldet (0/1/2), die Auflösung wirkt auf canbus-Schritte, ein canbus-Druck ändert sie nicht.

## Entscheidungen
- **Seitenmodell zurück, ohne Polling:** `EncoderPage` aus Git wiederherstellen. Der
  Client fragt `presetTypes` beim Verbinden und 0,3 s nach einem Auflösungsframe
  einmal ab. Kein Dauer-Timer.
- **Aktion:** `EncoderResolution(slot)` ersetzt die lokale Skalierung. Der Client
  ermittelt Namen und aktuelle Stufe aus der Seite, sendet
  `encoder_resolution_frame(name, (stufe+1)%3)` und liest danach die Seite neu.
- **Entfällt:** `_slot_resolution` und die Skalierung in `MappingEngine`; der
  `cycle`-Modifier bleibt, schaltet aber `EncoderResolution` statt lokaler Zustände.
- **Screen/MA:** keine Namen verfügbar → Warnung, kein Frame.

## Risiken
- Seite ohne Auswahl (keine Fixture): kein Name → Warnung, kein Frame.
