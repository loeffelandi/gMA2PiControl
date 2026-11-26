# Spec Delta

## ADDED Requirements

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
