# Tasks

## 1. Frame und Transport

- [x] 1.1 `frames.lua_hardkey_frame(code, pressed, session)` baut `command_frame("LUA 'gma.canbus.hardkey(<code>, <true|false>, false)'", session)`. Verifikation: Unit-Test vergleicht das Dict exakt mit dem Referenzformat.
- [x] 1.2 `ma2_client._dispatch` wählt bei Press/Release den Transport aus `ma2.hardkey_transport`. Verifikation: Tests für `lua` und `native` mit Fake-Transport prüfen die gesendeten Frames.
- [x] 1.3 Keyname-zu-Keycode-Auflösung im LUA-Pfad. Ein unbekannter Keyname im LUA-Pfad wird verworfen und protokolliert. Verifikation: Test mit unbekanntem Keyname sendet keinen Frame.

## 2. Konfiguration

- [x] 2.1 `config.py`: `ma2.hardkey_transport` mit Werten `lua` und `native`, Default `lua`. Verifikation: Tests für Default, gültigen und ungültigen Wert.
- [x] 2.2 `config.py`: Tabelle `[hardkeys.<KEYNAME>]` mit `code` (1–255) und `verified` (bool) parsen und validieren. Verifikation: Tests für ungültigen Code (0, 300) und fehlendes Feld.
- [x] 2.3 `config.py`: Pflichtprüfung beim Laden. Jeder im Mapping verwendete Hardkey braucht einen Eintrag, wenn der Transport `lua` ist. Verifikation: Test mit fehlendem Keycode nennt den Hardkey in der Fehlermeldung.
- [x] 2.4 `config.py`: Hardkey mit `verified = false` erzeugt eine Startwarnung und wird nicht gesendet. Verifikation: Test prüft Warnung und fehlenden Frame.

## 3. Fix-Korrektur

- [x] 3.1 `hardkeys.py`: `ALIASES["Fix"]` nicht mehr `FIXTURE`. Eigenen Keyname `FIX` ergänzen, falls nicht vorhanden. Verifikation: Test `resolve("Fix") != resolve("Fixture")`.

## 4. Release-Sicherheit

- [x] 4.1 Bestehende Tests für `release_device`, `cleanup` und `on_connection_lost` auf den LUA-Pfad erweitern. Verifikation: Test mit gehaltener Taste sendet genau einen Release bei Gerätverlust.
- [x] 4.2 Test: nach Verbindungsabbruch wird kein Release nachgesendet. Verifikation: Frame-Liste nach Wiederverbinden enthält keinen Press/Release aus der alten Session.

## 5. Konfigurationsdatei

- [x] 5.1 `config.toml` im Repo: `hardkey_transport = "lua"` und `[hardkeys.*]`-Tabelle mit allen verwendeten Hardkeys. Keycodes aus MIDIMonster, `verified = false`. Verifikation: `python -m ma2pi --check-config` meldet gültige Konfiguration.
- [x] 5.2 `ma2pi --check-config` mit der Repo-Datei ohne Fehler. Verifikation: Exit-Code 0.

## 6. Tests und Lauf

- [x] 6.1 `pytest` im Repo ist grün. Verifikation: alle Tests bestehen, Anzahl gegenüber den bisherigen 175 erhöht.
- [x] 6.2 Deploy auf dem Pi: Code und `/home/svt/test-live.toml` aktualisieren, Backup der alten Config anlegen, `--check-config`. Verifikation: Daemon startet, Session authentifiziert.
- [x] 6.3 Erster Test mit `Clear` (Keycode 105). Verifikation: Die Kommandozeile der onPC zeigt die Taste, der Benutzer bestätigt. Bei Ablehnung: `native` setzen und Ursache im Log prüfen.
- [x] 6.4 Verifikation je Taste über die Kommandozeile. Jede bestätigte Taste bekommt `verified = true` in der Config auf dem Pi und im Repo. Verifikation: Liste im Change-Ordner mit Taste, Keycode und Status. (Ziffern, Navigation, Funktionstasten, Channel, Clear bestätigt; übrige Tasten vom Benutzer freigegeben. Siehe `verification.md`.)
- [x] 6.5 Halten testen mit `Store` (Store Options erscheinen nur bei gehaltener Taste). Verifikation: Benutzer bestätigt Verhalten. (Halteschwelle 0,5 s; `hold=true` nach Schwellenwert.)
- [x] 6.6 Modifier-Test: MA + Fix (Desk Lock). Verifikation: Benutzer bestätigt, dass Desk Lock umschaltet. (MA als initialer Press + Hold; Logo-Taste = `KEY_SLASH`.)

## 7. ADR

- [x] 7.1 ADR 0016 auf Accepted setzen, wenn 6.3, 6.5 und 6.6 bestanden sind. Verifikation: ADR-Status und Abschnitt „Bestätigung“ sind abgehakt.

## Workflow follow-up

- Nach Abschluss der Verifikation: Change archivieren (`openspec-archive-change`), Spec in `openspec/specs/hardkey-transport/` übernehmen.
