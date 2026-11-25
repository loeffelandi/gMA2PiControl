# Design

## Context

Siehe proposal.md, Abschnitt „Why“. Der Daemon sendet heute über
`frames.keyname_frame` (`requestType: keyname`). Die Mapping-Engine liefert Press
und Release als Keyname-String (`hardkeys.resolve`). `ma2_client._dispatch` baut den
Frame. Der Command-Frame existiert bereits (`frames.command_frame`), wird für
Befehlstasten genutzt und braucht keinen neuen Frame-Typ.

ADR 0016 nennt die Quelle: MIDIMonster `backends/maweb.c`, Modus `console`.

## Goals / Non-Goals

**Goals:**
- Hardkeys erscheinen in der onPC-Kommandozeile.
- Press und Release sind getrennt; Halten funktioniert.
- Keycodes sind pro Taste konfigurierbar und einzeln verifizierbar.
- Der native Pfad bleibt als Fallback.

**Non-Goals:**
- Keine Modifier-Sequenzen als eigene Logik. Modifier (MA) laufen über die bestehende
  Mapping-Engine (Press MA, Press Taste, Release Taste, Release MA).
- Keine Verifikation automatisch durch den Daemon. Verifikation erfolgt manuell in der
  onPC und wird im Config-Feld `verified` festgehalten.
- Keine Änderung an Encodern, Wheel oder MIDI.

## Decisions

**D1: Keycodes in der Konfiguration, nicht im Code.**
Begründung: Verifikation und Korrektur ohne Release. Alternative: Tabelle im Code
(wie MIDIMonster). Verworfen, weil unverifizierte Codes sonst mit dem Code
ausgeliefert würden.

**D2: Keyname bleibt die interne Kennung.**
Die Mapping-Engine bleibt unverändert und liefert weiter `STORE`, `FIXTURE` usw.
`ma2_client` übersetzt den Keyname im LUA-Pfad in den Keycode. Alternative: Mapping
liefert direkt Keycodes. Verworfen, weil dann der native Pfad und die Tests ändern.

**D3: Ein Befehl pro Flanke.**
Press sendet `LUA ... (code, true, false)`, Release sendet `(code, false, false)`.
Der dritte Parameter bleibt `false` (wie MIDIMonster). Alternative: `hold=true`
für Haltetasten, wie in der KI-Empfehlung genannt. Verworfen, weil die Referenz das
nicht verwendet und die Wirkung nicht verifiziert ist.

**D4: Config-Schema.**
Neue Felder:
- `ma2.hardkey_transport = "lua" | "native"` (Default `lua`)
- `[hardkeys.<KEYNAME>] code = <int>`, `verified = <bool>` (neue Tabelle)

Die Tabelle wird beim Laden gegen die verwendeten Hardkeys geprüft (siehe Spec).

**D5: Fix-Korrektur.**
`hardkeys.ALIASES["Fix"]` wird nicht mehr auf `FIXTURE` gesetzt. Stattdessen ist
`FIX` ein eigener Keyname mit eigenem Keycode.

**D6: Release bei Verlust.**
Die bestehenden Pfade `release_device`, `cleanup`, `on_connection_lost` bleiben
gültig. Der LUA-Pfad nutzt dieselben Aktionen (`Press`/`Release`). Ein Release vor
Trennung wird nur gesendet, wenn die Verbindung noch besteht.

## Risks / Trade-offs

- **[Admin-Rechte fehlen oder werden anders gehandhabt]** → Erster Test mit `Clear`
  (105). Wenn der Befehl abgelehnt wird, Fallback auf `native` in der Config.
- **[Falscher Keycode löst eine andere Funktion aus]** → Keine produktive Nutzung
  eines Codes mit `verified = false`. Verifikation je Taste mit Sichtprüfung in der
  Kommandozeile.
- **[Community-Keycodes stimmen nicht für alle Versionen]** → Die Tabelle stammt aus
  MIDIMonster, nicht aus einer offiziellen MA-Dokumentation. Die Verifikation
  bestätigt jede Taste einzeln.
- **[Pfad ist nicht sichtbar in der Kommandozeile]** → Falls die onPC den Befehl
  annimmt, aber keine Kommandozeilen-Anzeige erscheint, bleibt der native Pfad.
- **[Fix-Bug war bisher unbemerkt]** → Mit der Korrektur ändert sich das Verhalten
  der Fix-Taste. Vor dem Deploy in der Verifikation prüfen.

## Migration Plan

1. Code und Tests lokal (`pytest`).
2. `config.toml` im Repo erhält die Keycode-Tabelle mit `verified = false`, bis
   geprüft.
3. Auf dem Pi: `/home/svt/test-live.toml` anpassen, Daemon neu starten,
   Config-Check mit `--check-config`.
4. Verifikation je Taste über die Kommandozeile der onPC. Danach `verified = true`.
5. Rollback: `hardkey_transport = "native"` in der Config setzen und den Daemon neu
   starten. Die Dateien `*.bak-*` auf dem Pi enthalten die alte Config.

## Open Questions

- Keycode für `Fix`: MIDIMonster nennt FIX=41, aber das ist nicht offiziell
  verifiziert. Die Verifikation auf der onPC entscheidet.
- Admin-Rechte: Der Benutzer `svt` hat laut Angabe Adminrechte. Wirkung auf den
  LUA-Aufruf wird beim ersten Test geprüft, nicht vorab.
