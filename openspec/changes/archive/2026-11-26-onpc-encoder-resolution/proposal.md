# Proposal

## Why

Taste 2 + Encoder-Klick schaltet die Auflösung aktuell nur lokal im Daemon um. Die
onPC-Oberfläche zeigt davon nichts, und der Benutzer sieht keinen Zustand. Gewünscht
ist, wie früher in der onPC (Encoder-Leiste) umzuschalten und den Zustand zu sehen.

Live gegen die onPC geprüft (Fixture 131):
- Der native Frame `{"requestType":"encoder","name":"DIM","resolution":n}` setzt die
  Auflösung, `presetTypes` meldet sie pro Attribut als `encoder_resolution` (0/1/2).
- Die gesetzte Auflösung wirkt auch auf `gma.canbus.encoder` (4 Schritte: Normal +2,0,
  Fine +0,2, Ultra ≈ 0).
- Ein canbus-Encoder-Druck ändert die Auflösung **nicht**.

## What Changes

- Taste 2 gehalten + Klick sendet den nativen Auflösungs-Frame für das Attribut des
  Slots und schaltet Normal → Fine → Ultra → Normal; die lokale Skalierung entfällt.
- Der Daemon liest dafür `presetTypes` nur bei Bedarf (beim Verbinden und kurz nach
  einem Auflösungswechsel), kein Dauer-Polling. Das Seitenmodell (`EncoderPage`) kommt
  für Namen und Auflösung zurück.
- Für Screen-Encoder (Screen-Modus oder MA gehalten) gibt es keinen Namen: dort wird
  nicht umgeschaltet, es erscheint eine Warnung im Log.

## Capabilities

### New Capabilities

(keine)

### Modified Capabilities

- `encoder-control`: Auflösung wird in der onPC umgeschaltet statt lokal; Seitenmodell
  nur bei Bedarf gelesen. Die LED von Taste 2 bleibt unverändert (Ruhe/Gedrückt).

## Impact

- `ma2pi/encoder_page.py` (wiederhergestellt), `ma2pi/ma2_client.py`, `ma2pi/mapping.py`,
  `ma2pi/actions.py`, `ma2pi/led_output.py`, `ma2pi/config.py`, `config.toml`, README, Tests.
