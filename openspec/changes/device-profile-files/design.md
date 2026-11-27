# Design

> **Status: Entwurf, Review erforderlich.** Die Entscheidungen R1–R9 unten sind
> Vorschläge mit Begründung. Sie werden im Review bestätigt oder geändert und
> dann in Gruppe 0 von `tasks.md` abgehakt. Erst danach beginnt die Umsetzung.

## Context

Motivation und Messwerte: siehe `proposal.md` (Why). Für den Entwurf relevante
Beobachtungen am Ist-Stand:

- **Profile und Layouts sind bereits je Profil adressiert.** `devices.<name>.profile`
  verweist auf ein Profil, `layout_for_device` schlägt `layouts` nach
  Profilname nach. Eine Datei je Profil entspricht dem vorhandenen Schlüssel.
- **Redundanz im Detail (gemessen an `config.toml`):**

  | Profil | Controls (Gruppen) | Bänke | Layout |
  |---|---|---|---|
  | `midicraft-enc` | 30 (4× Taste à 5, 5 Fader, 5 Encoder) | 16, davon 1 mit 30 Noten | 6 Reihen à 5 |
  | `midicraft-push` | 30 (30 Tasten) | 16 leer | 5 Reihen à 6 |
  | `midicraft-fade` | 25 (20 Tasten, 5 Fader) | 16 leer | 5 Reihen à 5 |
  | `midicraft-turn` | 30 (15 Tasten, 15 Potis) | 16 leer | 6 Reihen à 5 |
  | `midicraft-mix` | 25 (15 Tasten, 5 Fader, 5 Potis) | 16 leer | 5 Reihen à 5 |
  | `midicraft-spot` | 25 (10 Tasten, 5 Fader, 10 Potis) | 16 leer | 5 Reihen à 5 |

  Alle Bänke haben Kanal = Nummer. Control-IDs sind `<präfix>_<n>` mit
  fortlaufender Nummer, Labels `B<n>`/`F<n>`/`P<n>`/`E<n>` (bei `midicraft-enc`
  fortlaufend über vier Tastengruppen: B1–B20). In 5 von 6 Layouts stimmen
  Zell-Label und Control-Label überein.
- **`ConfigStore` kennt genau eine Datei.** `ConfigPaths.config`,
  `prepare_patch` (tomlkit-Dokument der einen Datei), `commit_prepared`
  (Backup `config-<stamp>.toml`, `last-good.toml`, atomarer Rename),
  `list_backups`/`read_backup` (nur `*.toml`-Namen) und `restore` setzen das
  voraus.
- **Die UI schreibt von allen Profildaten nur `profiles.<p>.banks`** zurück
  (`DevicesPage.svelte`, Learn-Speichern). Controls, Layouts, Noten flacher
  Profile und `led_feedback` werden von der UI nicht geschrieben. `merge_patch`
  ersetzt Listen komplett: ein Bank-Patch enthält also immer **alle** Bänke.
- **Vorbild für gefährliche Schlüssel**: `ma2.password_file`/`password_env`
  werden aus API-Patches verworfen (kein Datei-Orakel). `profiles_dir` ist
  derselbe Fall.
- Die Konfiguration ist strikt (`_reject_unknown`); neue Schlüssel brauchen
  Schema-Änderungen und Fehlerpfade mit Position.

## Goals / Non-Goals

**Goals:**

- Profildefinition eines Geräts liegt in genau einer, kleinen, lesbaren Datei.
- `config.toml` enthält nur Betriebskonfiguration (~600 statt 2617 Zeilen).
- Laufzeit, `GET /api/config`, Geräte-API und UI bleiben **unverändert**; sie
  sehen immer die expandierte, zusammengeführte Konfiguration.
- Bestehende monolithische Konfigurationen laufen unverändert weiter;
  Aufteilung ist ein bewusster, rückfallfähiger Schritt.
- Backups/Restore bleiben konsistent und vollständig.

**Non-Goals:**

- Kein generisches Vererbungs-/Template-System zwischen Profilen
  (`extends`), keine Variablen/Schleifen in der Konfiguration.
- Keine Verlagerung von `[devices.*]` (USB-IDs, Namensfilter) oder von
  `mapping`, `hardkeys`, `ma2` in eigene Dateien.
- Kein Hot-Reload per Dateiüberwachung (Änderungen laufen weiter über die API
  oder Neustart/`--check-config`).
- Keine Änderung am Frontend und an der REST-API außer dem additiven Feld
  `kind` in der Backup-Liste (R5).
- Kein Mitliefern von Profilen als Paketdaten mit Überlagerung (siehe R1,
  Option B).

## Review-Entscheidungen

### R9: Gehören Noten zum Modell oder zur Geräteinstanz? — **entschieden: Option 1** (Andreas, 2026-11-26)

Aus der Praxis (zwei MIDICRAFT ENC mit unterschiedlicher Belegung) ergibt sich:
Die **Noten-Belegung gehört physisch zum einzelnen Gerät**, das Control-
Inventar und das Layout zum **Modell**. Das heutige Schema vermischt beides im
Profil und erzwingt für zwei unterschiedlich belegte Geräte zwei Profile mit
getrennten Control-Präfixen (Control-Namen müssen konfigurationsweit eindeutig
sein, Encoder-IDs ebenfalls).

- **Option 1 (Ist-Stand, kein Schemawechsel):** Ein Profil je Gerät, auch bei
  gleichem Modell. Teil B (Templates) macht das billig (zweite Datei: Präfix und
  Bank-Belegung ändern, Gruppen und Layout identisch kopieren). Teil A lässt
  sich nahtlos anwenden: je Gerät eine Datei.
- **Option 2 (Schemawechsel):** Modell-Profil (Controls, Layout, Bank-Schema)
  teilen, die Noten-Belegung je Bank wandert in das Geräte-Objekt
  (`[devices.<name>.banks]`). Zwei ENC = ein Profil, zwei Geräte-Einträge mit
  eigener Belegung. Das wäre die saubere Trennung, bedeutet aber einen
  Eingriff in Parser, Mapping-Auflösung (Control-Namen wären dann je Gerät
  gleich, `mapping.playbacks` müsste je Gerät unterscheiden), Learn-Speichern,
  `serialize.py` und UI – ein eigener, größerer Change.

**Entscheidung:** Option 1. Ein Profil gehört zu genau einem physischen Gerät,
auch wenn mehrere Geräte dasselbe Modell sind; Spec und Tasks setzen das voraus
(Szenario „Zwei Geräte desselben Modells“ in `profile-templates`). Option 2
(Noten je Geräteeintrag, Modell-Profil geteilt) bleibt ein möglicher
Folge-Change, falls gleichartige Geräte mit abweichender Belegung der Normalfall
werden; R1 und der Umfang dieses Changes bleiben davon unberührt.

### R1: Wo liegt der Schreibzustand? (Empfehlung: Option A)

Bank-Belegungen sind **Nutzerdaten** (am MIDICRAFT frei einstellbar, per Learn
gespeichert), Control-Inventar und Layout sind **Hardware-Beschreibung**.

- **Option A (Vorschlag, entspricht „eine Datei je Gerät“):** Die Profildatei
  enthält alles zum Profil inklusive gelernter Noten. `ConfigStore` schreibt
  in die Datei des Profils. Vorteil: ein Ort je Gerät, einfaches mentales
  Modell, Gerätedatei ist als Ganzes kopier- und sicherbar. Nachteil:
  `ConfigStore` muss Mehrdatei-Schreiben, Dateisatz-Backups und Restore
  können (R3, R5) – der riskanteste Teil dieses Changes.
- **Option B:** Profildateien sind rein lesende Hardware-Definition; gelernte
  Bank-Noten und LED-Einstellungen bleiben als schmale Überlagerung
  (`[profiles.<name>]` mit nur `banks`/`led_feedback`) in `config.toml`.
  Vorteil: `ConfigStore`, Backups und Restore bleiben unverändert
  (Einzeldatei). Nachteil: Daten eines Geräts liegen an zwei Orten, es braucht
  Überlagerungsregeln, und `config.toml` wächst mit jedem gelernten Gerät.

Das Spec (`device-profile-files`) setzt Option A voraus. Fällt die Wahl auf B,
entfallen die Requirements „Änderungen landen in der Datei des Profils“ sowie
alle `runtime-config`-Deltas, und es kommt eine Überlagerungs-Requirement dazu.

### R2: Datei je *Profil* (= Gerätemodell), nicht je Geräteinstanz

Dateiname = Profilname (`profiles.d/midicraft-enc.toml`), weil `layouts` und
`devices.<name>.profile` bereits so adressiert sind. `[devices.*]` bleibt in
`config.toml`, da USB-IDs und Namensfilter anlagenspezifisch sind.

**Achtung, Einschränkung:** Ein Profil enthält heute neben der Hardware-
Beschreibung auch die **Noten-Belegung je Bank** (was das Gerät sendet). Zwei
physische Geräte des gleichen Modells, die am Gerät unterschiedlich belegt sind,
können sich daher **kein** Profil teilen (siehe R9). Die Konfiguration erlaubt
zwar mehrere `[devices.*]` mit demselben Profil, aber dann gelten Noten und
Control-Namen für beide Geräte gleich.

*Offene Option:* Geräteerkennung ins Profil ziehen (Katalog-Gedanke); bewusst
nicht Teil dieses Changes.

Dateiformat:

```toml
# profiles.d/midicraft-enc.toml  -> Profil "midicraft-enc"
[profile]                 # entspricht [profiles.midicraft-enc]
bank_count = 16
control_groups = [
  { prefix = "mc_click",   kind = "button",  count = 5, label = "B{n}" },
  { prefix = "mc_row1",    kind = "button",  count = 5, label = "B{n}", label_start = 6 },
  # ...
  { prefix = "mc_fader",   kind = "fader",   count = 5, label = "F{n}" },
  { prefix = "mc_encoder", kind = "encoder", count = 5, label = "E{n}" },
]

[[profile.banks]]         # nur Bänke mit Belegung oder abweichendem Kanal
number = 1
notes = { "55" = "mc_click_1", "56" = "mc_click_2" }

[layout]                  # entspricht [layouts.<key>] ohne "profile ="
columns = 5
[[layout.rows]]
cells = [{ control = "mc_encoder_{n}", label = "E{n}", color = "blue", count = 5 }]
```

### R3: Mehrdatei-Schreiben (Empfehlung: geordnete Renames + Satz-Backup)

Ein Apply kann Profildatei(en) und Hauptdatei betreffen; Restore betrifft immer
mehrere.

- **Vorschlag:** Vorab Backup des *vollständigen* alten Satzes (R5), dann jede
  geänderte Datei einzeln per temp+fsync+rename (bestehende `_atomic_write`),
  Profildateien zuerst, `config.toml` zuletzt. Abbruch dazwischen hinterlässt
  einen Satz, in dem jede Datei vollständig lesbar ist; ein Querverweis-Fehler
  wird beim Start mit Dateiname gemeldet, Restore des Backups behebt ihn.
  Das Zeitfenster ist Mikrosekunden und betrifft nur Patches, die gleichzeitig
  Profil *und* Mapping ändern (die UI sendet das nicht).
- *Alternative 1:* Apply auf **eine** Zieldatei beschränken (`422
  multi_file_patch`). Trivial atomar, löst aber Restore nicht.
- *Alternative 2:* Generationsverzeichnis mit atomarem Symlink-Wechsel.
  Echte Atomizität, aber `config.toml`-Pfad, `--config`, `install.sh` und alle
  Dokumente müssten auf das Symlink-Modell umgestellt werden.

### R4: Aktivierung explizit über `profiles_dir`

Kein Auto-Discovery von `profiles.d/` neben der Datei. Gründe: die Konfiguration
ist strikt und kennt keine Magie; `--config` mit abweichendem Dateinamen
(`config_file`) bleibt eindeutig; ein vergessenes Verzeichnis wird nicht
stillschweigend geladen. Sicherheitsregeln: nur relativer Pfad, keine
`..`-Segmente, aufgelöster Pfad muss im Konfigurationsverzeichnis liegen,
Symlinks aus dem Verzeichnis heraus werden abgelehnt; `_clean_patch` verwirft
`profiles_dir` aus API-Patches wie `password_file`.

### R5: Backup als Verzeichnis-Satz

Neues Backup bei vorhandenem `profiles_dir`: Verzeichnis
`backups/config-<stamp>/` mit `config.toml` und `profiles.d/*.toml`;
`last-good/` analog. Ohne `profiles_dir` bleibt es bei `config-<stamp>.toml`
(Abwärtskompatibilität, bestehende Backups restore-bar). `list_backups`
liefert zusätzlich `"kind": "set" | "file"` (additiv; die UI ignoriert
unbekannte Felder). Backup-ID bleibt der Name; Pfad-Traversal-Schutz wird auf
Verzeichnisnamen erweitert (`^config-\d{8}-\d{6}(-\d+)?$`). Restore eines
Satzes ersetzt `config.toml` und das gesamte Profilverzeichnis (nach Sicherung
des aktuellen Satzes); Restore eines Einzeldatei-Backups aktiviert eine
monolithische Konfiguration ohne `profiles_dir`, wodurch vorhandene
Profildateien ignoriert, aber nicht gelöscht werden. Rotation zählt Backups
(Satz = 1), nicht Dateien.

*Alternativen:* Tar-Archiv (opak, nicht mit Standardwerkzeugen lesbar),
abgeflachtes Einzel-TOML (verliert die Aufteilung beim Restore).

### R6: Syntax der kompakten Deklaration (Teil B)

Entwurf (Beispiel siehe R2):

- `bank_count = N` (1–16) im Profil; ausdrückliche `[[banks]]` überschreiben
  je `number`; `number > bank_count` ist ein Fehler.
- `control_groups`: `{ prefix, kind, count, label?, label_start? }`; ID
  `<prefix>_<i>` für `i = 1..count`; Label-Muster mit `{n}`, wobei
  `n = label_start + i − 1` (Default `label_start = 1`). `encoder_id` bei
  `relative-encoder` wie bisher über das Namensschema oder explizit
  ausgeschriebene Controls. Exklusiv zu `controls`.
- Layout-Zelle als Muster: `{ control = "<muster>", label = "<muster>", color?,
  count, start? }` erzeugt `count` Zellen mit `n = start + i − 1`
  (Default `start = 1`); nicht kombinierbar mit `row`/`col`/`col_span`/`row_span`
  (absolute Positionierung bleibt ausgeschriebenen Zellen vorbehalten). Das
  Zellen-Muster statt eines Zeilen-Musters erlaubt gemischte Zeilen und passt
  in eine Zeile je Reihe.
- Einziger Platzhalter ist `{n}`; Verschachtelung/Arithmetik gibt es nicht.

*Alternative:* generische Vererbung (`extends = "midicraft-base"`) – mächtiger
(teilt auch `led_feedback`), aber ein neues Konzept mit eigener Fehlerklasse und
Zyklenprüfung; für sechs Profile mit je einer Gruppenliste unverhältnismäßig.

### R7: Schreibnormalisierung nur für `banks`

Der Bank-Patch der UI enthält alle Bänke und würde `bank_count` aufblähen.
Vorschlag: Nach dem Zusammenführen wird `banks` im betroffenen Profil
**kompaktiert** – Bänke, die dem Erzeugten entsprechen (Kanal = Nummer, ohne
Noten, Nummer ≤ `bank_count`), werden nicht ausgeschrieben. Alle anderen
Schlüssel des Profils bleiben unangetastet (tomlkit erhält Kommentare). Controls
und Layout werden nie geschrieben (UI-Realität, siehe Context).
*Alternative:* Bank-Patch pro Nummer mergen (API-Änderung am Listen-Merge) –
verworfen, weil RFC 7386 dann nicht mehr gilt und alle Aufrufer betroffen wären.

### R8: Reihenfolge der Umsetzung (Empfehlung: Teil B vor Teil A)

Teil B (Templates) liefert fast den gesamten Größengewinn (2000 → ~250 Zeilen
für Profile und Layouts) und braucht **keine** Änderung an `ConfigStore`-
Schreiben und Backups; Teil A ist Organisation und trägt das Risiko. Beide sind
unabhängig auslieferbar. `tasks.md` ist daher B-zuerst gegliedert; sollte das
Review nur einen der Teile wollen, entfällt der andere ohne Rest.

## Decisions

### D1: Expansion beim Laden, nicht in der Laufzeit

Parser (`config/profiles/…`) erzeugen aus kompakter und ausgeschriebener Form
dieselben Dataclasses (`ProfileConfig.controls/banks`, `DeviceLayout.rows`). Alle
nachgelagerten Module (`mapping`, `midi_input`, `feedback`, `serialize`,
`devices`) bleiben unverändert. Absicherung: **Äquivalenztest** – jedes
mitgelieferte Profil wird einmal ausgeschrieben (Stand vor dem Umbau) und einmal
kompakt geladen; `redacted_config()` und `ProfileConfig`/`DeviceLayout` müssen
gleich sein.

### D2: Ladereihenfolge und Validierung

1. Hauptdatei parsen; `profiles_dir` validieren (R4).
2. Profildateien in sortierter Reihenfolge einlesen; je Datei nur `profile` und
   `layout` zulassen; Profilname aus Dateiname, Namensschema wie bisherige
   Profilnamen (`[A-Za-z0-9._-]+`).
3. Profile zusammenführen (Eindeutigkeit prüfen), dann die bestehenden
   Querverweis-Prüfungen unverändert über die zusammengeführte Sicht laufen
   lassen (Geräte → Profile, Mapping → Controls, Layout → Controls).
4. Fehlerpfade erhalten das Präfix `profiles.d/<datei>.toml:` für Dateien
   (`ConfigError.path`), für die Hauptdatei bleiben sie wie bisher.

`load_config(path)` bleibt die einzige Einstiegsfunktion; `parse_config(raw,
source_path)` akzeptiert ohne Dateisystemzugriff weiter ein Dict (Tests), wobei
Profildateien über einen injizierbaren Reader geliefert werden.

### D3: Schreibrouting im `ConfigStore`

`prepare_patch` zerlegt den Patch anhand der Schlüssel: `profiles.<p>` und
`layouts.<…>` für ein in einer Datei definiertes Profil gehen in dessen
tomlkit-Dokument, alles Übrige in das der Hauptdatei. Validiert wird einmal
über die zusammengeführte Kandidaten-Sicht (wie heute `validate(candidate)`),
danach wird pro betroffener Datei Text erzeugt und per `tomllib` gegengeprüft.
`PreparedConfig` trägt statt `text` eine Zuordnung `Pfad → Text`;
`commit_prepared` führt Backup und die Renames gemäß R3 aus. Tests, die
`PreparedConfig.text` benutzen, werden auf die Zuordnung umgestellt.

### D4: `--split-config`

CLI-Flag in `__main__`/`cli.py`; arbeitet mit `ConfigPaths` auf der aktiven
Konfiguration, erstellt Backup (R5), liest die Hauptdatei mit tomlkit, verschiebt
jede `[profiles.<p>]`/`[[profiles.<p>.*]]`- und die zugehörige
`[layouts.<key>]`-Tabelle (Layout wird über sein `profile`-Feld dem Profil
zugeordnet) in `<p>.toml`, setzt `profiles_dir`, validiert den Satz und
vergleicht `redacted_config()` vor und nach dem Schnitt. Erst danach wird
geschrieben (Reihenfolge R3). Layouts, die auf kein Profil verweisen, bleiben
in der Hauptdatei. Der Befehl macht **keine** Kompaktierung (das ist Teil B,
manuell oder per eigenem Hilfsbefehl).

### D5: Deploy und Berechtigungen

`ensure_layout` legt `profiles_dir` mit `0750` an, Dateien `0640`, Owner
`ma2pi`. `deploy/install.sh` kopiert die mitgelieferten `profiles.d/*.toml`
nur, wenn das Zielverzeichnis fehlt oder die jeweilige Datei fehlt, und
überschreibt nie (Profile enthalten gelernte Noten = Nutzerdaten). Folge:
Änderungen an mitgelieferten Profilen erreichen bestehende Installationen
nicht automatisch; das wird in README und ADR dokumentiert. Die
systemd-Unit schreibt bereits nach `/var/lib/ma2pi`; zu prüfen ist nur, dass
das Unterverzeichnis dort liegt (Task 3.4).

## Risks / Trade-offs

- **[Risiko] Mehrdatei-Schreiben verletzt die bisherige Garantie „ein Abbruch
  darf nichts zerstören“** → R3: Satz-Backup vor dem ersten Rename, jede Datei
  einzeln atomar, Start meldet ungültigen Zwischenstand mit Dateiname;
  Test, der den Prozess zwischen zwei Renames abbricht (Fault-Injection über
  einen injizierbaren Writer).
- **[Risiko] Expansion verändert Semantik unbemerkt** → D1-Äquivalenztest mit
  allen sechs MIDICRAFT-Profilen plus Golden-Test aus `modularize-backend-packages`
  (Task 0.3); Fehlerfälle als Tabelle.
- **[Risiko] Kompaktierung beim Schreiben zerstört Kommentare oder
  Formatierung der Profildatei** → nur der `banks`-Schlüssel wird ersetzt;
  Test mit Kommentaren in `control_groups` und `[layout]`.
- **[Risiko] Alte Backups und neue Struktur kollidieren** (Restore einer
  Einzeldatei bei vorhandenem Profilverzeichnis) → R5-Regel „Verzeichnis wird
  nur mit `profiles_dir` gelesen“; Szenarien im Spec.
- **[Risiko] Profile in der Hauptdatei und in Dateien zugleich**
  (Verwirrung) → Eindeutigkeitsfehler nennt beide Fundstellen; Mischbetrieb ist
  bewusst erlaubt (Migration schrittweise).
- **[Risiko] Upgrade überschreibt gelernte Noten** → D5: nie überschreiben.
- **[Risiko] Frontend/Backups-Seite stolpert über Verzeichnis-Backups** →
  `kind` ist additiv; BackupsPage-Test mit Satz-Eintrag; `size` bei Sätzen
  = Summe.
- **[Trade-off] Zwei Orte für „Konfiguration“** (Hauptdatei + Verzeichnis) →
  explizites `profiles_dir`, `--check-config` nennt beide, README
  beschreibt die Aufteilung.
- **[Trade-off] Kompakte Syntax ist eine zusätzliche Sprache** → bewusst
  minimal (ein Platzhalter, drei Konstrukte), vollständig ausgeschriebene Form
  bleibt jederzeit gültig und ist der Fallback für Sonderfälle.

## Migration Plan

1. Teil B ausrollen: bestehende Konfigurationen bleiben gültig; die
   mitgelieferte Beispielkonfiguration wird auf kompakte Form umgestellt
   (Test: expandiert gleich der alten).
2. Teil A ausrollen; auf dem Pi `python -m ma2pi --split-config` (Backup
   automatisch), danach `--check-config`, dann Dienst-Neustart.
3. Rückweg: Backup aus der Backup-Liste wiederherstellen (Satz oder Einzeldatei);
   `profiles_dir` aus `config.toml` entfernen reicht, um wieder monolithisch zu
   laden (Profile müssten dann in die Hauptdatei zurückkopiert werden – deshalb
   ist das Backup der Rückweg, nicht ein Gegenbefehl).

## Open Questions

- Soll `profiles_dir` einen Default bekommen (`"profiles.d"`), sobald das
  Verzeichnis existiert? Vorschlag: nein (R4); kann später ohne Spec-Änderung
  an der Datenstruktur nachgezogen werden.
- Brauchen die mitgelieferten Profile eine Versionsnummer (`profile_version`),
  damit ein künftiges Upgrade-Werkzeug veraltete Definitionen erkennen kann?
  Vorschlag: nicht jetzt.
