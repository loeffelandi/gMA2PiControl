# Spec Delta

## ADDED Requirements

### Requirement: Gerätezeilen auf der Statusseite

Die Statusseite SHALL jedes konfigurierte Gerät als Zeile mit Kennung,
Transport, VID:PID, Profil und Zustand darstellen. Die Darstellung MUST ohne
horizontales Scrollen umbrechen.

#### Scenario: Gerät mit allen Angaben

- **WHEN** ein Gerät konfiguriert und erkannt ist
- **THEN** zeigt die Zeile Kennung, Transport, VID:PID, Profil und „erkannt“

### Requirement: RX- und TX-Anzeigen

Jede Gerätezeile MUST zwei Aktivitätsanzeigen besitzen: RX für Daten vom Gerät
und TX für Daten zum Gerät. Die Anzeigen MUST auf einen Anstieg des jeweiligen
Zählers sichtbar reagieren und ohne Aktivität gedimmt bleiben. Die Bedeutung von
RX und TX MUST zusätzlich zur Farbe über eine Legende oder Beschriftung
erkennbar sein. Bei `prefers-reduced-motion: reduce` MUST die Reaktion ohne
Animation erfolgen.

#### Scenario: Eingabe lässt RX blinken

- **WHEN** ein Gerät ein Ereignis liefert
- **THEN** pulsiert die RX-Anzeige dieser Zeile kurz und die TX-Anzeige bleibt unverändert

#### Scenario: Ausgabe lässt TX blinken

- **WHEN** ein Wert erfolgreich an ein Gerät geschrieben wird
- **THEN** pulsiert die TX-Anzeige dieser Zeile kurz

#### Scenario: Keine Aktivität

- **WHEN** ein Gerät längere Zeit nichts sendet oder empfängt
- **THEN** bleiben beide Anzeigen gedimmt und es entsteht kein Dauerlicht

#### Scenario: TX ohne Ausgabepfad

- **WHEN** ein Gerät nie beschrieben wird
- **THEN** bleibt seine TX-Anzeige gedimmt, ohne als Fehler markiert zu werden

### Requirement: Terminal-Log auf der Statusseite

Die Statusseite SHALL unter den Geräten ein Terminal-Log der letzten
Aktivitätsereignisse anzeigen. Jede Zeile MUST Zeitstempel mit Millisekunden,
Richtungs-Badge, Gerätekennung und Kurztext enthalten. Das Log MUST die neuesten
Einträge unten anzeigen und bei neuen Einträgen ans Ende scrollen. Es MUST auf
100 Einträge begrenzt sein und bei leerem Zustand einen Hinweis anzeigen.
Einträge MUST über ihre Sequenznummer dedupliziert werden, damit Status-Resync
und Delta-Events sich nicht doppeln.

#### Scenario: Neues Ereignis erscheint im Log

- **WHEN** ein `activity`-Event neue Einträge liefert
- **THEN** erscheinen sie in chronologischer Reihenfolge am Ende des Logs

#### Scenario: Resync ersetzt den Log-Stand

- **WHEN** ein Status-Snapshot mit Log-Ring empfangen wird
- **THEN** entspricht der angezeigte Log-Stand diesem Ring ohne doppelte Sequenznummern

#### Scenario: Leeres Log

- **WHEN** seit dem Start keine Aktivität aufgetreten ist
- **THEN** zeigt das Terminal einen Hinweis statt einer leeren Fläche
