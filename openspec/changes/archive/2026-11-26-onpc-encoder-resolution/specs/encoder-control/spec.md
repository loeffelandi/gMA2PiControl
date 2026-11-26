# Spec Delta

## MODIFIED Requirements

### Requirement: Attribut-Fenster folgt der onPC

Die Slot-Encoder SHALL die Hardware-Attribut-Encoder der onPC adressieren; die
onPC routet diese selbst auf das aktuell gewählte Feature und Attribut-Fenster.
Der Daemon MUST kein `presetTypes`-Dauer-Polling betreiben; er DARF das
Attribut-Modell nur beim Verbinden und kurz nach einem Auflösungswechsel lesen,
um Attributnamen und Auflösung zu bestimmen.

#### Scenario: onPC blättert weiter

- **WHEN** der Benutzer in der onPC von den Attributen 1–4 auf die Attribute 5–8 wechselt
- **THEN** senden die vier Encoder weiterhin ihre Hardware-Encoder-Indizes und die onPC legt sie auf die Attribute 5–8

#### Scenario: Weniger Attribute als Slots

- **WHEN** das aktuelle Feature nur zwei Attribute hat
- **THEN** bleiben die Hardware-Encoder 3 und 4 an der onPC ohne Wirkung; der Daemon sendet ihre Indizes weiter und die onPC ignoriert sie

#### Scenario: Feature-Wechsel

- **WHEN** der Benutzer in der onPC ein anderes Feature wählt
- **THEN** adressieren die Encoder ohne Zutun des Daemons das Fenster des neuen Features; es findet kein Dauer-Polling statt

### Requirement: Auflösung per Taste 2 und Encoder-Klick

Solange der lokale Modifier `asl_button_2` gehalten wird, SHALL ein Encoder-Klick
die Auflösung des Attributs des Slots in der onPC zyklisch umschalten (Normal →
Fine → Ultra → Normal) und keinen Encoder-Druck senden. Die Umschaltung MUST per
nativem `encoder`-Frame mit `name` und `resolution` erfolgen; der Daemon skaliert
Deltas nicht selbst. Für Screen-Encoder (Screen-Modus oder MA gehalten) MUST
nichts gesendet und eine Warnung protokolliert werden.

#### Scenario: Auflösung durchschalten

- **WHEN** `asl_button_2` gehalten und Encoder 1 dreimal geklickt wird
- **THEN** werden nacheinander `resolution` 1, 2 und 0 für das Attribut von Slot 1 gesendet, und kein Klick erzeugt einen Encoder-Druck-Frame

#### Scenario: Fine skaliert

- **WHEN** die onPC Fine für das Attribut meldet und der Slot gedreht wird
- **THEN** ändert sich der Wert pro Schritt entsprechend kleiner, ohne dass der Daemon die Schritte skaliert

#### Scenario: Klick ohne Taste 2

- **WHEN** `asl_button_2` nicht gehalten wird und ein Encoder geklickt wird
- **THEN** wird der Encoder-Druck an die onPC gesendet und die Auflösung ändert sich nicht
