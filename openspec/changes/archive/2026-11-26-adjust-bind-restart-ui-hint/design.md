# Design

## Context

Der UI-Hinweis „LAN-Port“ wurde entfernt. Die Haupt-Spec `config-ui` verlangt
im Szenario „Bind-Adresse geändert“ noch eine Meldung in der Oberfläche. Siehe
`proposal.md` für die Motivation.

## Goals / Non-Goals

**Goals:**

- Die Spec an das tatsächliche, bereits umgesetzte Verhalten angleichen.
- Die Abnahmematrix und die README-Dokumentation konsistent halten.

**Non-Goals:**

- Bind-Adresse oder Port in der Oberfläche editierbar machen.
- Das Laufzeitverhalten des Listeners ändern.
- Den bereits entfernten UI-Hinweis wieder einführen.

## Decisions

- Nur das betroffene Szenario wird geändert; die Anforderung und die übrigen
  Szenarien bleiben unverändert. Dadurch bleibt die Spec klein und die
  bestehenden Nachweise für lokale Assets und LAN-Zugriff gelten weiter.
- Die README bleibt die maßgebliche Stelle für den Hinweis, dass
  Bind-Adresse/Port-Änderungen erst nach einem Dienstneustart wirksam werden.
  Eine UI-Meldung ist dafür nicht mehr erforderlich.

## Risks / Trade-offs

- [Benutzer übersieht den nötigen Neustart] → README und Kommentar in
  `config.toml` nennen den Neustart weiterhin; das Laufzeitverhalten bleibt
  unverändert und sicher.
- [Spec und Implementierung laufen wieder auseinander] → Das Szenario
  beschreibt jetzt ausdrücklich den unveränderten Listener und die
  README-Dokumentation.
