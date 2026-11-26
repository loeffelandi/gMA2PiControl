# mapping-engine Specification

## Purpose

Übersetzt logische Tasteneingaben anhand der TOML-Konfiguration in
grandMA2-Hardkeys oder CMD-Sequenzen, verwaltet Modifier-Kombinationen mit
echter Press-/Release-Reihenfolge und verhindert hängende Tasten nach Abbrüchen.

## Requirements

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

Die Engine SHALL alle offenen Presses je Gerät und Control verfolgen und bei
Verbindungsverlust, Geräteverlust, Start eines Lernmodus, Konfigurationswechsel
oder Shutdown best effort freigeben. Nach Reconnect MUST kein alter Press
bleiben. Ein Release MUST nur den Press desselben Geräts beenden; beim Aufräumen
gehaltener lokaler Modifier MUST auch deren LED-Rückmeldung zurückgesetzt werden.

#### Scenario: Verbindungsverlust bei gehaltenen Tasten

- **WHEN** die WebSocket-Verbindung abbricht, während MA und Store gehalten sind
- **THEN** wird der lokale Zustand samt Modifier-Rückmeldung geleert, nach dem
  Reconnect wird kein veraltetes Release gesendet und die nächste Taste
  funktioniert normal

#### Scenario: Gerät wird im Betrieb entfernt

- **WHEN** das Keyboard gezogen wird, während eine Taste gehalten ist
- **THEN** gibt die Engine die zu diesem Gerät gehörenden Presses frei und
  protokolliert den Vorgang

#### Scenario: Release von einem anderen Gerät

- **WHEN** Gerät A einen Control hält und Gerät B, das ihn nicht hält, ein
  Release für denselben Control-Namen sendet
- **THEN** bleibt der Press von Gerät A bestehen und es wird kein Release-Frame
  gesendet

#### Scenario: Doppel-Press desselben Geräts

- **WHEN** dasselbe Gerät einen bereits gehaltenen Control erneut drückt
- **THEN** wird der zweite Press ignoriert wie bisher

#### Scenario: Einzelnes Gerät

- **WHEN** nur ein Gerät angeschlossen ist
- **THEN** verhalten sich Press und Release wie bisher

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

### Requirement: Bankabhängige Mapping-Auflösung

Die Engine SHALL jedes Ereignis anhand von Gerät, Bank und Control auflösen:
zuerst gegen die Bank-Ebene, danach gegen das globale Mapping. Gibt es in beiden
keinen Eintrag, MUST kein Frame gesendet werden. Die Bank stammt aus dem
MIDI-Kanal und der gelernten Notenzuordnung, nicht aus einem Gerätezustand.

#### Scenario: Treffer in der Bank-Ebene

- **WHEN** ein Ereignis aus Bank 2 eintrifft und die Bank-Ebene für dieses Control einen Eintrag hat
- **THEN** wird ausschließlich dieser Eintrag ausgeführt

#### Scenario: Fallback auf globales Mapping

- **WHEN** ein Ereignis eintrifft und die zugehörige Bank-Ebene das Control nicht nennt
- **THEN** wird das globale Mapping mit Bank-Offset ausgeführt

#### Scenario: Kein Eintrag

- **WHEN** weder Bank-Ebene noch globales Mapping das Control nennen
- **THEN** wird kein Frame gesendet und das Ereignis nur auf Debug-Level protokolliert

### Requirement: Bankbindung gehaltener Tasten

Beim Press MUST die Engine die Bank des Ereignisses festhalten. Das Release MUST
gegen dieselbe Bank aufgelöst werden, auch wenn das Gerät inzwischen auf eine
andere Bank umgeschaltet wurde. Das gilt auch für Modifier, die über einen
Bankwechsel hinweg gehalten werden.

#### Scenario: Release nutzt die Press-Bank

- **WHEN** ein Control in Bank 2 gedrückt und nach einem Wechsel auf Bank 3 losgelassen wird
- **THEN** wird das Release mit dem Ziel der Bank 2 gesendet

#### Scenario: Modifier über Bankwechsel

- **WHEN** ein Modifier in Bank 1 gehalten und in Bank 2 eine Taste gedrückt wird
- **THEN** bleibt der Modifier-Press bestehen und die Taste wird mit Bank 2 aufgelöst

#### Scenario: Kein automatisches Release

- **WHEN** das Gerät auf eine andere Bank umschaltet, während Tasten gehalten werden
- **THEN** erzeugt der Wechsel selbst keine Release-Frames

### Requirement: Bank-Offset bei der Auflösung

Fehlt ein Eintrag in der Bank-Ebene, SHALL die Engine das Executor-Ziel der Bank
1 verwenden und die Executor-Nummer um `(bank-1) * bank_size` erhöhen, sofern
für die Bank keine MA-Page hinterlegt ist. Nur Executor-Ziele dürfen verschoben
werden; Button-Nummern, Hardkeys, Commands und die MA-Page MUST unverändert
bleiben. Explizite Einträge der Bank-Ebene MUST ohne Offset gelten.

#### Scenario: Vererbter Fader in Bank 2

- **WHEN** Bank 1 den Fader auf Executor 1 legt, `bank_size` 5 ist und Bank 2 keinen Eintrag hat
- **THEN** sendet der Fader in Bank 2 einen Frame für Executor 6

#### Scenario: Explizites Ziel ohne Offset

- **WHEN** die Bank-Ebene für Bank 2 den Executor 20 nennt
- **THEN** wird Executor 20 gesendet und kein Offset addiert

#### Scenario: Hardkey bleibt unverändert

- **WHEN** ein Control in Bank 2 ein Hardkey-Mapping ohne Bank-Eintrag hat
- **THEN** wird derselbe Hardkey wie in Bank 1 gesendet

#### Scenario: MA-Page statt Offset

- **WHEN** für Bank 2 eine MA-Page hinterlegt ist
- **THEN** wird kein Bank-Offset angewendet

#### Scenario: Berechneter Executor wird ungültig

- **WHEN** der Bank-Offset eine Executor-Nummer kleiner als eins ergibt
- **THEN** wird kein Frame gesendet und der Fehler einmalig protokolliert

### Requirement: Gleiche Konsolen-Taste auf mehreren Geräten

Halten mehrere Geräte gleichzeitig Controls, die auf dieselbe Konsolen-Taste
oder denselben Encoder-Klick abgebildet sind, SHALL die Engine die Frames nach
der Konsolen-Taste ausgeben: Press beim ersten haltenden Gerät, Release erst,
wenn das letzte loslässt. Hold-Upgrade und Aufräumpfade MUST je Konsolen-Taste
höchstens einmal Frames erzeugen.

#### Scenario: Zwei Geräte halten dieselbe Taste

- **WHEN** Gerät A und Gerät B nacheinander Controls drücken, die beide auf
  `Go+` abgebildet sind
- **THEN** wird genau ein Press-Frame für `Go+` gesendet

#### Scenario: Erstes Gerät lässt los

- **WHEN** Gerät A loslässt, während Gerät B noch hält
- **THEN** wird kein Release-Frame gesendet und `Go+` bleibt auf der Konsole
  gehalten

#### Scenario: Letztes Gerät lässt los

- **WHEN** danach auch Gerät B loslässt
- **THEN** wird genau ein Release-Frame für `Go+` gesendet

#### Scenario: Geräteverlust bei geteilter Taste

- **WHEN** Gerät A und Gerät B dieselbe Konsolen-Taste halten und Gerät A
  entfernt wird
- **THEN** wird kein Release-Frame gesendet, solange Gerät B hält

#### Scenario: Apply bei geteilter Taste

- **WHEN** zwei Geräte dieselbe Konsolen-Taste halten und ein Apply läuft
- **THEN** wird für diese Taste genau ein Release-Frame gesendet und
  anschließend ist kein Press mehr offen

#### Scenario: Hold-Upgrade bei geteilter Taste

- **WHEN** der Lua-Transport aktiv ist und zwei Geräte dieselbe Taste halten,
  bis die Hold-Schwelle überschritten ist
- **THEN** wird das Hold-Upgrade höchstens einmal für diese Taste gesendet

### Requirement: Modifier wirken gerätübergreifend

Ein Modifier (Fine, Ultra, Auflösungs-Zyklus und die Screen-Encoder-Taste MA)
SHALL als gehalten gelten, solange mindestens ein Gerät ihn hält, unabhängig
davon, an welchem Gerät der Encoder gedreht oder geklickt wird. Die Rückmeldung
für lokale Modifier MUST beim ersten Halter „gedrückt“ und erst beim letzten
Halter „losgelassen“ melden.

#### Scenario: Modifier auf einem anderen Gerät

- **WHEN** der Fine- oder Auflösungs-Modifier auf Gerät A gehalten und ein
  Encoder auf Gerät B betätigt wird
- **THEN** wirkt der Modifier wie gewohnt auf den Encoder von Gerät B

#### Scenario: Rückmeldung bei zwei Haltern

- **WHEN** Gerät A und Gerät B denselben lokalen Modifier halten und Gerät A
  loslässt
- **THEN** meldet die Rückmeldung weiterhin „gedrückt“ und erst nach dem
  Loslassen von Gerät B „losgelassen“

### Requirement: Relative Encoder in gebankten MIDI-Profilen

Ein gebanktes MIDI-Profil (`[[profiles.<id>.controls]]` + `[[profiles.<id>.banks]]`)
SHALL Controls mit `kind = "relative-encoder"` enthalten dürfen, die über
`[mapping.encoders]` und bankabhängige Encoder-Ebenen auf Attribut-Slots oder
Attributnamen abgebildet werden können.

#### Scenario: Gebankter relativer Encoder sendet Schritte

- **WHEN** ein gebanktes MIDI-Profil einen `relative-encoder` definiert und auf
  Slot 1 abbildet
- **THEN** wird die Konfiguration akzeptiert und Drehbewegungen erzeugen
  entsprechende Encoder-Schritte für Slot 1

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
