# Spec Delta

## MODIFIED Requirements

### Requirement: Eingebettete Web-Oberfläche

Der Daemon SHALL die statische Svelte-Oberfläche und die JSON-API im selben
Prozess ausliefern. Bind-Adresse und Port MUST konfigurierbar sein; die
Oberfläche MUST ohne Internetverbindung und ohne externe CDN-Ressourcen laden.
Änderungen an Bind-Adresse oder Port werden erst nach einem Dienstneustart
wirksam.

#### Scenario: Oberfläche lädt ohne Internet

- **WHEN** der Browser nur den Pi im LAN erreicht, aber keinen Internetzugang hat
- **THEN** laden HTML, JavaScript, Styles und Schriften vollständig aus lokalen Assets und die Oberfläche ist bedienbar

#### Scenario: Zugriff aus dem LAN

- **WHEN** ein Browser im selben LAN die konfigurierte Adresse und den Port aufruft
- **THEN** wird die Oberfläche ausgeliefert und die API antwortet

#### Scenario: Bind-Adresse geändert

- **WHEN** die Bind-Adresse in der Konfiguration geändert und angewendet wird
- **THEN** bleibt der laufende Listener unverändert; die Änderung wird erst nach einem Dienstneustart wirksam und ist in der README dokumentiert
