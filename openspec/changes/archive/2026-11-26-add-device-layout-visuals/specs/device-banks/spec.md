# Spec Delta

## Purpose

Beschreibt Geräte-Bänke als vom Benutzer gewählte Mapping-Ebenen: Ein
Page-Wechsel am Gerät ändert MIDI-Kanal und Notenbelegung gemeinsam. Der Kanal
ordnet ein Ereignis seiner Bank zu, die Noten dem Control; zum Anlernen und
Mappen wird die Bank zusätzlich explizit in der Oberfläche ausgewählt.

## ADDED Requirements

### Requirement: Bank als Editorzustand

Ein MIDI-Geräteprofil SHALL bis zu 16 Bänke definieren. Die Oberfläche MUST eine
Bank zum Anlernen und Bearbeiten auswählen lassen; diese Auswahl MUST nur den
Editorzustand ändern und weder an das Gerät noch an die MA gesendet werden. Es
MUST keinen geräteweiten Zustand geben, der als aktive Bank angezeigt wird; die
zuletzt verarbeitete Bank darf ausschließlich für die optionale
MA-Page-Bindung gemerkt werden.

#### Scenario: Bank zum Bearbeiten wählen

- **WHEN** im Editor Bank 3 gewählt wird
- **THEN** zeigt die Fläche die Belegung der Bank 3 und speichert Änderungen in deren Ebene, ohne das Gerät oder die MA zu beeinflussen

#### Scenario: Kein automatischer Bankwechsel im Editor

- **WHEN** am Gerät die Page gewechselt wird
- **THEN** ändert sich die Editorauswahl nicht, bis der Benutzer sie selbst ändert

### Requirement: Bank besteht aus Kanal und Notenbelegung

Jede Bank MUST eine Nummer von 1 bis 16, einen MIDI-Kanal von 1 bis 16 sowie
ihre eigenen Noten tragen. Ohne Kanalangabe MUST der Kanal der Banknummer
entsprechen. Ein Page-Wechsel am Gerät MUST als Wechsel von Kanal und
Notenbelegung gemeinsam behandelt werden. Ein Profil ohne Bank-Definition MUST
wie eine einzelne Bank 1 auf Kanal 1 behandelt werden.

#### Scenario: Page-Wechsel ändert Kanal und Noten

- **WHEN** am MIDICRAFT von Bank 1 auf Bank 2 geschaltet wird
- **THEN** sendet das Gerät auf Kanal 2 mit der Notenbelegung von Bank 2

#### Scenario: Kanal ohne Angabe

- **WHEN** Bank 3 keinen Kanal nennt
- **THEN** verwendet sie Kanal 3

#### Scenario: Mehr als 16 Bänke

- **WHEN** ein Profil eine Bank mit Nummer 17 definiert
- **THEN** schlägt die Validierung mit der Banknummer fehl

### Requirement: Eindeutiger MIDI-Kanal je Bank

Die Kanäle MUST innerhalb eines Profils eindeutig sein, weil der Kanal die Bank
bestimmt. Dieselbe Note MAY in verschiedenen Bänken vorkommen, sofern die
Kanäle unterschiedlich sind. Innerhalb einer Bank MUST jede Note genau einem
Control zugeordnet sein.

#### Scenario: Gleiche Note in zwei Bänken

- **WHEN** Bank 1 Note 55 auf Kanal 1 und Bank 2 Note 55 auf Kanal 2 verwendet
- **THEN** ist die Belegung gültig und beide Ereignisse sind eindeutig zuordenbar

#### Scenario: Doppelter Kanal

- **WHEN** zwei Bänke denselben MIDI-Kanal verwenden
- **THEN** schlägt die Validierung mit Kanal und beiden Bänken fehl

#### Scenario: Doppelte Note in einer Bank

- **WHEN** zwei Controls derselben Bank dieselbe Note verwenden
- **THEN** schlägt die Validierung mit Bank, Note und beiden Controls fehl

### Requirement: Zuordnung über Kanal und Note

Der Daemon MUST ein eingehendes MIDI-Ereignis zuerst über den Kanal der Bank und
danach über die Note dem Control zuordnen. Eine unbekannte Kombination MUST
ignoriert und einmalig protokolliert werden.

#### Scenario: Ereignis aus Bank 2

- **WHEN** ein Ereignis auf Kanal 2 mit einer in Bank 2 gelernten Note eintrifft
- **THEN** wird es dem Control in Bank 2 zugeordnet und die Mapping-Ebene von Bank 2 verwendet

#### Scenario: Unbekannter Kanal

- **WHEN** ein Ereignis auf einem Kanal eintrifft, dem keine Bank zugeordnet ist
- **THEN** wird kein Ereignis erzeugt und der Kanal einmalig pro Gerät protokolliert

#### Scenario: Unbekannte Note im Kanal

- **WHEN** ein Ereignis auf einem bekannten Bank-Kanal mit einer nicht gelernten Note eintrifft
- **THEN** wird kein Ereignis erzeugt und die Note einmalig pro Gerät protokolliert

### Requirement: Mapping-Ebenen je Bank

Die Konfiguration SHALL je Gerät und Bank eine optionale Mapping-Ebene
definieren können, die Tasten-, Encoder- und Playback-Ziele überschreibt. Bei
der Auflösung MUST zuerst die Ebene der Bank gelten; existiert dort kein Eintrag
für das Control, MUST die Bank- beziehungsweise Global-Regel greifen.

#### Scenario: Bank-Ebene überschreibt globales Mapping

- **WHEN** ein Control in Bank 2 einen Eintrag in der Bank-Ebene hat und global ein anderer Eintrag existiert
- **THEN** wird bei einem Ereignis aus Bank 2 der Eintrag der Bank-Ebene ausgeführt

#### Scenario: Getrennte Ziele pro Bank

- **WHEN** derselbe Fader in Bank 1 und Bank 3 explizit unterschiedliche Executor-Ziele hat
- **THEN** steuert er je nach zugeordneter Bank das jeweilige Ziel

### Requirement: Bank-Offset als Default

Ohne expliziten Eintrag in der Bank-Ebene SHALL ein Executor-Ziel der Bank N aus
dem Ziel der Bank 1 abgeleitet werden, indem die Executor-Nummer um
`(N-1) * bank_size` erhöht wird. `bank_size` MUST pro Gerät konfigurierbar sein
und ist standardmäßig die Anzahl der Fader-Controls, ersatzweise die Anzahl der
Tasten-Controls. Die Button-Nummer und die MA-Page MUST unverändert bleiben.

#### Scenario: Fünf Fader, Bank 2

- **WHEN** `bank_size = 5` ist, Bank 1 den Fader auf Executor 1 legt und Bank 2 keinen Eintrag hat
- **THEN** steuert derselbe Fader in Bank 2 Executor 6

#### Scenario: Bank 3 mit Schrittweite 5

- **WHEN** `bank_size = 5` ist und Bank 3 keinen Eintrag hat
- **THEN** liegt der Fader auf Executor 11

#### Scenario: Expliziter Eintrag gewinnt

- **WHEN** Bank 2 für den Fader Executor 20 explizit nennt
- **THEN** wird Executor 20 ohne zusätzlichen Offset verwendet

#### Scenario: Button-Nummer bleibt

- **WHEN** ein Button in Bank 2 über den Bank-Offset auf einen anderen Executor zeigt
- **THEN** bleibt seine Button-Nummer unverändert

### Requirement: Optionale MA-Page-Bindung

Eine Bank MAY eine MA-Page referenzieren. Ist eine MA-Page hinterlegt, MUST der
Daemon beim ersten Ereignis einer Bank, die sich von der zuletzt verarbeiteten
Bank unterscheidet, einmalig `Page <n>` senden; für diese Bank MUST kein
Bank-Offset angewendet werden. Ein Fehlschlag MUST die Eingabeverarbeitung nicht
blockieren.

#### Scenario: Bank schaltet MA-Page

- **WHEN** ein Ereignis aus Bank 2 eintrifft und Bank 2 die MA-Page 4 hinterlegt hat
- **THEN** wird genau einmal `Page 4` gesendet und die Ziele gelten auf MA-Page 4 ohne Offset

#### Scenario: Kein erneutes Senden

- **WHEN** weitere Ereignisse derselben Bank eintreffen
- **THEN** wird der MA-Page-Befehl nicht erneut gesendet

#### Scenario: Bank ohne MA-Bindung

- **WHEN** eine Bank keine MA-Page hinterlegt hat
- **THEN** bleibt die MA-Page unverändert und der Bank-Offset greift

### Requirement: Validierung der Bank-Konfiguration

Beim Laden MUST jede Banknummer zwischen 1 und 16 und jeder Kanal zwischen 1 und
16 liegen; Banknummern und Kanäle MUST je Profil eindeutig sein. Jede
Mapping-Ebene MUST auf ein konfiguriertes Gerät und eine dort definierte Bank
verweisen; referenzierte Controls MUST im Profil vorkommen. `bank_size` MUST
größer oder gleich eins sein.

#### Scenario: Mapping-Ebene für unbekannte Bank

- **WHEN** eine Mapping-Ebene Bank 5 nennt, das Profil aber nur Bänke 1–4 definiert
- **THEN** schlägt die Validierung mit Gerät und Bank fehl

#### Scenario: Ungültige Bankgröße

- **WHEN** `bank_size = 0` konfiguriert ist
- **THEN** schlägt die Validierung mit Gerät und Wert fehl
