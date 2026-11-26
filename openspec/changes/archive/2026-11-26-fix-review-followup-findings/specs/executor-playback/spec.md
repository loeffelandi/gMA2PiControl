# Spec Delta

## ADDED Requirements

### Requirement: Ungepaartes Loslassen erzeugt keinen Executor-Frame

Trifft für ein Playback-Button-Control ein Loslassen (`value < 0.5`) ein, ohne
dass dafür im `PlaybackRouter` ein aktiver Tastendruck vermerkt ist (etwa nach
Verbindungsverlust, Konfigurations-Cleanup oder Ende eines Lernmodus), MUST der
Router das Ereignis verwerfen, ohne einen `playbackButton`-Release-Frame oder
einen `Page`-Befehl zu senden.

#### Scenario: Physisches Loslassen nach Session-Reset

- **WHEN** eine gehaltene Playback-Taste durch Verbindungsverlust zurückgesetzt
  wurde und der Bediener sie nach dem Reconnect loslässt
- **THEN** sendet `ma2pi` keinen verwaisten Release-Frame an die neue Session
