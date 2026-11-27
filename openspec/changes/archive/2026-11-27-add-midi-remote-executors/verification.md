# Verification

## Messung 2026-11-27 (onPC `192.168.178.72`, grandMA2 onPC 3.9.61.5, Benutzer `svt`)

Testeinträge lagen auf Kanal 16, Note 100 (MIDI-Remote 86) und auf der
Scratch-Page 40; alles wurde danach entfernt. Kontrolle nach den Messungen:
`MidiRemotes (85)`, `SequencePool (264)` wie vorher, Master-Page 3.

### 1.1 M1: RTP-MIDI vom Pi

- rtpMIDI (Tobias Erichsen) auf dem svt-PC, Session `SVT-PC`, Port 5004,
  „Who may connect to me: Anyone“.
- **Portkonflikt gefunden:** Der Screen-Helper (`docs/screen-helper.ahk`)
  lauschte auf UDP 5005, dem Datenport der RTP-MIDI-Session. rtpMIDI antwortete
  deshalb auf keine Einladung, und Probe-Pakete auf 5005 ließen das AHK-Skript
  mit „PCRE execution error -10“ abbrechen. Behoben: Screen-Helper auf UDP 5010
  (Default in `ma2pi/config.py`, `config.toml`, Live-Config, Skript) und das
  Skript ignoriert Binärpakete.
- Wegwerf-Initiator (`IN` auf 5004 und 5005, `CK0/1/2`, RTP-MIDI ohne Journal,
  `BY`) vom Pi aus: beide Einladungen `OK`, Clock-Sync RTT 1,0–1,7 ms, rtpMIDI
  zeigt den Teilnehmer `ma2pi` mit 1 ms Latenz. **Ohne Journal angenommen.**
- MA-MIDI-Eingang musste in der onPC auf die rtpMIDI-Session gestellt werden
  (lokale onPC-Einstellung, nicht Teil der Show). Danach löste `9F 64 7F` eine
  Cmd-Remote (`SetVar $RTPTEST=42`) aus; der MIDI-Monitor der MA zeigt:

  ```
  OnMidiNote c=16 p=1 n=100 v=127
  ReceiveMidiRemote p=1 n=100 o=0
  ReceiveMidiRemote firing remote 100
  MIDI DECODER NEW COMMAND : Note Off
  OnMidiNote c=16 p=0 n=100 v=0
  ReceiveMidiRemote p=0 n=100 o=0
  ReceiveMidiRemote firing remote 100
  ```

- Das direkt am PC angeschlossene MIDI-Gerät (Remotes auf Kanal 1–3) geht
  nicht mehr, sobald der MA-MIDI-Eingang auf rtpMIDI steht (Rückmeldung des
  Nutzers). Es wird nicht gebraucht; rtpMIDI ist der einzige MIDI-Eingang der
  onPC. Wer das Gerät wieder braucht, leitet es per rtpMIDI-Live-Routing in
  die Session.

### 1.2 M2: Telnet

- Port 30000, Anmeldung `login "svt" ""` (`Logged in as User 'svt'`). Falscher
  Benutzer: `Error #72: COMMAND NOT EXECUTED`, die Sitzung bleibt als `guest`
  angemeldet.
- `/36` (absolut) funktioniert nicht; relativ `cd 36` → `RemoteTypes`,
  `cd 2` → `RemoteTypes/MidiRemotes`. `MidiRemotes 2 Enabled=On CLI=On (85)`.
- `list` liefert eine Tabelle mit den Spalten `Name Note Channel Type Page
  Executor Button Keycode CMD Info`; Zeilen `RemoteMidi <nr> MIDI Input <note>
  <channel> <type> <page> <executor> <button> <keycode> [cmd]`. `Page` ist eine
  Zahl oder `Current Page on Master` (Mehrwort!), `Channel` eine Zahl oder
  `All`, `Button` `Button 1..3` oder `Fader`, `Type` `Exec`, `CMD` oder `None`.
- Anlegen: `store <nr>` → Eintrag mit Note 0, Kanal All, Typ None, Page
  „Current Page on Master“, Exec 1, Button 1.
- Ändern: `assign <nr> /note=100 /channel=16 /type="Exec" /page=40
  /executor=101 /button="Button 1"`; `/page=0` → „Current Page on Master“;
  `/cmd="…"` für Typ Cmd.
- Löschen: `delete <nr> /noconfirm`.
- Fehler: `Error #7: NUMBER TOO LONG` (`/executor=99999`), `Error #9: NUMBER TOO
  LARGE (max=16)` (`/channel=17`). **Still ohne Fehler:** `assign` auf einen
  nicht vorhandenen Eintrag, ungültiger Button-Name (`"Button 9"`), `delete`
  eines nicht vorhandenen Eintrags. Der Abgleich muss daher nach dem Schreiben
  zurücklesen.
- Rohmitschnitte: `tests/fixtures/telnet/session.txt` (Liste, Anlegen, Ändern,
  Fehlerfälle, Löschen) und `tests/fixtures/telnet/badlogin.txt`.

### 1.3 M3: Verhalten der MIDI-Remote

| Test | Aufbau | Ergebnis |
|---|---|---|
| Release | Seq 1 auf 40.101, Button 1 = Flash, Remote Page 40 Exec 101 | Note-On gehalten: `isRun 1`; nach Note-Off: `isRun 0` |
| Aktuelle Page | Remote `/page=0`, Master-Page 40 | Note startet 40.101 |
| Store von der Cherry | LUA-Hardkey STORE (59), dann Note auf Remote Page 40 Exec 102 (leer) | 40.102 hat danach eine Sequenz (`tt = Sequ`) – **gespeichert statt ausgelöst** |
| Breiter Executor | 40.101 mit `/width=2` (`combinedItems 2`), Remote auf 40.102 | Druck startet 40.101; der verdeckte Slot hat seine eigene Tastenfunktion (Go), nicht das Flash von 101 – wie eine Konsolentaste in dieser Spalte |

Nebenbefund: `Assign Toggle ExecButton1 40.101` änderte die Tastenfunktion nicht
erkennbar (zweiter Druck schaltete nicht aus); für die Entscheidungen ohne
Belang. Der Store-Test legte Sequenz 264 an, sie wurde wieder gelöscht.

### 1.4 M4: Fader über MIDI-Remote

Remote `/button="Fader"` auf 40.1. Der Wert kommt aus der Note-Velocity:
`0x40` → 0.504, `0x7F` → 1.0, `0x01` → 0.008, `0x00` → 0.0. Control Change
(`BF 64 50`) wird ignoriert. 7 Bit Auflösung bestätigt.

### 3.1 AppleMIDI-Initiator gegen rtpMIDI

`ma2pi/applemidi.py` vom Mac gegen die Session `SVT-PC` (`192.168.178.72:5004`):
Einladung auf beiden Ports angenommen, Clock-Sync 2,8 ms, nach dem ersten
periodischen Sync (10 s) 4,7 ms, Sitzung stand weiter; `close()` meldet mit
`BY` ab. Ohne Note gesendet. Tests: `tests/test_applemidi.py` (angenommen,
abgelehnt, stumm, `BY` der Gegenstelle mit Neuaufbau, ausbleibender Clock-Sync,
Antwort auf fremden `CK0`, Paket-Bytes).

### 4.1/4.2 Telnet-Client und Abgleich gegen die Show

`Ma2Telnet` + `MidiRemoteTable` live: Anmeldung 0,11 s, `list` mit 85
Einträgen 0,08 s; `cd /` führt zurück zur Wurzel (in die Fixture übernommen).
Abgleich auf Kanal 16 mit drei Wegwerf-Zielen (40.101 B1, 40.102 B2, current
103 B3): 3 angelegt (86–88), danach auf ein Ziel reduziert: 2 entfernt, danach
leer: 1 entfernt; Tabelle wieder 85 Einträge. **Die MA nummeriert nach
`delete` nach:** Eintrag 88 hieß nach dem Löschen von 86 und 87 Nummer 86. Der
Abgleich löscht deshalb absteigend und liest am Ende zurück.

### 6.2 Deploy auf den Pi (2026-11-27 01:02)

Live-Config gesichert (`config.toml.bak-before-midi-remote`), `[midi_remote]`
mit `enabled = true`, `channels = [15, 16]`, `sync = "auto"` ergänzt,
`--check-config` grün (245 MIDI-Ziele). Nach dem Neustart: RTP-MIDI-Sitzung
zu `192.168.178.72:5004` steht sofort, Web Remote authentifiziert, erster
Abgleich nach 28 s: `245 angelegt, 0 geändert, 0 entfernt, 0 fehlerhaft`.
Tabelle per Telnet: 330 Einträge, Kanal 15: 128, Kanal 16: 117, die 85
Einträge auf Kanal 1–3 unverändert. Offen: Abnahme an der Hardware durch den
Nutzer (MIDICRAFT ENC war beim Start nicht angesteckt).

### 6.2 Abnahme an der Hardware (2026-11-27 01:03–01:04)

MIDICRAFT ENC um 01:03:49 erkannt. Store, Assign und Edit von der Cherry
(LUA-Hardkeys, u. a. 59) gefolgt von ENC-Tasten, normales Auslösen und Fader
getestet; Fader gingen als `playbackFader` über den Web Remote, keine
„verworfen“-Warnung im Journal, Status-Seite „MIDI-Remote: verbunden · 2.3 ms“,
„Remote-Abgleich: 245/245“. Bestätigung des Nutzers: „das funktioniert sehr
gut“.
