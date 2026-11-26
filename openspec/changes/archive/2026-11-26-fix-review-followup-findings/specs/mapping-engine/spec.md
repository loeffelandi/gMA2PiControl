# Spec Delta

## ADDED Requirements

### Requirement: Reihenfolgeunabhängige Encoder-IDs für gebankte Relativ-Encoder

Die Konfigurationsprüfung SHALL automatische `encoder_id`-Werte für gebankte
`relative-encoder`-Controls erst vergeben, nachdem alle explizit deklarierten
Encoder-IDs sämtlicher Profile erfasst wurden. `GET /api/config` MUST eine
abweichende `encoder_id` auch bei `encoder.*`-Namen erhalten, und `GET /api/devices`
MUST `encoder_id` im Control-Inventar ausgeben sowie Geräteknoten nach denselben
Regeln wie `HidManager` und `MidiManager` zuordnen.

#### Scenario: Explizite Encoder-ID in späterem Profil kollidiert nicht

- **WHEN** ein gebanktes Profil mit automatischer `encoder_id` in der TOML vor
  einem Profil mit expliziter `id = 1` steht
- **THEN** erhält das gebankte Profil die nächste freie ID ohne Kollision
