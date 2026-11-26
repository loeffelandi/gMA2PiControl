# Design

## Context

`ExecutorFeedback._apply` schreibt pro geänderter LED sofort einen Frame
(`90 <Note> <Velocity>`) über `MidiManager.send` → `RealMidiHandle.write`
(`os.write` auf `O_RDWR|O_NONBLOCK`). Beim Start und nach jedem Wechsel der
geöffneten Geräte (`_sync_devices` leert `_last`) gehen bis zu 15 Frames
unmittelbar hintereinander hinaus. Zwischen den Frames gibt es keinen Abstand,
und es gibt keine Rückmeldung, ob das Gerät sie abnimmt.

### Beobachtung auf dem Pi (nur lesend, 2026-11-26)

| Zeitraum | Feedback | ENC-Events |
|---|---|---|
| 19:20:29–19:22:38 | an | 0 |
| 19:23:36–19:26:35 | an | 0 |
| 19:29:10–19:31:30 | aus | 508 Encoder, 174 Button-Frames |

- Kernel: `sound midiC4D0: rawmidi drain error (avail = 4075, buffer_size =
  4096)` am 19:22:48, `avail = 3619` am 16:00:34. Der Puffer war also nicht
  voll; das Gerät hat angenommene Bytes nicht abgeholt.
- Die ASL (`card3`) bekommt dieselbe Art Ausgabe ohne Probleme
  (`Tx bytes: 1158`).
- Es gibt keine Button-Frames in den Feedback-Läufen. Eine Rückkopplung durch
  Echo der LED-Noten ist damit nicht belegt; das Gerät wird still.
- Stopp des Dienstes dauerte 28–56 s (z. B. 19:22:38 → 19:23:34), passend zu
  einem Drain-Timeout je Gerät beim Schließen.
- Nicht belegt: ob Burst, Dauerrate, Notenliste oder Kanal die Ursache ist.
  Die Notenliste (`led_notes`) stammt aus dem Handbuch und ist am ENC nicht
  gemessen (Task 1.2 in `add-midicraft-led-feedback`).

### Neue Information: andere Software sendet problemlos

Laut Betreiber (2026-11-26) senden ShowCockpit und die Lua-Plugins der MA2
ohne Probleme an den ENC. Das schwächt die Annahme „das Gerät kann keine
Ausgabe“ und verschiebt die Frage auf den Unterschied zwischen `ma2pi` und
diesen Sendern. Der USB-Descriptor des ENC (`lsusb -v`, nur lesend) ist
unauffällig: USB 1.10 Full-Speed, ein Audio-Control- und ein
MIDI-Streaming-Interface mit je einem Bulk-Endpoint (EP 1 OUT, EP 2 IN,
64 Bytes, `bInterval` 5), 500 mA, ein Embedded-Jack je Richtung.

| Hypothese | Begründung | Prüfung |
|---|---|---|
| H1: Inhalt der Frames weicht ab (Note, Kanal, Velocity, Note-Off statt Velocity 0) | `midicraft-v2` stammt aus dem Handbuch, nie am ENC gemessen | Referenzverkehr aufzeichnen und mit `90 <Note> <Vel>` auf Kanal 1 vergleichen |
| H2: Form der Übertragung weicht ab: Linux füllt einen Bulk-Transfer mit allen anstehenden Paketen (bis 64 Bytes), der Start-Burst aus 15 Frames geht als ein Transfer hinaus; macOS und Windows senden meist einzelne Pakete | Verhalten von `snd-usb-audio` nach Kenntnis des Treibers, hier nicht gemessen; passt zu `bMaxPacketSize` 64 und einer kleinen Firmware-Pufferung | Einzelframes mit Pause gegen Burst messen, Kernel-Log mitlesen |
| H3: Linux-/Hub-Pfad (Full-Speed hinter dem internen Hub, Stall-Wellen schon ohne Ausgabe am 18:36 und 19:15) | Disconnects traten auch in Läufen ohne Feedback auf | ENC an anderem Port oder direkt am Hub, Messung mit und ohne Ausgabe |
| H4: Beide Wege gemeinsam: ein O_RDWR-Handle, das zugleich liest und schreibt, belastet die Firmware | Andere Software öffnet In und Out meist getrennt | Messung nur Lesen, nur Schreiben, beides |

### Referenz: offizielles Midicraft-LED-Plugin (v1.3, „extended“)

Der Betreiber hat das funktionierende MA2-Lua-Plugin geliefert
(`test.lua`, registriert über `test.xml` als „Midicraft LED-Feedback
extended“). Es sendet pro LED die MA2-Kommandozeile
`MidiNote <Kanal>.<Note> <Velocity>`; Kanal und Note kommen aus den
`MidiRemotes` der Show (Typ `Exec`, Button 1–3), also aus derselben Zeile,
über die die Eingabe läuft. Auf dem Draht ist das ein Note-On
`9n <Note> <Velocity>`. Daraus folgt:

| Punkt | Plugin | `ma2pi` heute |
|---|---|---|
| Frame-Form | Note-On, Kanal je MidiRemote-Zeile | Note-On, fest Kanal 1 |
| Abstand beim Start | `gma.sleep(0.01)` nach jedem Frame, Schleifentakt 0,05 s | kein Abstand |
| Wann senden | nur bei Änderung der Executor-Klasse (Cache) | nur bei Änderung (`_last`) |
| Velocity aus | `0` | `0` |
| Velocity dunkel | `1 + Farbe` | `1 + Farbe` |
| Velocity hell | **`17 + Farbe`** | **`15 + Farbe`** |
| Komplementär / blinkend hell | `33 + Farbe` | nicht verwendet |
| Blinkend dunkel | `49 + Farbe` | nicht verwendet (Handbuch: 43–55) |
| Feedback-Modus des Geräts | `65 + Farbe` | nicht verwendet |
| Farben | 15 (weiß bis pink, dazu CTO, CTB) | 13 (ohne CTO, CTB) |
| Vom Gerät definierte Farbe | `123`–`127` | nicht verwendet |

Das Plugin kennt damit ein Layout mit Abstand 16 je Modus (1, 17, 33, 49, 65);
die Kommentare im Plugin nennen „Firmware-Version 2.x“ für die komplementären
Farben. Das `midicraft-v2`-Protokoll von `ma2pi` folgt dem Layout aus dem
Handbuch (Abstand 14: 1–13 dunkel, 15–27 hell, 43–55 blinkend dunkel). Ob der
ENC Firmware 1.x oder 2.x hat, ist nicht bekannt (`bcdDevice 0.01` sagt es
nicht). Läuft der ENC mit dem 2.x-Layout, sind unsere Helligkeitswerte um 2
verschoben: Velocity 15 ist dort „dunkel, Farbe 14 (CTB)“, 16 ist nicht
belegt, 17 ist „hell, weiß“. Das erklärt falsche Farben, aber nicht für sich
allein einen Eingabestillstand.

Folgerungen:

- **H1 teilweise bestätigt:** Frame-Form stimmt, die Velocity-Tabelle nicht
  (bei hell und bei den nicht genutzten Modi). Sie hängt von der
  Firmware-Version ab. Eine Korrektur gehört in einen Folge-Change an
  `add-midicraft-led-feedback`, nicht hierher.
- **H2 gestützt:** Das Plugin hält mindestens 10 ms zwischen den Frames
  ein und sendet über die MA-Kommandozeile, die jedes Kommando einzeln
  verarbeitet. `ma2pi` schreibt dagegen den Startzustand ohne Abstand. Die
  Messung soll zeigen, ob 10 ms reichen; der Default von 20 ms bleibt, bis das
  gemessen ist.
- **Kanal:** Das Plugin sendet auf dem Kanal der MidiRemote-Zeile. `ma2pi`
  sendet fest auf Kanal 1; bei Bank 1 deckt sich das, bei höheren Banken
  nicht. Das bleibt ausdrücklich außerhalb dieses Changes.

H1 und H2 sind die wahrscheinlichsten und billigsten zu prüfen; sie
bestimmen, ob die Ausgabe-Queue (D2) reicht oder `midicraft-v2` selbst
angepasst werden muss. H3 und H4 bleiben offen, falls H1 und H2 nichts
ergeben. Das bestehende Verhalten „bis zu 15 Frames sofort“ passt zu H2.

### Einschränkungen

- Nur Lesezugriff auf den Pi bis zur Freigabe; die Messung (Gruppe 1 in
  `tasks.md`) braucht den ENC exklusiv und den gestoppten Dienst.
- `rawmidi` erlaubt je Substream einen Öffner; Messwerkzeuge dürfen nicht
  parallel zum Dienst laufen.
- Ein einmal angenommener Frame lässt sich nicht zurückholen; Schutz muss vor
  dem `write` greifen.

## Goals / Non-Goals

**Goals:**

- Der ENC liefert Eingaben unabhängig vom Feedback, solange nicht gemessen ist,
  dass seine LED-Ausgabe stabil ist.
- Die Ausgabe ist je Gerät steuerbar, getaktet und stoppt bei Stau.
- Stopp und Hotplug warten nicht auf Geräte, die nichts abnehmen.
- Die Messung am Gerät ist reproduzierbar beschrieben und beginnt mit dem
  Referenzverkehr von ShowCockpit oder dem MA2-Lua-Plugin.

**Non-Goals:**

- Neue LED-Protokolle, Bank- oder Kanal-Logik der LED-Frames.
- Änderungen an der Eingabepipeline, am Mapping oder am Beschleuniger.
- Behebung von USB-Disconnects des ENC auf Hardwareebene.
- Backoff-Obergrenze beim Öffnen (eigener Change).

## Decisions

### D1: `enabled` je Profil

`[profiles.<id>.led_feedback]` bekommt `enabled: bool` (Default `true`).
`build_feedback_targets` überspringt Profile mit `enabled = false`; damit
entstehen weder Ziele noch Polling-Blöcke für Geräte ohne Feedback. Sind alle
Profile aus, gilt das bestehende Verhalten „kein LED-fähiges Ziel“ (kein
Polling). `config.toml` setzt `enabled = false` für `midicraft-enc`, bis die
Messung bestanden ist.

*Alternativen:* Profil ohne `[led_feedback]` zu lassen (verliert `led_notes`
und Dokumentation) oder globales `[feedback] enabled = false` (schaltet auch
die ASL ab, die funktioniert). Verworfen.

### D2: Getaktete Ausgabe je Gerät

Statt `midi.send` direkt aufzurufen, reiht `_apply` den Zustand in eine
Ausgabe-Queue je Gerät ein, geordnet nach LED `(device, note)`; ein neuer
Zustand ersetzt einen offenen für dieselbe LED (Zusammenfassen). Ein Zeitgeber
je Gerät entnimmt höchstens einen Frame pro `frame_interval_ms`
(`[profiles.<id>.led_feedback]`, 1–500, Default 20) und sendet ihn über
`MidiManager.send`. Die Reihenfolge ist FIFO nach erster Einreihung; ein
Austausch behält die Position.

Der Startzustand (15 LEDs) braucht damit bei 20 ms rund 300 ms. Das ist
sichtbar genug unkritisch und beliebig feiner einstellbar.

`_last` wird erst nach erfolgreichem Senden aktualisiert (wie bisher), nicht
beim Einreihen.

*Alternativen:* Ein Zeitgeber für alle Geräte (die ASL würde vom ENC
ausgebremst), oder `asyncio.sleep` im `_apply` (blockiert den Poll-Zyklus).
Verworfen.

### D3: Stau erkennen über Status der Ausgabe

`rawmidi` meldet ausstehende Bytes über `SNDRV_RAWMIDI_IOCTL_STATUS`
(`avail` des Ausgabe-Substreams; `buffer_size − avail` = ausstehend). Vor jedem
Senden prüft die Ausgabe-Schleife des Geräts den Status. Bleibt „ausstehend > 0“
länger als 2 s (Konstante `OUTPUT_STALL_SECONDS`) bestehen, gilt die Ausgabe
des Geräts als gestaut: Die Schleife sendet nicht weiter, protokolliert
einmal `WARNING` mit Gerät und Anzahl ausstehender Bytes und hält offene Frames
zurück. Mit dem Wiederöffnen des Geräts (neues Handle, `_sync_devices`) wird der
Zustand zurückgesetzt und der Startzustand neu gesendet.

`EAGAIN` beim Schreiben (Puffer voll) zählt ebenfalls als Stau, ist aber nicht
die Messgröße: Im Fall vom 2026-11-26 war der Puffer fast leer (21 von 4096
Bytes), das Gerät holte dennoch nichts ab.

Fällt der Status-ioctl aus (z. B. Testumgebung mit Fake-FD), gilt „nicht
gestaut“; es gibt dann nur den `EAGAIN`-Pfad.

*Offene Frage:* Ob der Status-ioctl auf dem ENC zuverlässig `avail` liefert,
klärt die Messung (Gruppe 1). Fallback wäre `/proc/asound/cardN/midi0`
(`Avail`), aber das ist weniger robust und gehört nicht in den Daemon.

### D4: Schließen verwirft Ausgabe

`RealMidiHandle.close` ruft vor `os.close` den ioctl `SNDRV_RAWMIDI_IOCTL_DROP`
für den Ausgabe-Substream auf (nur wenn schreibbar geöffnet). Fehler dabei sind
nur ein DEBUG-Eintrag. Der Kernel wartet beim `close()` dann nicht auf den
Drain. Damit entfällt die Wartezeit je Gerät (vorher bis zu 10 s im
Kernel-Drain), und Hotplug und Stopp sind nicht mehr vom gestauten Gerät
abhängig.

Ausstehende LED-Frames gehen dadurch beim Schließen verloren. Das ist
gewollt: Beim nächsten Öffnen wird der Zustand ohnehin neu ermittelt und
gesendet.

### D5: Messvorschrift

Die Messung beginnt mit dem **Referenzverkehr**: Was sendet ShowCockpit oder das
MA2-Lua-Plugin an den ENC (Noten, Kanal, Velocity, Note-On/Off, Abstände,
Bündelung)? Aufzeichnung auf dem Rechner, auf dem es funktioniert, mit einem
MIDI-Monitor auf dem Ausgangsport (macOS: MIDI Monitor, Windows: MIDI-OX).
Danach läuft die Messung am Pi bei gestopptem Dienst über ein kleines
Python-Skript oder `amidi` (Schritte in `tasks.md`, Gruppe 1). Sie liefert pro
Schritt zwei Aussagen: LED sichtbar ja/nein und Eingabe danach weiter ja/nein,
ergänzt um `journalctl -k -f` (kein `urb status -32`, kein `drain error`).
Ergebnisse stehen in einer Tabelle im Design und bestimmen `led_notes`, die
Frame-Kodierung, `frame_interval_ms` und das `enabled` des ENC-Profils.

Weicht der Referenzverkehr von `midicraft-v2` ab (H1), wird nicht der Takt,
sondern die Kodierung angepasst; das wäre ein Folge-Change an
`add-midicraft-led-feedback`.

## Risks / Trade-offs

- **Ursache bleibt unklar**: Takt und Stau-Schutz machen den Daemon robuster,
  beheben aber nicht die Ursache im ENC. Bleibt die Ausgabe auch bei einzelnen
  Frames mit Pause instabil, bleibt der ENC auf `enabled = false`.
  *Mitigation:* Gruppe 1 vor Gruppe 2 bis 4 ausführen; Ergebnis gate-t die
  Aktivierung.
- **Verzögerte LED**: Mit Takt erscheinen LEDs bis zu rund 0,3 s später beim
  Start. Im Betrieb ändern sich wenige LEDs gleichzeitig, der Effekt ist
  kleiner als das Poll-Intervall von 250 ms.
- **ioctl-Portabilität**: Die Konstanten für `STATUS` und `DROP` sind
  Linux-ALSA-spezifisch. *Mitigation:* Kapselung in `RealMidiHandle`, Fehler
  führen zu „kein Stau erkannt“ beziehungsweise zu normalem `close`.
- **Verlorene Frames beim Schließen**: siehe D4, akzeptiert.

## Migration Plan

1. Sofortmaßnahme steht bereits auf dem Pi (`[feedback] enabled = false`).
2. Gruppe 1 (Messung) ausführen, Ergebnisse im Design festhalten.
3. Gruppen 2–4 umsetzen (Config, Ausgabe, Schließen).
4. ENC mit gemessenem `frame_interval_ms` und gemessener `led_notes`-Liste
   aktivieren; Bestätigung über Kernel-Log (keine Stall-Wellen) und
   dauerhafte Eingabe über 10 Minuten.
5. Rollback: `enabled = false` im Profil beziehungsweise global.

## Open Questions

- Welcher Mindestabstand ist am ENC stabil (1, 5, 20, 50 ms)? Antwort aus der
  Messung.
- Liefert der Status-ioctl am ENC `avail` korrekt (siehe D3)?
- Sind die Noten 65–69, 75–79, 80–84 am ENC wirklich die RGB-LEDs und gilt
  Kanal 1 für die aktive Bank? Antwort aus der Messung.
