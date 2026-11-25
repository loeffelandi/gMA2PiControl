# Tasks

> Status: bewusst nur als Stub angelegt. Ziel ist, das Layout-Thema nicht zu
> verlieren; die Details werden vor der Umsetzung ausgearbeitet.

## 1. Schema und Validierung

- [ ] 1.1 `DeviceLayout`/`LayoutCell`-Dataclasses und `[layouts.*]`-Parser in `config.py` implementieren (`device`, `columns`, `rows`, `label`, `control`, `col_span`, `row_span`); Tests für gültige Layouts, unbekanntes Gerät und unbekanntes Control.
- [ ] 1.2 Layout-Validierung gegen die Controls des Geräteprofils inklusive Fehlermeldung mit Gerät, Reihe, Spalte und Control; Test für jede Fehlerart.

## 2. Mitgelieferte Layouts

- [ ] 2.1 Cherry G86-63400 aus dem aktuellen Tastaturfoto als `[layouts.cherry]` abbilden (Reihen, Spalten, Labels, Spannen für `Pause`, `Go+`, `Go-`, `Store`, `Please`); Test prüft Reihenzahl und Stichproben.
- [ ] 2.2 ASL MK2-E4B3 als `[layouts.asl]` abbilden (vier Encoder, vier Clicks, drei Tasten); Test prüft `encoder.1`–`encoder.4` und die Tasten-Controls.

## 3. API

- [ ] 3.1 Layout in `GET /api/devices` ausliefern (optional, `null` wenn nicht konfiguriert); Test mit und ohne Layout.
- [ ] 3.2 Layout-Blöcke in `GET /api/config` redigiert und editierbar bereitstellen; Test prüft Struktur und dass keine Secrets enthalten sind.

## 4. Frontend

- [ ] 4.1 `DeviceLayout`-Komponente (CSS Grid, Spannen, klickbare Zellen) mit Komponententest für Spannen und Control-Zuordnung.
- [ ] 4.2 Layout in die Geräte-/Mapping-Seite einbinden; Test prüft, dass ein Klick auf eine Zelle die passende Mapping-Zeile fokussiert.

## 5. Dokumentation

- [ ] 5.1 Layout-Schema in der README-Konfigurationsreferenz dokumentieren.
- [ ] 5.2 `openspec validate --strict` und vollständige Testsuite grün.
