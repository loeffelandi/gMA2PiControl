# Spec Delta

## MODIFIED Requirements

### Requirement: Schutz vor hängenden Tasten

Die Engine SHALL alle offenen Presses je Gerät und Control verfolgen und bei
Verbindungsverlust, Geräteverlust oder Shutdown best effort freigeben. Nach einem
Reconnect MUST kein veralteter Press bestehen bleiben; der erste neue
Tastendruck MUST wieder ein vollständiges Press-/Release-Paar erzeugen. Ein
Release MUST nur den Press des Geräts beenden, das ihn ausgelöst hat; ein
Release desselben Control-Namens von einem anderen Gerät MUST NOT den Press
dieses Geräts beenden.

#### Scenario: Verbindungsverlust bei gehaltenen Tasten

- **WHEN** die WebSocket-Verbindung abbricht, während MA und Store gehalten sind
- **THEN** wird der lokale Zustand geleert, nach dem Reconnect wird kein veraltetes Release gesendet und die nächste Taste funktioniert normal

#### Scenario: Gerät wird im Betrieb entfernt

- **WHEN** das Keyboard gezogen wird, während eine Taste gehalten ist
- **THEN** gibt die Engine die zu diesem Gerät gehörenden Presses frei und protokolliert den Vorgang

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

## ADDED Requirements

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
davon, an welchem Gerät der Encoder gedreht wird. Die Rückmeldung für lokale
Modifier MUST beim ersten Halter „gedrückt“ und erst beim letzten Halter
„losgelassen“ melden.

#### Scenario: Modifier auf einem anderen Gerät

- **WHEN** der Fine-Modifier auf Gerät A gehalten wird und ein Encoder auf
  Gerät B gedreht wird
- **THEN** wirkt die feine Auflösung wie bisher auf den Encoder von Gerät B

#### Scenario: Rückmeldung bei zwei Haltern

- **WHEN** Gerät A und Gerät B denselben lokalen Modifier halten und Gerät A
  loslässt
- **THEN** meldet die Rückmeldung weiterhin „gedrückt“ und erst nach dem
  Loslassen von Gerät B „losgelassen“
