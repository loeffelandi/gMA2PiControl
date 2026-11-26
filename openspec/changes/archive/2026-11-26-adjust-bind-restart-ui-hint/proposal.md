# Proposal

## Why

Der Hinweis „LAN-Port“ wurde auf Wunsch aus der Seite **Erweitert** entfernt.
Die Haupt-Spec `config-ui` fordert im Szenario „Bind-Adresse geändert“ aber
weiterhin, dass die Oberfläche den erforderlichen Dienstneustart meldet. Damit
weichen Spec und implementiertes Verhalten voneinander ab.

## What Changes

- Das Szenario „Bind-Adresse geändert“ wird an das tatsächliche Verhalten
  angepasst: Der laufende Listener bleibt bis zum Dienstneustart unverändert,
  und die README dokumentiert den Neustart.
- Die Anforderung „Eingebettete Web-Oberfläche“ bleibt ansonsten unverändert:
  lokale Assets, LAN-Zugriff und konfigurierbare Bind-Adresse/Port gelten
  weiterhin.
- Keine UI-Änderung in diesem Change; der Hinweis wurde bereits entfernt.
- Die Abnahmematrix wird auf den dokumentierten Stand gebracht.

## Capabilities

### New Capabilities

Keine.

### Modified Capabilities

- `config-ui`: Das Szenario „Bind-Adresse geändert“ verlangt keinen
  UI-Hinweis mehr, sondern beschreibt das unveränderte Laufzeitverhalten und
  die README-Dokumentation.

## Impact

- `openspec/specs/config-ui/spec.md`
- `docs/acceptance-config-ui.md`
- Keine Änderung an API, Laufzeit oder Frontend-Code.
