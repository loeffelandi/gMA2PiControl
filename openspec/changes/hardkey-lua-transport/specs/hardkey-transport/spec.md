# Spec Delta

## Purpose

Sendet Hardkey-Press und -Release an die grandMA2 onPC so, dass die Tasten in der
Kommandozeile sichtbar sind. Der Transport ist konfigurierbar; der native
`keyname`-Pfad bleibt als Fallback erhalten.

## ADDED Requirements

### Requirement: Transportauswahl

Der Daemon SHALL den Hardkey-Transport über `ma2.hardkey_transport` wählen. Erlaubt
sind `lua` und `native`. Der Default MUST `lua` sein. Andere Werte MUST beim Laden
der Konfiguration mit einem Fehler abgelehnt werden.

#### Scenario: Default ist lua

- **WHEN** `hardkey_transport` nicht gesetzt ist
- **THEN** wird `lua` verwendet

#### Scenario: Unbekannter Transport

- **WHEN** `hardkey_transport = "osc"` konfiguriert ist
- **THEN** bricht das Laden mit einer Meldung ab, die den Schlüssel und die erlaubten Werte nennt

### Requirement: LUA-Hardkey-Befehl

Bei `hardkey_transport = "lua"` SHALL jeder Press und jeder Release als
`command`-Frame gesendet werden, dessen Befehl genau
`LUA 'gma.canbus.hardkey(<code>, <pressed>, false)'` lautet. `<pressed>` MUST `true`
bei Press und `false` bei Release sein. Der dritte Parameter MUST immer `false` sein.
Halten wird durch den Abstand zwischen Press und Release erreicht.

#### Scenario: Press einer Taste

- **WHEN** die Taste `Store` gedrückt wird und ihr Keycode `59` ist
- **THEN** wird ein `command`-Frame mit `LUA 'gma.canbus.hardkey(59, true, false)'` und der aktuellen Session gesendet

#### Scenario: Release einer Taste

- **WHEN** die Taste `Store` losgelassen wird
- **THEN** wird ein `command`-Frame mit `LUA 'gma.canbus.hardkey(59, false, false)'` gesendet

### Requirement: Keycode-Tabelle

Jeder Hardkey, der über den LUA-Transport gesendet wird, SHALL einen Keycode in der
Konfiguration haben. Ein Hardkey ohne Keycode MUST beim Laden der Konfiguration zu
einem Fehler führen, der den Hardkey-Namen nennt. Ein Keycode MUST eine ganze Zahl
zwischen 1 und 255 sein.

#### Scenario: Fehlender Keycode

- **WHEN** eine Taste `hardkey = "Store"` verwendet wird, aber kein Keycode für `Store` konfiguriert ist
- **THEN** bricht das Laden mit einer Meldung ab, die `Store` nennt

#### Scenario: Ungültiger Keycode

- **WHEN** ein Keycode `0` oder `300` konfiguriert ist
- **THEN** bricht das Laden mit einer Meldung ab, die den Hardkey-Namen nennt

### Requirement: Fix-Taste

Die Taste `Fix` MUST auf einen eigenen Keycode und einen eigenen Keyname abgebildet
werden. Sie MUST NOT auf `FIXTURE` abgebildet werden.

#### Scenario: Fix sendet Fix

- **WHEN** die Taste `Fix` gedrückt wird
- **THEN** wird der Keycode für Fix gesendet, nicht der für Fixture

### Requirement: Nativer Fallback

Bei `hardkey_transport = "native"` SHALL der bisherige `keyname`-Frame mit
`hardkey_press_value` und `hardkey_release_value` gesendet werden. Die Keycode-Tabelle
MUST in diesem Modus nicht geprüft werden.

#### Scenario: Native Press

- **WHEN** `hardkey_transport = "native"` gesetzt ist und `Store` gedrückt wird
- **THEN** wird ein `keyname`-Frame mit `STORE` und Wert `1` gesendet

### Requirement: Keine hängenden Tasten

Ein Release MUST für jeden gesendeten Press gesendet werden, auch bei Gerätverlust,
Shutdown oder Verbindungsabbruch, soweit die Verbindung noch besteht. Nach einem
Verbindungsabbruch MUST kein Release gepuffert und nach dem Wiederverbinden nachgesendet
werden.

#### Scenario: Gerät verloren während Taste gehalten

- **WHEN** eine Taste gehalten wird und das Gerät getrennt wird
- **THEN** wird der Release gesendet, bevor der Zustand verworfen wird

#### Scenario: Verbindung verloren

- **WHEN** die Verbindung zur onPC während eines Press abbricht
- **THEN** wird der Press lokal verworfen und nach dem Wiederverbinden nicht nachgesendet

### Requirement: Verifikation der Keycodes

Der Daemon SHALL pro Hardkey einen Verifikationsstatus unterstützen. Die Konfiguration
MUST für jeden Keycode ein Feld `verified` mit `true` oder `false` akzeptieren.
Keycodes mit `verified = false` MUST nicht über den LUA-Transport gesendet werden;
der Hardkey wird stattdessen als Konfigurationswarnung beim Start gemeldet.

#### Scenario: Unverifizierter Keycode

- **WHEN** `Store` einen Keycode mit `verified = false` hat
- **THEN** wird beim Start eine Warnung mit dem Hardkey-Namen protokolliert und keine Taste gesendet, die auf `Store` abgebildet ist
