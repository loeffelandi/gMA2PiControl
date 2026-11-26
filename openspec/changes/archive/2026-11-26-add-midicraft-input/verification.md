# Verification

Stand: 2026-11-26

## Automatisierte Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `pytest` | 390 Tests bestanden |
| `npm run check` (Svelte/TypeScript) | 0 Fehler, 0 Warnungen |
| `npm run test` (Vitest) | 35 Tests bestanden |
| `npm run check:offline` | keine externen Netzwerkressourcen |
| `npm run build` | erfolgreich |

Abgedeckt: Profil- und Mapping-Validierung, absolute MIDI-Werte, zwei parallele
MIDI-Geräte, Frame-Builder inklusive `page = "current"` → `pageIndex = -1`,
Sende-Queue mit Fader-Coalescing, Vorrang des Playback-Routers, Geräte-API und
Mapping-Editor inklusive Feldvalidierung.

## Netzwerk zum Testzeitpunkt

- Pi: `eth0` `192.168.178.21/24`, `wlan0` `192.168.178.12/24`
- Live-Konfiguration `/var/lib/ma2pi/config.toml`: `ma2.host = 192.168.178.72`
- Prüfung vom Pi: `ping` erfolgreich, `http://192.168.178.72/?ma=1` liefert
  HTTP 200.
- Abweichung: Die Beispielkonfiguration im Repo nennt weiterhin
  `192.168.0.10`; die Live-Konfiguration wurde bereits auf die erreichbare
  Adresse umgestellt. Kein Codeänderungsbedarf in diesem Change.

## Page-Messung MIDICRAFT (2026-11-26, Übergabe an `add-device-layout-visuals`)

- Der Page-Wechsel am Gerät sendet **kein** eigenes MIDI-Ereignis; die Page ist
  nur an den eingehenden Nachrichten erkennbar.
- Page 2 sendet auf **MIDI-Kanal 2** (`91`/`81`).
- Page 2, Encoder-Klick 1: **Note 0** (`91 00 7F` / `81 00 00`).
- Page 2, Fader 1: **Note 15** (`91 0F`), absolut 1–127.
- Konsequenz für das Page-Modell: Die Auflösung muss über **(Kanal, Note)**
  erfolgen, nicht über die Note allein. Die Eindeutigkeitsprüfung gehört auf das
  Paar, nicht nur auf die Note.
- Default-Bank laut Benutzer: Page N → Executor `(N-1)*5+1 … N*5` auf der
  aktuell aktiven MA-Page; Basis und Button-Rollen frei konfigurierbar.
- Vorgeschlagene Button-Defaults: Encoder-Klick → Button 1, obere Reihe →
  Button 2, mittlere Reihe → Button 3, untere Reihe → kein Executor-Ziel.
- Diese Page-/Geräte-Tab-Funktion gehört zu `add-device-layout-visuals` und
  wurde hier nicht implementiert.

## Hardware-Abnahme (bestanden)

### Befund 2026-11-26: Nullwert wurde verworfen

Beim Zurückfaden blieben Executoren auf dem letzten Wert vor 0 stehen
(Encoder bei 1, Fader je nach Geschwindigkeit bei 1–8). Ursache: Der Parser
machte aus Note-On mit Velocity 0 eine Note-Off-Nachricht; `_normalise`
verwirft Note-Off für absolute Werte. Dadurch fehlte der Wert 0.0. Der Parser
behält jetzt den Nachrichtentyp aus dem Statusbyte, sodass Note-On mit
Velocity 0 als Wert 0.0 ankommt. Abgedeckt durch
`test_zero_value_survives_parser_and_normalise`.

### Ergebnis 2026-11-26

Vom Benutzer am Pi bestätigt: Page 1 funktioniert mit den Buttons 1–3, den
Fadern und dem absoluten Encoder; `page = "current"` folgt der aktiven
Master-Page. Der Nullwert-Fehler wurde behoben und ist durch
`test_zero_value_survives_parser_and_normalise` abgedeckt. Die neue Version ist
nach `/opt/ma2pi/app` installiert, der Dienst läuft.

### Vorbereiteter Deploy auf dem Pi

- Quellcode + gebautes Frontend: `/tmp/gMA2PiControl/`
- Konfigurations-Merge: `/tmp/merge-midicraft-config.py` (legt
  `devices.midicraft` und `profiles.midicraft-enc` an, ergänzt das
  Beispiel-Mapping mit `page = "current"`, setzt `led.device = "asl"`,
  validiert vor dem Schreiben und legt ein Backup an)
- Wrapper: `/tmp/deploy-midicraft.sh` (Installation, Merge, `--check-config`,
  Dienstneustart, Logausgabe)

Aufruf:

```bash
ssh -t -i /Users/Andreas/.ssh/ma2pi_pi_ed25519 svt@192.168.178.21 \
  'sudo /tmp/deploy-midicraft.sh'
```

Der Merge wurde vorab ohne Schreiben gegen die Live-Konfiguration validiert:
Profile `asl-mk2-e4b3`, `cherry-g86`, `midicraft-enc`; MIDI-Geräte `asl` und
`midicraft`; Playback-Ziele `mc_click_1..3`, `mc_fader_1` und `mc_encoder_1`
mit `page = "current"`.

Abnahmeschritte:

1. Build nach `/opt/ma2pi/app` installieren und Dienst neu starten.
2. Im Web-UI unter **Geräte/Mapping → Playback-Ziele** prüfen, ob die fünf
   Beispielziele mit `current` vorhanden sind; bei Bedarf anpassen.
3. Im Frame-Log `playbacks_userInput` mit korrektem `execIndex`,
   `pageIndex = -1`, `buttonId`, `pressed`/`released` und `faderValue` prüfen.
4. Auf der MA beobachten, ob die drei Button-Nummern und der Fader auf der
   aktiven Page auslösen; danach die Master-Page wechseln und erneut prüfen,
   ob `pageIndex = -1` der neuen Page folgt.
5. Ergebnis hier nachtragen.

Bekannte Einschränkung ohne PickUp: Nach einem Seitenwechsel springt ein
Executor beim nächsten Faderwert auf die physische Position.
