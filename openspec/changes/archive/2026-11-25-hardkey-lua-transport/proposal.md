# Proposal

## Why

Hardkeys, die als Web-Remote-`keyname`-Frame gesendet werden, erscheinen nicht in
der Kommandozeile der onPC. Der Bediener sieht nicht, was er tippt. Mit
`gma.canbus.hardkey` über einen Command-Frame kommen die Tasten als echte
Hardware-Ereignisse an und werden sichtbar in der Kommandozeile verarbeitet.
Entschieden in ADR 0016 (Status Proposed, ersetzt ADR 0001).

## What Changes

- Neuer Transport `hardkey_transport = "lua"` für Hardkeys: Press und Release werden
  als `command`-Frame mit `LUA 'gma.canbus.hardkey(<code>, <true|false>, false)'`
  gesendet.
- Der bisherige `keyname`-Pfad bleibt als `hardkey_transport = "native"` erhalten.
- Jede Hardkey-Belegung braucht einen verifizierten Keycode in der Konfiguration.
  Fehlt ein Code, bricht das Laden der Konfiguration ab.
- Korrektur: `Fix` wird nicht mehr auf `FIXTURE` abgebildet, sondern auf den eigenen
  Keycode für Fix.
- **BREAKING**: Der Default für `hardkey_transport` wechselt von `native` auf `lua`.
  Konfigurationen ohne Keycode-Tabelle starten nicht mehr.

## Capabilities

### New Capabilities

- `hardkey-transport`: Senden von Hardkey-Press und -Release an die onPC, wahlweise
  über den Command-Line-Pfad (`gma.canbus.hardkey`) oder den nativen
  Web-Remote-`keyname`-Pfad, inklusive Keycode-Verwaltung und Verifikationsstatus.

### Modified Capabilities

Keine. Die Hauptspezifikation unter `openspec/specs/` ist leer.

## Impact

- `ma2pi/frames.py`: neuer Frame-Builder für den LUA-Hardkey-Befehl.
- `ma2pi/ma2_client.py`: Dispatch für Press/Release wählt den Transport.
- `ma2pi/hardkeys.py`: Korrektur `Fix` → eigener Keyname/Code, Erweiterung um die
  Keycode-Tabelle.
- `ma2pi/config.py`: neues Feld `hardkey_transport` mit Validierung, Keycode-Tabelle
  pro Hardkey, Pflichtprüfung beim Laden.
- `config.toml` und `/home/svt/test-live.toml` auf dem Pi: Keycode-Tabelle und
  Transport.
- Abhängigkeit: Der Web-Remote-Benutzer der onPC braucht Admin-Rechte (nach Angabe
  des Benutzers vorhanden, Benutzer `svt`).
- Tests: `tests/` für Frame-Format, Transportauswahl, Konfigurationsprüfung und
  Press/Release-Reihenfolge.
