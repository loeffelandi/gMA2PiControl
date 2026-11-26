# Spec Delta

## ADDED Requirements

### Requirement: Zielangaben ausgehender onPC-Frames im Ereignis-Log

`describe_frame` SHALL für ausgehende Frames an die grandMA2 onPC die tatsächlich
verwendeten Protokollfelder (`pageIndex`, `execIndex`, `buttonId`, `name` sowie
`keyname` bei `hardkeyPress` und `hardkeyRelease`) auswerten und 0-basierte
Indizes für die Anzeige wieder 1-basiert (`current` bei `pageIndex == -1`)
formatieren, ohne Kommandotexte oder Geheimnisse aufzunehmen.

#### Scenario: Playback- und Hardkey-Frames zeigen ihr Ziel im Log

- **WHEN** ein `playbackButton`-Frame für Page `current`, Executor 3, Button 1
  oder ein `hardkeyPress` für `Go+` gesendet wird
- **THEN** enthält der Kurztext im Ereignis-Log `page current · executor 3 · button 1`
  beziehungsweise `Go+` statt nur der bloßen Frame-Art
