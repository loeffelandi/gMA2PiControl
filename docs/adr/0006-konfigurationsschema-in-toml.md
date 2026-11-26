# 0006. Konfigurationsschema in TOML

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

Verifiziert 2026-11-26: strikte TOML-Validierung (`config.py`), `--check-config` grün, 219 Tests decken Fehlerfälle ab; Konfigurationsreferenz vollständig.

Amended by [0010. Hot Reload der Konfiguration](0010-hot-reload-der-konfiguration.md)

## Kontext und Problemstellung

Das Mapping von physischen Tasten und Encodern auf MA2-Hardkeys, Kommandos und
Wheels muss ohne Codeänderung anpassbar sein. Gleichzeitig sind Geräteprofile
für nicht standardisierte Hardware (ASL MK2 E4B3) und Geheimnisse für den Login
zu verwalten. Das Schema muss von Hand lesbar, strikt validierbar und
versionierbar sein.

## Entscheidungstreiber

* Lesbarkeit und Kommentierbarkeit durch Menschen
* Strikte Validierung mit klaren Fehlermeldungen
* Keine Geheimnisse im Repository
* Erweiterbarkeit für weitere Geräte und Ziele
* Keine zusätzliche Laufzeitabhängigkeit

## Betrachtete Optionen

* TOML mit `tomllib`
* YAML mit PyYAML
* JSON
* Python-Datei als Konfiguration
* Datenbank oder GUI

## Entscheidung

Es wird TOML mit `tomllib` aus der Standardbibliothek verwendet. Das Schema
beginnt mit `schema_version = 1` und wird strikt validiert: unbekannte
Schlüssel, falsche Typen, ungültige Bereiche und nicht auflösbare Referenzen
brechen den Start ab. Es gibt keine stillen Defaults für sicherheits- oder
protokollrelevante Werte.

Kernentscheidungen des Schemas:

* **Geräte und Profile sind getrennt.** `[devices.*]` beschreibt die Erkennung
  (Vendor-/Product-ID, Namensfilter), `[profiles.*]` beschreibt die Bedeutung
  der evdev-Controls. So kann ein neues Gerät ohne Änderung der Mapping-Logik
  ergänzt werden.
* **Logische Namen als Bindeglied.** Profile liefern logische Control-Namen
  (z. B. `fix`, `ma`, `enc_1`), `[mapping.*]` verweist darauf. Rohcodes stehen
  nur in Profilen.
* **Hardkeys symbolisch, IDs als Override.** Die Konfiguration nutzt Namen aus
  einem mitgelieferten Katalog (`Fix`, `Store`, `MA`, `Go +`, `0`, …). Ein
  numerischer Override ist möglich, falls eine onPC-Version abweicht.
* **Ziele sind eindeutig.** Ein Encoder hat entweder `wheel = 1..10` oder
  `attribute = "<Name>"`, nie beides.
* **Auflösung getrennt nach Zieltyp.** Wheel- und Attribut-Auflösungen haben
  eigene Normal/Fine/Ultra-Multiplikatoren, weil Wheels ganze Ticks erwarten.
* **Geheimnisse nur über Datei oder Umgebung.** Genau eine Quelle:
  `password_file` oder `password_env`; Klartextpasswörter im Config-File sind
  nicht erlaubt. Die Datei liegt außerhalb des Repositories mit Modus `0640`.
* **Kein Hot-Reload in v1.** Konfigurationsänderungen erfordern einen
  Service-Restart. Das vermeidet inkonsistente Zustände mitten in einer
  gehaltenen Tastenkombination.

### Konsequenzen

* Gut, weil das Schema ohne Zusatzpaket lesbar und strikt prüfbar ist.
* Gut, weil Geräteprofile und Mapping getrennt erweiterbar sind.
* Gut, weil keine Geheimnisse versehentlich eingecheckt werden.
* Schlecht, weil TOML keine `null`-Werte kennt und verschachtelte Arrays of Tables schnell unübersichtlich werden; das Schema muss eindeutig bleiben.
* Schlecht, weil jede Schemaänderung eine Versionserhöhung und Migrationshinweise braucht.
* Schlecht, weil ein Restart bei jeder Mapping-Änderung nötig ist.

### Bestätigung

Accepted, wenn die mitgelieferte Beispielkonfiguration alle geforderten Keys
abdeckt, `openspec validate --strict` und die Config-Validierung grün sind und
im Repository kein Geheimnis liegt.

## Vor- und Nachteile der Optionen

### TOML

* Gut, weil Standardbibliothek, lesbar und für flache bis mittlere Hierarchien ideal.
* Schlecht, weil komplexe verschachtelte Strukturen schnell unübersichtlich werden.

### YAML

* Gut, weil sehr flexibel.
* Schlecht, weil zusätzliche Abhängigkeit, implizite Typen und gefährliche Loader-Fallen.

### JSON

* Gut, weil eindeutig und maschinell gut verarbeitbar.
* Schlecht, weil keine Kommentare und für Handpflege ungeeignet.

### Python-Datei

* Gut, weil maximale Flexibilität.
* Schlecht, weil Konfiguration und Code verschwimmen und Validierung erschwert wird.

### Datenbank oder GUI

* Gut, weil komfortabel bei vielen Einträgen.
* Schlecht, weil für ein Einzelgerät übertrieben und schlecht versionierbar.

## Weitere Informationen

* Vollständiges Beispiel: `config.toml` im Repository
* Verwandt: ADR-0002, ADR-0004, ADR-0007
