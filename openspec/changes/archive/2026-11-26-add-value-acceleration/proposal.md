# Proposal

## Why

Die absoluten Encoder des MIDICRAFT ENC lösen sehr fein auf. Wer damit einen
Executor-Fader über den Web Remote bewegt, braucht für den vollen Weg viele
Umdrehungen. Langsame Drehungen sollen weiterhin 1:1 und feinfühlig bleiben,
schnelle Drehungen aber deutlich mehr Weg pro Raste machen, sodass eine kräftige
Umdrehung den Fader von 0 bis voll bewegt. Die Beschleunigung soll je Encoder
optional sein; physische Fader und relative Encoder bleiben unverändert.

## What Changes

- Neuer Abschnitt `[mapping.value_acceleration]` mit `curve`, `window`,
  `slow_rate`, `fast_rate` und `max_multiplier`.
- Neues optionales Feld `accelerated` an einem Playback-Ziel mit
  `kind = "fader"`. Es ist nur für Controls erlaubt, die im Geräteprofil als
  absoluter Encoder (`kind = "encoder"`) geführt werden; Default ist `false`.
- Der Playback-Router führt je beschleunigtem Control einen virtuellen Wert:
  Die erste Raste setzt ihn auf den Rohwert, danach wird die Rohwertänderung
  mit einem aus der Ereignisrate berechneten Multiplikator verstärkt und auf
  0.0–1.0 geklemmt.
- Der Multiplikator ist bei langsamer Drehung exakt 1.0 und erreicht bei
  schneller Drehung höchstens `max_multiplier`; die Kurve ist linear oder
  exponentiell.
- Der Mapping-Editor zeigt für absolute Encoder mit Fader-Ziel eine Checkbox
  „Beschleunigt“ und speichert sie im Playback-Ziel.
- Physische Fader, relative Encoder und Controls ohne Playback-Ziel werden
  nicht beschleunigt.

## Capabilities

### New Capabilities

- `value-acceleration`: virtueller Wert, Ratenfenster, Multiplikatorkurve,
  Klemmung und Zustands-Lifecycle für absolute Werte.

### Modified Capabilities

- `config-ui`: Checkbox je absolutem Encoder mit Fader-Ziel.
- `executor-playback`: beschleunigte Werte vor dem Senden eines Fader-Frames.

## Impact

- `ma2pi/config.py`: `ValueAccelerationSettings`, Feld `accelerated` an
  `PlaybackMapping`, Parser und Validierung.
- `ma2pi/acceleration.py` (neu): gemeinsame Funktion für die
  Raten-Multiplikatorkurve; `ma2pi/mapping.py` nutzt sie für relative Encoder
  ohne Verhaltensänderung.
- `ma2pi/playback.py`: virtueller Wert je Control, Ratenfenster, Klemmung,
  Zustands-Reset bei Konfigurationswechsel.
- `web/src/lib/MappingPage.svelte` und Tests: Checkbox und Payload.
- `config.toml`, README, Tests.
- Neue ADR (Proposed) für das virtuelle Wertemodell.

## Out of Scope

- LED-Feedback, PickUp und Executor-Polling.
- Änderungen an der Auflösungsumschaltung der relativen Encoder.
- Beschleunigung physischer Fader.
- Einstellungen der globalen Kurve in der Oberfläche; sie bleiben in der
  Konfigurationsdatei.
- Der Geräte-Tab und das Page-Modell aus `add-device-layout-visuals`.
