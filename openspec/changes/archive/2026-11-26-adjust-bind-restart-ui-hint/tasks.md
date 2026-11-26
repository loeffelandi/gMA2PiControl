# Tasks

## 1. Spec und Dokumentation

- [x] 1.1 Delta-Spec `config-ui` mit dem angepassten Szenario „Bind-Adresse geändert“ anlegen; `openspec validate adjust-bind-restart-ui-hint --strict` ist grün.
- [x] 1.2 `docs/acceptance-config-ui.md` auf den dokumentierten Neustart-Hinweis ohne UI-Meldung aktualisieren; `grep` findet weder „LAN-Port“ noch „Dienstneustart wirksam“ in `web/src` und `web/dist`.

## 2. Verifikation

- [x] 2.1 Frontend prüfen: `npm test`, `npm run check`, `npm run build` und `npm run check:offline` sind grün; die Seite **Erweitert** beginnt mit „PIN-Sperre“ und zeigt keinen LAN-Port-Hinweis.
- [x] 2.2 Live-UI auf dem Pi nach dem statischen Deployment prüfen: `/api/auth/status` antwortet, die Sperrseite funktioniert und der Hinweis fehlt im ausgelieferten JavaScript.

## Workflow follow-up

- Haupt-Spec `config-ui` beim Archivieren mit der Delta-Spec synchronisieren.
- Change nach bestandener Prüfung archivieren.
