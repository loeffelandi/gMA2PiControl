# Tasks

Reihenfolge: **Teil B (Templates) vor Teil A (Dateien)**, siehe `design.md` R8.
Abnahmekriterium jeder Gruppe: `.venv/bin/python -m pytest -q` bleibt grün und der
Golden-Test auf `redacted_config()` (aus `modularize-backend-packages` Task 0.3)
bleibt unverändert.

## 0. Review-Gate (blockiert alles Weitere)

- [ ] 0.1 Review durch Andreas: Entscheidungen R1–R8 aus `design.md` bestätigen
  oder ändern (R9 ist entschieden: Option 1, ein Profil je Gerät) und je Punkt als „entschieden: …“ vermerken; den Entwurfs-Banner in
  `proposal.md` und `design.md` entfernen. Wird R1 = Option B gewählt, vorher
  `specs/` und diese Tasks anpassen (Gruppen 4 und 5 entfallen bzw. ändern sich).
  Verifikation: `openspec validate device-profile-files --strict` ist grün und
  kein Banner „Entwurf“ mehr in den Artefakten.
- [ ] 0.2 Prototyp zur Größenmessung (Wegwerf-Skript, nicht committet): die sechs
  MIDICRAFT-Profile samt Layout in die Syntax aus R6 überführen und gegen die
  ausgeschriebene Fassung vergleichen. Verifikation: Tabelle „Zeilen vorher/
  nachher je Profil“ ersetzt die Schätzung in `proposal.md`; kein Profil und
  kein Layout lässt sich nicht ausdrücken (sonst R6 anpassen).
- [ ] 0.3 Abhängigkeiten klären: `modularize-backend-packages` Phase 1
  (`ma2pi/config/`-Paket, Golden-Test) abgeschlossen; `fix-midicraft-led-output`
  und `add-per-device-led-protocols` (ändern `led_feedback`) abgeschlossen oder
  Rebase-Plan vermerkt. Verifikation: `openspec list` zeigt die Changes als
  abgeschlossen bzw. der Plan steht in `design.md`.

## 1. Teil B: Expansion der kompakten Deklaration

- [ ] 1.1 `bank_count` im Profil-Parser: Bänke 1..N mit Kanal = Nummer ohne Noten
  erzeugen, ausdrückliche Bänke je Nummer überschreiben, Nummer > N ablehnen;
  Bank-Regeln gelten nach der Expansion. Tests in `tests/test_config.py` zu den
  drei Szenarien des Specs (16 leere Bänke, Überschreiben, Bank über Anzahl)
  plus „gleich 16 ausgeschriebene Bänke“.
- [ ] 1.2 `control_groups` (`prefix`, `kind`, `count`, `label`, `label_start`):
  Controls `<prefix>_<i>` erzeugen, Label-Muster mit `{n}`; Gruppen und
  `controls` schließen sich aus; Expansion läuft **vor** der Encoder-ID-Vergabe
  für gebankte `relative-encoder`. Tests: Fader, fortlaufende Beschriftung,
  Mischung abgelehnt, doppelte Namen abgelehnt, zwei Profile gleicher Gruppen
  mit unterschiedlichem Präfix gültig, gleiches Präfix in zwei Profilen
  abgelehnt (beide Profile genannt), `relative-encoder`-Gruppe erhält IDs wie
  ausgeschriebene Controls.
- [ ] 1.3 Layout-Zellenmuster (`count`, `start`, Platzhalter `{n}`): Zellen
  erzeugen; nur `{n}` als Platzhalter (jede andere Klammer ist ein Fehler, kein
  `str.format`); Kombination mit `row`/`col`/`col_span`/`row_span` ablehnen;
  Control-Referenzen wie bisher prüfen. Tests in `tests/test_layouts.py` zu allen
  vier Szenarien des Specs.
- [ ] 1.4 Äquivalenztest `tests/test_profile_templates_equivalence.py`: Fixtures
  mit den sechs MIDICRAFT-Profilen kompakt vs. ausgeschrieben (Stand der
  aktuellen `config.toml`); `ProfileConfig`, `DeviceLayout` und
  `redacted_config()` müssen identisch sein. Verifikation: Test grün; Änderung
  einer Gruppenanzahl macht ihn rot.
- [ ] 1.5 Kompakte Schlüssel erscheinen nicht in der API: Test in
  `tests/test_config_api.py`, dass `GET /api/config` für ein kompaktes Profil
  weder `bank_count` noch `control_groups` enthält und die ausgeschriebene
  Struktur liefert.

## 2. Teil B: Schreib-Normalisierung

- [ ] 2.1 Kompaktierung des `banks`-Patches in `ConfigStore` (nur für Profile mit
  `bank_count`): Bänke, die dem Erzeugten entsprechen, werden nicht
  ausgeschrieben; alle anderen Schlüssel des Profils bleiben unangetastet,
  Profile ohne `bank_count` schreiben wie bisher alle Bänke. Unit-Tests auf
  Textebene: erste Belegung → genau eine ausdrückliche Bank und `bank_count`
  bleibt; Belegung löschen → Bank verschwindet; Kommentare in
  `control_groups` und Layout bleiben erhalten.
- [ ] 2.2 API-Tests in `tests/test_config_api.py`/`tests/test_runtime.py`: ein
  UI-förmiger Bank-Patch (alle 16 Bänke) gegen eine kompakte Konfiguration lässt
  die Datei kompakt und `GET /api/config` unverändert ausgeschrieben; ein Patch
  mit `controls` gegen ein Profil mit `control_groups` wird mit `422` und beiden
  Schlüsseln abgelehnt.

## 3. Teil A: Profildateien laden

- [ ] 3.1 `profiles_dir` im Schema: relativer Pfad, keine `..`-Segmente,
  aufgelöster Pfad im Konfigurationsverzeichnis, Symlinks hinaus abgelehnt;
  `AppConfig` erhält eine nicht serialisierte Zuordnung „Profil → Quelldatei“.
  Tests: ohne Schlüssel unverändert, absoluter Pfad, `..`, Symlink-Ausbruch.
- [ ] 3.2 Loader: `*.toml` sortiert einlesen, Profilname aus dem Dateinamen
  (Namensregel wie bisher), nur `[profile]` und `[layout]` zulassen, mit der
  Hauptdatei zusammenführen, Doppeldefinition mit beiden Fundstellen ablehnen,
  danach laufen die bestehenden Querverweis-Prüfungen unverändert. Fehlerpfade
  für Dateien mit `profiles.d/<datei>.toml:`-Präfix. Tests (`tmp_path`) zu allen
  Szenarien von „Eine Datei je Profil“, „Profilnamen sind eindeutig“ und „Fehler
  nennen die Datei“; ein Test, dass Fehlertexte der Hauptdatei unverändert sind.
- [ ] 3.3 `parse_config(raw, …)` bleibt ohne Dateisystemzugriff nutzbar
  (injizierbarer Reader für Profildateien), `load_config` nutzt das Dateisystem.
  Verifikation: alle bestehenden Config-Tests laufen unverändert; ein neuer
  Test lädt einen Dateisatz über den Reader ohne `tmp_path`.
- [ ] 3.4 `_clean_patch` verwirft `profiles_dir` aus API-Patches (analog
  `ma2.password_file`); `GET /api/config` gibt `profiles_dir` nicht preis.
  Test in `tests/test_config_api.py`: Patch mit `profiles_dir` ändert nichts und
  liefert keinen Fehlerhinweis auf den Dateisystempfad.
- [ ] 3.5 `--check-config` lädt den Dateisatz, nennt die Zahl der Profildateien
  und scheitert bei fehlendem Verzeichnis mit dessen Namen. Tests in
  `tests/test_cli.py` für Erfolg und Fehlerfall.

## 4. Teil A: Schreiben, Backup und Restore des Dateisatzes

- [ ] 4.1 `PreparedConfig` trägt eine Zuordnung `Pfad → Text`; `prepare_patch`
  leitet `profiles.<p>`/`layouts` für dateibasierte Profile in deren
  tomlkit-Dokument, alles Übrige in die Hauptdatei, validiert einmal über die
  zusammengeführte Sicht und prüft jeden erzeugten Text per `tomllib` gegen.
  Bestehende Tests, die `PreparedConfig.text` nutzen, werden auf die Zuordnung
  umgestellt (Assertions bleiben). Neue Tests zu den drei Szenarien von
  „Änderungen landen in der Datei des Profils“ (andere Dateien byte-identisch).
- [ ] 4.2 `commit_prepared`: Backup des vollständigen alten Satzes vor dem ersten
  Rename (R5), Rename-Reihenfolge Profildateien vor Hauptdatei, unveränderte
  Dateien werden nicht geschrieben, `last-good` als Satz, Rotation zählt Sätze.
  Tests zu „Backup eines Dateisatzes“, „Nur eine Datei betroffen“ und ein
  Fault-Injection-Test, der zwischen zwei Renames abbricht („Abbruch zwischen
  zwei Dateien“, „Ungültiger Zwischenstand beim Start“ mit Dateiname).
- [ ] 4.3 Backup-API und Restore: Liste liefert `kind: "set"|"file"` und die
  Summe der Größen; Backup-ID-Validierung für Verzeichnisnamen (Traversal-Tests
  bleiben grün, neue Fälle ergänzt); Restore eines Satzes ersetzt
  `config.toml` und das Profilverzeichnis nach Sicherung des aktuellen Satzes;
  Restore eines Einzeldatei-Backups aktiviert eine Konfiguration ohne
  `profiles_dir`. Tests in `tests/test_backups.py`/`tests/test_runtime.py` zu
  den drei Szenarien von „Backup und Wiederherstellung als Dateisatz“.
- [ ] 4.4 `ensure_layout`: Profilverzeichnis mit `0750`, Dateien `0640`, Owner
  `ma2pi` (wie `config.toml`). Test in `tests/test_config_store.py` mit
  injizierbarem Owner.
- [ ] 4.5 Backups-Seite verträgt Satz-Einträge: `BackupsPage.test.ts` um einen
  Eintrag mit `kind: "set"` ergänzen (nur Test, keine Änderung an der
  Komponente). Verifikation: `cd web && npm test -- --run BackupsPage`.

## 5. Teil A: Migration und Deploy

- [ ] 5.1 `--split-config` (D4): Backup, Zuordnung Layout → Profil über das
  Feld `profile`, Schreiben der Profildateien, `profiles_dir` setzen,
  Satz validieren, `redacted_config()` vor/nach vergleichen, Schreibreihenfolge
  R3; Layouts ohne Profil bleiben in der Hauptdatei; keine Kompaktierung. Tests
  zu den drei Szenarien von „Aufteilen einer bestehenden Konfiguration“
  (Aufteilen, zweiter Aufruf, Validierung schlägt fehl) gegen die
  mitgelieferte `config.toml`.
- [ ] 5.2 `deploy/install.sh`: mitgelieferte `profiles.d/*.toml` nur kopieren,
  wenn Verzeichnis bzw. Datei fehlt, nie überschreiben, Modi/Owner setzen;
  Hinweis auf Upgrade-Verhalten in der Ausgabe. Verifikation: `bash -n
  deploy/install.sh` und ein Lauf gegen temporäre Verzeichnisse (Variablen
  überschreibbar machen, falls nötig) mit zweimaligem Aufruf, der keine
  vorhandene Datei verändert.
- [ ] 5.3 Hardware-Smoke nur auf ausdrückliche Freigabe: auf dem Pi
  `--split-config`, `--check-config`, Dienst-Neustart, MIDICRAFT-Bank lernen und
  speichern (nur Profildatei ändert sich), Backup-Liste und Restore eines Satzes.
  Verifikation: Protokoll analog zu `docs/hardware-smoke-2026-11-26.log`.

## 6. Beispielkonfiguration, Dokumentation und Abnahme

- [ ] 6.1 Repository-`config.toml` auf die schlanke Form umstellen: `profiles_dir`
  und neun `profiles.d/*.toml`-Dateien (Cherry, ASL, sechs MIDICRAFT; Letztere
  kompakt per R6). Verifikation: Golden-Test auf `redacted_config()` bleibt
  **unverändert**; `wc -l config.toml profiles.d/*.toml` bestätigt die Größen
  aus Task 0.2.
- [ ] 6.2 Doku: neue ADR `docs/adr/<nächste freie Nummer>-…md` (derzeit 0026; 0025 ist vergeben; Nummer beim Anlegen per `ls docs/adr` prüfen; ergänzt ADR-0006 und ADR-0009;
  Entscheidungen R1–R9), Eintrag in `docs/adr/README.md`; `README.md` um
  Abschnitt „Geräteprofile“ (Dateiformat, `profiles_dir`, `--split-config`,
  kompakte Syntax, Upgrade-Verhalten, Rezept „zweites Gerät desselben Modells:
  Profildatei kopieren, Präfix und Bank-Belegung ändern“); `docs/api.md` um das Feld `kind` der
  Backup-Liste. Verifikation: im README dokumentierte Beispiele laufen durch
  `--check-config` (Test, der die Codeblöcke lädt).
- [ ] 6.3 Abschlussprüfung: `.venv/bin/python -m pytest -q`,
  `cd web && npm run check && npm test -- --run`, frisches venv
  `pip install .` und `python -m ma2pi --config config.toml --check-config`,
  `openspec validate device-profile-files --strict`. Verifikation: alle ohne
  Fehler.

## Workflow follow-up

- Change nach erfolgreichem Review der Umsetzung und Hardware-Smoke archivieren.
- Folge-Idee (nicht Teil dieses Changes): Geräteerkennung (`[devices.*]`) als
  Profil-Katalog mitliefern; Versionsnummer für mitgelieferte Profile.
