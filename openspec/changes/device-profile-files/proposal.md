# Proposal

> **Status: Entwurf – Review durch Andreas erforderlich, bevor `/opsx-apply`
> gestartet wird.** Die offenen Entscheidungen stehen in `design.md`
> (Abschnitt „Review-Entscheidungen“) und werden in Gruppe 0 von `tasks.md`
> als Gate abgehakt. Vorher darf kein Code angefasst werden.

## Why

`config.toml` hat 2617 Zeilen / 65 KB. Gemessen entfallen davon **2000 Zeilen
(76 %) auf Geräteprofile und Layouts** – allein die sechs MIDICRAFT-Modelle
samt Layout machen 1647 Zeilen (63 %) aus. Die eigentliche Betriebskonfiguration
(`ma2`, `mapping`, `devices`, `hardkeys`, Hilfsdienste) ist ~620 Zeilen groß.

Zwei Probleme überlagern sich:

- **Organisation**: Hardware-Beschreibungen (Control-Inventar, Layout, Bank-
  Schema eines Geräts) liegen in derselben Datei wie die Show-spezifische
  Konfiguration. Wer ein Gerät hinzufügt oder anpasst, scrollt durch 2000
  Zeilen fremde Geräte; Diffs und Backups mischen beides.
- **Redundanz**: Die sechs MIDICRAFT-Profile unterscheiden sich nur in Präfix
  und Control-Gruppen. Jedes Profil enthält 25–30 fast gleiche `[[controls]]`-
  Tabellen (5 Zeilen je Control) und 16 Bank-Tabellen, von denen 15 leer sind
  (`notes = {}`, Kanal = Nummer); die Layouts wiederholen das Raster mit
  denselben Labels.

Jedes Profil besitzt bereits einen natürlichen Schlüssel (`layouts` sind nach
Profil benannt, `devices.<name>.profile` verweist darauf). Das legt eine Datei
je Profil nahe. Zusätzlich lässt sich die Redundanz durch eine kompakte
Deklaration beseitigen, ohne dass Laufzeit, API oder UI davon etwas merken.

## What Changes

**Teil A – Eine Datei je Geräteprofil**

- Optionaler Schlüssel `profiles_dir` in `config.toml` (relativ zum
  Konfigurationsverzeichnis). Jede `<profilname>.toml` darin definiert genau
  ein Profil samt optionalem Layout. Ohne den Schlüssel bleibt alles wie heute;
  eine monolithische `config.toml` bleibt gültig, Mischbetrieb ist erlaubt,
  Doppeldefinitionen sind ein Fehler.
- `ConfigStore` schreibt Änderungen an einem Profil (typisch: gelernte
  Bank-Belegung) in die Datei **dieses** Profils, alles andere nach
  `config.toml`; Kommentare bleiben erhalten.
- Backups und Restore arbeiten auf dem **Dateisatz**; alte Einzeldatei-Backups
  bleiben wiederherstellbar.
- Migrationsbefehl `python -m ma2pi --split-config` teilt eine bestehende
  `config.toml` idempotent, mit Backup und Validierung auf.
- Fehlermeldungen nennen die betroffene Datei; `--check-config` prüft den
  gesamten Satz; `profiles_dir` ist per API nicht änderbar (kein Datei-Orakel).

**Teil B – Kompakte Profil-Deklaration („Templates“), unabhängig von Teil A**

- `bank_count` statt 16 ausgeschriebener Bank-Tabellen (Kanal = Nummer, leer);
  explizite Bänke überschreiben je Nummer.
- `control_groups` (Präfix, Art, Anzahl, Label-Muster) statt einzelner Controls.
- Layout-Zellen als Muster (`count`, Platzhalter `{n}`), mischbar mit
  ausgeschriebenen Zellen in derselben Reihe.
- Alles wird beim Laden zu denselben Datenstrukturen **expandiert**:
  `GET /api/config`, UI und Laufzeit sehen unverändert die ausgeschriebene Form.
  Beim Schreiben bleibt die kompakte Form erhalten.

Erwartete Größe nach A+B (Schätzung, per Prototyp in Task 0.2 zu bestätigen):
`config.toml` ≈ 600 Zeilen, je MIDICRAFT-Datei 30–60 Zeilen statt 200–300.

- **Keine BREAKING Changes**: bestehende Konfigurationen laufen unverändert;
  die Aufteilung ist ein bewusst ausgelöster Schritt.

## Capabilities

### New Capabilities

- `device-profile-files`: Profile und Layouts als Dateien je Profil laden,
  schreiben, sichern, migrieren und prüfen; Verhältnis zur monolithischen
  Konfiguration.
- `profile-templates`: kompakte Deklaration von Bänken, Control-Gruppen und
  Layout-Zellen mit identischer Expansion und erhaltenem Schreibformat.

### Modified Capabilities

- `runtime-config`: zusätzliche Anforderungen an Schreibreihenfolge,
  Wiederanlauf und Backup/Restore, wenn die Konfiguration aus mehreren Dateien
  besteht (bestehende Anforderungen bleiben unverändert).

## Impact

- **Backend**: `ma2pi/config*` (Loader für Profildateien, Expansion;
  voraussetzungsgemäß nach dem Paket-Umbau aus `modularize-backend-packages`),
  `ma2pi/config_store.py` (Dateisatz, Schreibrouting, Bundle-Backups),
  `ma2pi/runtime.py` (`_clean_patch`: `profiles_dir` verwerfen; Restore),
  `ma2pi/web/serialize.py` (unverändert erwartet, durch Golden-Test gesichert),
  `ma2pi/__main__.py` (`--split-config`, `--check-config`).
- **Deploy**: `deploy/install.sh` (Beispieldateien kopieren, nie überschreiben;
  Verzeichnis-Modi `0750`/`0640`), `docs/api.md`, `README.md`, neue ADR
  (ergänzt ADR-0006 und ADR-0009).
- **Repository**: `config.toml` wird zur schlanken Beispielkonfiguration, neue
  `profiles.d/*.toml` als mitgelieferte Geräteprofile.
- **Nicht betroffen**: Frontend (liest nur die kanonische API), `[devices.*]`
  (USB-IDs bleiben in `config.toml`), Mapping-Schema.
- **Abhängigkeiten zu anderen Changes**: baut auf `modularize-backend-packages`
  Phase 1 auf (Loader liegt in `config/loader.py`). `add-per-device-led-protocols`
  und `fix-midicraft-led-output` ändern `led_feedback` im Profil; sie sollten vor
  dem Umbau abgeschlossen oder danach rebased werden.
