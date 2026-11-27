# Design

## Context

Siehe proposal.md – Why. Ausgangslage im Code:

- `PlaybackRouter` (`ma2pi/playback.py`) löst Playback-Ziele auf (Bank,
  `page = "current"`, breite Executoren über `ExecutorTopology`) und schickt
  `PlaybackButton`/`PlaybackFader`-Aktionen an `Ma2Client`, der daraus
  `playbacks_userInput` baut.
- `PlaybackPoller` fragt `playbacks` für LED-Feedback und Topologie ab; das
  bleibt unverändert.
- Die Cherry bleibt bei `hardkey_transport = "lua"` (ADR 0016).
- Der Pi läuft mit Debian 13 (trixie); ein Paket `rtpmidid` gibt es dort nicht
  in den Quellen. PipeWire ist vorhanden.
- Der onPC-Rechner ist Windows; dort ist der rtpMIDI-Treiber von Tobias
  Erichsen der übliche RTP-MIDI-Endpunkt. Die MA liest MIDI von einem
  Eingangsport, den man im Setup wählt.
- Live bestätigt (verification.md): Eine Note per RTP-MIDI vom Pi auf eine
  MIDI-Remote respektiert eine per LUA vorbereitete Kommandozeile (Store).
- Der Screen-Helper lauschte auf UDP 5005, dem Datenport der RTP-MIDI-Session;
  er liegt jetzt auf UDP 5010.

## Goals / Non-Goals

**Goals:**

- ENC-Executor-Tasten verhalten sich wie Konsolentasten (Store, Assign, Edit,
  Delete, Move, Copy, Label greifen).
- Der Nutzer pflegt Ziele nur in `ma2pi`; die MIDI-Remotes der MA entstehen
  daraus.
- Der Web Remote bleibt für Feedback, Topologie, Encoder, Hardkeys und Screens.

**Non-Goals:**

- Kein MIDI-Feedback aus der MA (LEDs kommen weiter aus dem Polling).
- Keine MIDI-Remotes für Hardkeys oder Kommandos; nur Executor-Ziele.
- Kein eigener RTP-MIDI-Listener auf dem Pi (der Pi lädt ein, er nimmt keine
  Einladungen an).

## Decisions

### D1: Buttons über MIDI, Fader zunächst über den Web Remote

Nur Buttons brauchen die Kommandozeile. Für Fader spricht der Web Remote:

- Auflösung: `faderValue` ist ein Float; eine MIDI-Remote liefert 7 Bit
  (128 Stufen). Mit der Wert-Beschleunigung (`accelerated = true`) entstehen
  feine Zwischenwerte, die bei 7 Bit verloren gingen.
- Coalescing und Token-Bucket des Web Remote sind erprobt (ADR 0019).
- Ein Fader-Ziel braucht keine Remote in der Show.

Für MIDI-Fader spräche nur ein einheitlicher Weg. Deshalb bleiben Fader auf
`web`, Buttons gehen per Default über `midi`. `transport = "midi"` für Fader
lehnt die Konfigurationsprüfung ab; ein späterer Change kann das freigeben,
wenn ein Bedarf entsteht. M4 (verification.md) bestätigt: Fader-Remotes nehmen
den Wert aus der Note-Velocity mit 7 Bit, Control Change wird ignoriert.

Alternative: alles über MIDI (Wunsch des Nutzers als Ausgangspunkt) – zurück-
gestellt wegen Auflösung, nicht verworfen.

### D2: RTP-MIDI in `ma2pi` selbst (AppleMIDI-Initiator)

`ma2pi` implementiert die AppleMIDI-Sitzung direkt in asyncio: Einladung (`IN`
→ `OK`) auf Control- und Datenport, Clock-Sync (`CK0/1/2`), Abmelden (`BY`),
RTP-MIDI-Pakete ohne Recovery-Journal. Das sind wenige Nachrichtentypen über
UDP, gut mit Fakes testbar.

Alternativen:

- `rtpmidid` als Dienst plus ALSA-Sequencer: nicht in den Debian-Quellen,
  eigener Build/Dienst, zusätzlicher Weg ALSA → `ma2pi` (Raw-MIDI über
  `snd-virmidi` und `aconnect`). Mehr bewegliche Teile auf dem Pi.
- Python-Bibliothek für RTP-MIDI: keine gepflegte, kleine Abhängigkeit
  bekannt; die Paketliste des Pi bleibt schlank.

M1 (verification.md): rtpMIDI nimmt die Sitzung ohne Journal an, Clock-Sync
mit RTT unter 2 ms. Der Initiator beantwortet Clock-Sync-Anfragen der
Gegenstelle (`CK0`) und startet selbst periodisch einen Clock-Sync, damit die
Sitzung über Stunden stehen bleibt (im Test nur 8 s gehalten).

### D3: Adressvergabe aus reservierten Kanälen

Die Ziele mit Transport `midi` werden nach (Page, Executor, Button) sortiert
und der Reihe nach auf (Kanal, Note) der Liste `channels` gelegt: Kanal
`channels[0]` Note 0–127, dann `channels[1]` usw. `page = "current"` gilt als
eigener Page-Wert und sortiert vor den Zahlen. Ändert sich die Zielmenge,
können sich Adressen verschieben; das ist zulässig, weil der Abgleich (D4) die
Tabelle danach neu schreibt.

Alternative: Adresse aus Executor-Nummer ableiten (z. B. Note = Executor) –
verworfen, weil Pages und drei Buttons je Executor den Bereich sofort sprengen.

### D4: Abgleich per Telnet, Kanal als Besitzmarke

Telnet ist nötig, weil `command`-Frames des Web Remote keine Ausgabe liefern
und die Tabelle sonst nicht lesbar ist. `ma2pi` öffnet die Telnet-Verbindung
nur für den Abgleich, meldet sich mit dem Benutzer der MA-Verbindung an, liest
die MIDI-Remotes, schreibt die Differenz und schließt wieder. Besitz eines
Eintrags erkennt `ma2pi` ausschließlich am Kanal (`channels`); andere Einträge
werden nicht angefasst.

Befehlssyntax (M2, verification.md): `cd 36`, `cd 2` (relativ; `/36` geht
nicht), `list`, `store <nr>`, `assign <nr> /note= /channel= /type="Exec"
/page= /executor= /button="Button 1"` (`/page=0` = „Current Page on Master“),
`delete <nr> /noconfirm`. `store` braucht eine explizite Nummer; `ma2pi` nimmt
die nächste Nummer hinter dem höchsten vorhandenen Eintrag. Die MA meldet nur Zahlenfehler (`Error #7`, `Error #9`);
`assign` auf fehlende Einträge und ungültige Button-Namen gehen still durch.
Deshalb liest der Abgleich nach dem Schreiben die Tabelle erneut und vergleicht.
`delete` nummeriert die folgenden Einträge nach (gemessen); der Abgleich schreibt
erst um und an, nutzt übrige eigene Einträge wieder und löscht zuletzt
absteigend. Schlägt `assign` nach `store` fehl, wird der frische Eintrag sofort
gelöscht, sonst bliebe er auf Kanal „All“ außerhalb der Besitzmarke liegen.
Der Parser muss mehrwortige Felder („Current Page on Master“, „MIDI Input“,
„Button 1“) tragen; er arbeitet über die Spaltenpositionen der Kopfzeile. Die
Syntax steckt in einem eigenen Modul.

Der Abgleich läuft nicht im Eingabepfad: Tasten gehen sofort als MIDI raus,
solange das Ziel als abgeglichen gilt.

### D5: Weiche im Router, Topologie vor der Adresse

`PlaybackRouter` löst die Bank wie bisher auf und entscheidet danach anhand
von `transport`: `web` → Topologie-Auflösung und `PlaybackButton` an
`Ma2Client`, `midi` → `MidiRemoteButton` an den neuen Ausgang, **ohne**
Topologie-Auflösung. M3 zeigt: Eine Remote auf einem verdeckten Slot erreicht
den breiten Executor, und zwar mit der Tastenfunktion dieser Spalte – genau wie
eine Konsolentaste. Umleiten würde davon abweichen und Remotes bei jeder
Topologie-Änderung neu abgleichen müssen.

### D6: Kein stilles Ausweichen

Ein Rückfall auf den Web Remote würde den Store-Fehler unbemerkt zurückbringen:
Die Taste löst aus, statt zu speichern. Deshalb verwirft `ma2pi` Eingaben auf
nicht verfügbare `midi`-Ziele, warnt einmal je Ausfall und zeigt den Grund im
Status. Wer den alten Weg will, setzt `transport = "web"`.

### D7: Neue ADR

ADR 0019 verwarf MIDI-Remotes („nur per Telnet lesbar, keine Release-Semantik,
doppelte Pflege"). Die neue ADR hält fest: Die doppelte Pflege entfällt durch
den automatischen Abgleich, Telnet wird bewusst nur für den Abgleich genutzt,
und die Release-Semantik ist belegt (M3: Flash hält bei Note-On und endet
bei Note-Off). Sie ersetzt ADR 0019
nur für den Transport von Executor-Buttons.

## Messpunkte

Alle vier Messpunkte sind gemessen, Ergebnisse in verification.md: M1
RTP-MIDI ohne Journal angenommen; M2 Telnet-Syntax; M3 Release, aktuelle Page,
Store von der Cherry, breite Executoren; M4 Fader über Velocity mit 7 Bit.

## Risks / Trade-offs

- [Die MA nimmt nur einen MIDI-Eingang] → Der Eingang musste in der onPC auf
  rtpMIDI umgestellt werden; das direkte MIDI-Gerät geht danach nicht mehr und
  wird nicht gebraucht. rtpMIDI ist als einziger Eingang dokumentiert; ein
  weiteres Gerät käme über die „Live routings“ von rtpMIDI in die Session.
- [Show wird verändert] → nur reservierte Kanäle; `sync = "check"` für
  vorsichtige Installationen; Hinweis in der UI, die Show zu speichern.
- [Adressen verschieben sich bei Konfigurationsänderung] → Abgleich direkt nach
  Aktivierung; bis zum Abschluss gelten betroffene Ziele als nicht abgeglichen
  (D6), damit keine Taste auf eine alte Adresse feuert.
- [UDP-Verlust ohne Journal] → LAN, kleine Pakete; verlorenes Note-Off würde
  einen Flash hängen lassen. Abmilderung: Note-Off nach 20 ms einmal
  wiederholen (idempotent).
- [Telnet unverschlüsselt] → nur im Show-LAN, nur zum Abgleich geöffnet.

## Migration Plan

1. Deploy mit `[midi_remote] enabled = false`: Verhalten unverändert.
2. rtpMIDI auf dem onPC-Rechner einrichten, MA-MIDI-Eingang darauf stellen,
   Telnet in der MA aktivieren.
3. `enabled = true`, `sync = "auto"`: Buttons gehen über MIDI, Fader weiter über
   den Web Remote.
4. Rückweg: `enabled = false` oder `transport = "web"` je Ziel; die angelegten
   Remotes auf den reservierten Kanälen bleiben harmlos in der Show.

## Open Questions

- Soll die Web-UI einen Knopf „Remotes jetzt abgleichen" bekommen, zusätzlich
  zum automatischen Abgleich? (Ändert weder Spec noch Ablauf; Kosmetik.)
