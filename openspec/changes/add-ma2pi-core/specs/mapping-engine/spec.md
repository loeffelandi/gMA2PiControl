# Spec Delta

## Purpose

Übersetzt logische Tasteneingaben anhand der TOML-Konfiguration in
grandMA2-Hardkeys oder CMD-Sequenzen, verwaltet Modifier-Kombinationen mit
echter Press-/Release-Reihenfolge und verhindert hängende Tasten nach Abbrüchen.

## ADDED Requirements

### Requirement: Konfigurationsvalidierung

Die Mapping-Engine SHALL die TOML-Konfiguration beim Start vollständig laden
und validieren: Schema-Version, Typen, Wertebereiche sowie referenzierte
Geräteprofile, Hardkeys und Ziele. Bei ungültiger Konfiguration MUST der Start
mit einer Meldung abbrechen, die Datei, Schlüssel und Ursache nennt; es dürfen
keine Frames gesendet werden.

#### Scenario: Gültige Beispielkonfiguration

- **WHEN** die mitgelieferte `config.toml` geladen wird
- **THEN** startet die Engine ohne Warnungen und alle Beispiel-Mappings sind aktiv

#### Scenario: Unbekannter Schlüssel

- **WHEN** die Konfiguration einen unbekannten Schlüssel enthält
- **THEN** bricht der Start ab und die Meldung nennt Datei, Schlüsselpfad und den erwarteten Aufbau

#### Scenario: Ungültige Referenz

- **WHEN** ein Mapping auf ein nicht definiertes Geräteprofil oder einen unbekannten Hardkey verweist
- **THEN** bricht der Start ab, bevor irgendein Frame gesendet wird

### Requirement: Hardkey-Press und -Release

Jedes konfigurierte Key-Down SHALL genau einen Hardkey-Press-Frame mit einem
Press-Wert größer als `0.9` erzeugen, jedes Key-Up genau einen Release-Frame mit
einem Wert kleiner als `0.9`. Ein bereits gedrückter Key MUST keinen zweiten
Press erzeugen; ein Release ohne vorherigen Press MUST ignoriert werden.

#### Scenario: Kurzer Tastendruck

- **WHEN** die Fix-Taste gedrückt und wieder losgelassen wird
- **THEN** wird genau ein Press-Frame gefolgt von genau einem Release-Frame gesendet

#### Scenario: Taste wird gehalten

- **WHEN** die Store-Taste eine Sekunde lang gehalten wird
- **THEN** wird genau ein Press gesendet, währenddessen kein Repeat, und beim Loslassen genau ein Release

#### Scenario: Doppelter Press

- **WHEN** für eine bereits gedrückte Taste erneut ein Key-Down eintrifft
- **THEN** wird kein zweiter Press-Frame gesendet

#### Scenario: Release ohne Press

- **WHEN** ein Key-Up für eine Taste eintrifft, die lokal nicht als gedrückt gilt
- **THEN** wird kein Release-Frame gesendet

### Requirement: Modifier-Stack und Chords

Als Modifier konfigurierte Tasten SHALL beim Drücken sofort als Press gesendet
und bis zum Loslassen gehalten werden. Nachfolgende Key-Events MUST währenddessen
normal gesendet werden, sodass die onPC die Kombination sieht. Bei geordnetem
Abbau (Shutdown, Verbindungsverlust, Geräteverlust) MUST die Engine Releases in
umgekehrter Press-Reihenfolge senden.

#### Scenario: MA+Fix löst Desk Lock aus

- **WHEN** MA gedrückt gehalten und anschließend Fix gedrückt und losgelassen wird
- **THEN** lautet die Reihenfolge MA-Press, Fix-Press, Fix-Release und die onPC führt Desk Lock aus; MA bleibt bis zum Loslassen gehalten

#### Scenario: Zwei Modifier und eine Taste

- **WHEN** zwei Modifier gehalten und danach eine Zieltaste gedrückt wird
- **THEN** werden beide Modifier-Presses vor dem Ziel-Press gesendet und das Ziel-Release vor den Modifier-Releases

#### Scenario: Geordneter Abbau

- **WHEN** der Daemon bei gehaltenen Modifern beendet wird
- **THEN** werden die Releases in umgekehrter Press-Reihenfolge gesendet

### Requirement: Schutz vor hängenden Tasten

Die Engine SHALL alle offenen Presses verfolgen und bei Verbindungsverlust,
Geräteverlust oder Shutdown best effort freigeben. Nach einem Reconnect MUST kein
veralteter Press bestehen bleiben; der erste neue Tastendruck MUST wieder ein
vollständiges Press-/Release-Paar erzeugen.

#### Scenario: Verbindungsverlust bei gehaltenen Tasten

- **WHEN** die WebSocket-Verbindung abbricht, während MA und Store gehalten sind
- **THEN** wird der lokale Zustand geleert, nach dem Reconnect wird kein veraltetes Release gesendet und die nächste Taste funktioniert normal

#### Scenario: Gerät wird im Betrieb entfernt

- **WHEN** das Keyboard gezogen wird, während eine Taste gehalten ist
- **THEN** gibt die Engine die zu diesem Gerät gehörenden Presses frei und protokolliert den Vorgang

### Requirement: CMD-Sequenzen

Ein Key kann statt eines Hardkeys eine CMD-Sequenz auslösen. Key-Down SHALL genau
einen `command`-Frame mit dem konfigurierten String senden; Key-Up MUST keinen
weiteren Frame erzeugen. Der String MUST unverändert übernommen werden.

#### Scenario: Clear als Kommando

- **WHEN** eine mit `command = "Clear"` gemappte Taste gedrückt und losgelassen wird
- **THEN** wird genau ein `command`-Frame mit dem Inhalt `Clear` gesendet und beim Loslassen nichts

#### Scenario: Mehrteilige Sequenz

- **WHEN** eine Taste eine Sequenz mit Semikolon auslöst
- **THEN** wird die Sequenz als ein einziger `command`-Frame unverändert gesendet

### Requirement: Unmappte Eingaben

Nicht gemappte logische Controls SHALL ignoriert und auf Debug-Level
protokolliert werden; sie dürfen keine Frames erzeugen.

#### Scenario: Taste ohne Mapping

- **WHEN** eine Taste gedrückt wird, für die weder Hardkey noch Kommando konfiguriert ist
- **THEN** wird kein Frame gesendet und der Vorgang erscheint nur im Debug-Log
