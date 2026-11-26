# Design

## Context

Siehe `proposal.md` für Motivation und Scope. Die Messung am Gerät (zwei
vollständige Durchläufe, einzelner dauerhaft geöffneter ALSA-Zugriff) hat das
Layout des ENC festgelegt; alle Nachrichten laufen auf MIDI-Kanal 1:

| Control | Notes | Verhalten |
|---|---|---|
| Fader 1–5 | 70–74 | Note-On, Velocity = Position 0–127 (absolut) |
| Encoder 1–5 | 60–64 | Note-On, Velocity = Position 0–127 (absolut, an 0/127 geklemmt) |
| Encoder-Klicks 1–5 | 55–59 | Note-On `7F` / Note-Off `00` (Flash) |
| Tastenreihe oben | 65–69 | Flash |
| Tastenreihe mitte | 75–79 | Flash |
| Tastenreihe unten | 80–84 | Flash |

Bestehende Fakten im Code: `MidiManager` liest ALSA-Rawmidi über einen
dauerhaft geöffneten Dateideskriptor und `add_reader`; `_normalise` kennt nur
Tasten und relative Encoder und verwirft alles andere. `ProfileConfig` hat
`notes` und `midi_encoders`. Es gibt keine Executor-Ziele und keine
`playbacks_*`-Frames. `_find_led_device` wählt ohne `[led].device` das erste
konfigurierte MIDI-Gerät. Der Mapping-Editor bearbeitet nur
`mapping.keys`/`mapping.encoders`.

## Goals / Non-Goals

**Goals:**

- Das gemessene ENC-Layout als reguläres Geräteprofil abbilden, ohne
  Sonderpfade im MIDI-Leser.
- Absolute Werte generisch (Fader und Encoder) in die bestehende
  Ereignispipeline einspeisen.
- Executor-Ziele über den bestehenden Web Remote senden, mit geordneten
  Buttons und zusammengefassten Faderwerten.
- Zweites MIDI-Gerät parallel zum ASL betreiben, ohne dessen LED-Ausgabe zu
  stören.

**Non-Goals:**

- LED-Feedback, Executor-Polling und PickUp.
- Änderungen an der Relativ-Encoder-Semantik des ASL.
- MIDI-CC-Unterstützung; das Gerät sendet Note-On.
- Import oder Veränderung der MA-MIDI-Remote-Tabelle.
- Bearbeiten der Geräteprofile im Web-UI (Notes bleiben Konfigurationsdatei).

## Decisions

### 1. Absolutwerte als eigene Profilsektion `midi_values`

`ProfileConfig` erhält `midi_values: tuple[MidiValueProfile, ...]` mit
`control`, `note` und `kind` (`fader` oder `encoder`). Die Note wird wie bei
`notes` und `midi_encoders` validiert und darf mit keiner anderen Note des
Profils kollidieren. `validate_midi_profile` akzeptiert ein Profil, wenn
mindestens eine der drei Sektionen belegt ist.

Alternative: absolute Werte als `midi_encoders` mit einem Flag behandeln. Das
vermischt zwei Semantiken (Delta vs. Absolutwert) in einem Typ und macht die
Validierung und den Leser unnötig kompliziert.

### 2. Ein Wertereignis für Fader und absolute Encoder

`_normalise` erzeugt für konfigurierte Absolut-Notes
`InputEvent("value", control, velocity / 127, device)`. Note-Off wird
verworfen. Fader und Encoder teilen sich diesen Pfad; der Unterschied ist nur
die logische Control-ID. Die Skalierung auf 0.0–1.0 passiert genau einmal an
der Gerätegrenze, damit Mapping und Frame-Erzeugung mit einem einheitlichen
Wertebereich arbeiten.

### 3. Playback-Ziele als eigene Mapping-Tabelle

Neue Sektion `[mapping.playbacks.<control>]` statt einer Erweiterung von
`KeyMapping`:

```toml
[mapping.playbacks."midicraft.fader.1"]
page = 1
executor = 1
kind = "fader"

[mapping.playbacks."midicraft.click.1"]
page = 1
executor = 1
kind = "button"
button = 1
```

Gründe: `KeyMapping` ist auf Press/Release und Hardkey/Command ausgelegt;
Fader-Ziele brauchen keine Button-Nummer, Button-Ziele keine Hardkey-Felder.
Eine getrennte Tabelle hält bestehende Konfigurationen unverändert und erlaubt
eine klare Vorrangregel.

### 4. Vorrangregel vor dem MappingEngine

`__main__._process_input` fragt zuerst den neuen `PlaybackRouter`. Hat das
Control ein Playback-Ziel, wird das Ereignis dort verarbeitet und nicht an den
`MappingEngine` weitergereicht. Sonst bleibt der bisherige Pfad unverändert.
Damit kann ein Control nicht gleichzeitig einen Hardkey und einen Executor
auslösen; die Konfiguration bleibt trotzdem rückwärtskompatibel, weil die
Sektion optional ist.

### 5. Frames und Indexumrechnung

Neue Builder in `frames.py`:

```json
{"requestType":"playbacks_userInput","execIndex":0,"pageIndex":0,
 "buttonId":0,"pressed":true,"released":false,"type":0,"session":N}
```

```json
{"requestType":"playbacks_userInput","execIndex":0,"pageIndex":0,
 "faderValue":0.5,"type":1,"session":N}
```

Die Konfiguration bleibt 1-basiert (wie die MA-Oberfläche); die Umrechnung
`-1` erfolgt ausschließlich im Builder. `button = 1..3` wird zu `buttonId =
0..2`. Der `session`-Wert kommt wie bei allen anderen Frames aus dem
`Ma2Client`.

Für `page = "current"` sendet der Builder `pageIndex = -1`. Die MA
interpretiert das als die aktuell aktive Master-Page, analog zur
Remote-Input-Einstellung „Current Page on Master". `ma2pi` muss die Page dafür
weder kennen noch pollen; ein Seitenwechsel auf der MA wirkt sofort. Die
Semantik von `-1` wird bei der Hardware-Abnahme bestätigt. Falls die MA den
Wert nicht akzeptiert, bleibt als Ausweichweg nur ein leichter
`playbacks`-Poll der aktuellen Page.

### 6. Getrennte Warteschlangen für Buttons und Fader

`SendQueue` erhält neben der Control- und Encoder-Klasse eine dritte,
zusammengefasste Klasse für Fader, gekeyt auf `(page, executor)`. Ein neuer
Wert überschreibt den noch nicht gesendeten Wert desselben Ziels; der letzte
Wert gewinnt. Buttons bleiben in der Control-Klasse und damit strikt geordnet.
Der Router merkt sich zusätzlich den zuletzt enqueuten Wert pro Ziel und
verwirft unveränderte Werte, bevor sie die Queue erreichen.

Alternative: Fader als normale Control-Actions senden. Bei einem Fader-Sweep
entstehen dann hunderte Frames, die den Token-Bucket füllen und Button-Releases
verzögern. Coalescing ist für absolute Werte zwingend.

### 7. Zwei MIDI-Geräte und eindeutige LED-Wahl

`select_midi_devices` unterstützt bereits mehrere konfigurierte Geräte; jedes
bekommt einen eigenen `RealMidiHandle`. Es bleibt beim dauerhaft geöffneten
Deskriptor, damit das beim ENC beobachtete Stummschalten nach häufigem
Öffnen/Schließen nicht auftritt. Für die LED-Ausgabe wird die Auswahl
verschärft: Ist die LED-Ausgabe aktiviert, mehr als ein Gerät mit Backend `midi`
konfiguriert und `[led].device` nicht gesetzt, bricht die Validierung mit einer
klaren Meldung ab. Damit kann die ASL-LED nicht versehentlich am ENC landen.

### 8. Web-UI erweitert die bestehende Mapping-Ansicht

`/api/devices` liefert je Gerät zusätzlich `values` (Control, Note, Art). Der
Mapping-Editor zeigt diese Controls in einer neuen Playback-Sektion und
schreibt `mapping.playbacks` über den vorhandenen `PUT /api/config`-Pfad.
Kein neuer Endpunkt, keine neue Berechtigungslogik. Die Validierung bleibt
serverseitig maßgeblich; die Oberfläche prüft zusätzlich die Feldbereiche.

### 9. Obsoletes Change entfernen, ADR ergänzen

`openspec/changes/add-midicraft-remote-import/` wird gelöscht; es enthält keine
Implementierung und keine archivierten Specs. Die neue Architekturentscheidung
(absolutes MIDI, Executor-Ziele über den Web Remote, kein Feedback in v1) wird
als ADR mit Status `Proposed` dokumentiert und bei Annahme übernommen.

## Risks / Trade-offs

- **Sprung beim Seitenwechsel ohne PickUp** → Bekannte Einschränkung; der
  Fader sendet sofort seine absolute Position. Mitigation: im README
  dokumentieren, Fader vor dem Seitenwechsel parken; PickUp/Feedback folgt im
  nächsten Change.
- **Falsche Button-ID auf der echten MA** → Button 1–3 wird zu `buttonId` 0–2.
  Mitigation: Hardware-Abnahme mit allen drei Button-Nummern; bei Abweichung
  nur die Umrechnung im Builder korrigieren.
- **`pageIndex = -1` wird nicht als aktuelle Page verstanden** → Mitigation:
  bei der Hardware-Abnahme zuerst einen Button auf `page = "current"` drücken
  und im Frame-Log prüfen, ob der Executor der aktiven Page reagiert. Falls
  nicht, auf einen `playbacks`-Poll der aktuellen Page ausweichen.
- **Fader-Flut bei schnellen Bewegungen** → Coalescing pro Ziel plus
  bestehender Token-Bucket. Mitigation: Frame-Zähler im Status beobachten.
- **LED-Ausgabe am falschen Gerät** → Validierungsfehler bei mehreren
  MIDI-Geräten ohne `[led].device`. Mitigation: Beispielkonfiguration und
  Fehlermeldung nennen das erwartete Feld.
- **Profil-Notes kollidieren** → Validierung verhindert doppelte Notes über
  `notes`, `midi_encoders` und `midi_values`. Mitigation: Test für jede
  Kollisionsart.
- **Gerät wird während des Betriebs neu enumeriert** → Der Zugriff schlägt fehl
  und wird vom bestehenden Reconcile-Loop neu geöffnet; andere Geräte bleiben
  unberührt. Mitigation: Test mit `FakeMidiSource`.
- **Bestehender Test erwartet genau zwei Geräte** → `test_example_config_is_valid`
  muss die neue Geräteliste prüfen. Mitigation: Test im selben Change anpassen.

## Migration Plan

1. Neue Konfiguration validieren (`openspec`-unabhängig: `parse_config`), dann
   per `PUT /api/config` ohne Dienstneustart anwenden.
2. Beispielkonfiguration um `[devices.midicraft]`, `[profiles.midicraft-enc]`
   und eine auskommentierte `[mapping.playbacks]`-Vorlage ergänzen;
   `[led].device = "asl"` explizit setzen.
3. Rollback: die neuen Sektionen entfernen oder ein Backup über die
   bestehende Backup-Funktion einspielen. Ein Downgrade auf eine ältere
   `ma2pi`-Version lehnt die neuen Schlüssel ab; deshalb vor dem Ausrollen ein
   Backup anlegen.

## Open Questions

- Welche Page/Executors der konkreten Show belegt werden, ist Benutzerdaten und
  wird bei der Hardware-Abnahme im UI gesetzt; das ändert weder Spec noch
  Design.
- Ob absolute Encoder später auch Nicht-Executor-Ziele (z. B. Attributwerte)
  steuern sollen, ist nicht Teil dieses Changes und wird bei Bedarf als
  eigenes Change bewertet.
