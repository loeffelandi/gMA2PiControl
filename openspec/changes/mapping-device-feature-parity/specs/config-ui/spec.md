# Spec Delta

## ADDED Requirements

### Requirement: Gemeinsames Zuweisungsmodell

Mapping- und Geräte-Tab SHALL dieselben Zuweisungsobjekte bearbeiten und
dieselben Aktionen anbieten: Hardkey, Command, Screen-Modus, Screen-Auswahl,
Encoder-Klick, Playback-Ziel, Encoder-Ziel, Screen-Encoder und Modifier. Eine
Aktion mit demselben Control und demselben Scope MUST in beiden Tabs exakt
dieselbe Konfiguration erzeugen; tab-spezifische Schreibregeln MUST NOT
existieren.

#### Scenario: Hardkey in beiden Tabs

- **WHEN** derselbe Hardkey im Mapping-Tab und im Geräte-Tab demselben Control im globalen Scope zugewiesen wird
- **THEN** enthält die gespeicherte Konfiguration in beiden Fällen denselben Hardkey und keine zusätzlichen Felder

#### Scenario: Playback mit Beschleunigung

- **WHEN** ein absoluter Encoder in beiden Tabs dasselbe Fader-Ziel mit aktiver Beschleunigung erhält
- **THEN** stimmen Ziel, Art und `accelerated` in der gespeicherten Konfiguration überein

#### Scenario: Entfernen in beiden Tabs

- **WHEN** eine bestehende Belegung in einem der beiden Tabs entfernt wird
- **THEN** ist sie anschließend in beiden Tabs nicht mehr vorhanden

### Requirement: Scope und effektive Belegung

Jede Zuweisung SHALL einen expliziten Scope besitzen: `global` oder
`Gerät + Bank`. Die Oberfläche MUST die effektive Belegung eines Controls auf
der gewählten Bank anzeigen und ihre Herkunft kennzeichnen: expliziter
Bank-Eintrag, expliziter globaler Eintrag, geerbter globaler Eintrag, geerbt
mit Bank-Offset oder Default. Ein Scope-Wechsel MUST als eigene Entscheidung
erfolgen und darf eine geerbte Belegung nicht stillschweigend in einen
expliziten Eintrag umwandeln.

#### Scenario: Geerbter Executor mit Bank-Offset

- **WHEN** global Executor 1 auf Page 1 gemappt ist und im Geräte-Tab Bank 2 mit Bankgröße 5 gewählt wird
- **THEN** zeigt die Oberfläche Executor 6 als geerbtes Ziel mit Bank-Offset und nicht als expliziten Bank-Eintrag

#### Scenario: Expliziter Bank-Eintrag

- **WHEN** für Bank 2 ein eigener Executor gespeichert ist
- **THEN** wird dieser Eintrag als explizit für Bank 2 angezeigt und der globale Eintrag bleibt unverändert

#### Scenario: Global ändern

- **WHEN** im Mapping-Tab ein globales Playback-Ziel geändert wird
- **THEN** wirkt die Änderung auf alle Bänke ohne expliziten Override und wird im Geräte-Tab als geerbt angezeigt

#### Scenario: Scope-Wechsel

- **WHEN** der Benutzer eine geerbte Belegung bearbeitet und „nur diese Bank“ wählt
- **THEN** entsteht ein expliziter Bank-Eintrag; bei „global“ wird der globale Eintrag geändert

### Requirement: Belegung bearbeiten, überschreiben und entfernen

Der gemeinsame Zuweisungsdialog SHALL alle Aktionen anbieten und eine Belegung
ausdrücklich entfernen können. Beim Entfernen eines Bank-Eintrags MUST die
geerbte globale Belegung wieder sichtbar werden; beim Entfernen eines globalen
Eintrags MUST die Belegung in allen Bänken ohne Override verschwinden. Ungenutzte
Felder einer Aktion MUST beim Speichern auf `null` gesetzt werden, damit ein
Aktionswechsel keine widersprüchlichen Felder hinterlässt.

#### Scenario: Bank-Override entfernen

- **WHEN** ein expliziter Bank-Eintrag entfernt wird und ein globales Ziel existiert
- **THEN** zeigt die Bank anschließend wieder das geerbte globale Ziel

#### Scenario: Globalen Eintrag entfernen

- **WHEN** ein globaler Eintrag entfernt wird und einzelne Bänke Overrides besitzen
- **THEN** verschwindet die Belegung nur in den Bänken ohne Override; die Overrides bleiben erhalten

#### Scenario: Hardkey zu Command wechseln

- **WHEN** eine Taste von Hardkey auf Command umgestellt wird
- **THEN** enthält die gespeicherte Belegung nur noch das Command und kein Hardkey-Feld

#### Scenario: Button zu Fader wechseln

- **WHEN** ein Playback-Ziel von Button auf Fader umgestellt wird
- **THEN** wird die Button-Nummer nicht mitgespeichert und das Backend akzeptiert die Belegung

#### Scenario: Screen-Encoder leeren

- **WHEN** ein Encoder von Screen-Encoder auf Attribut umgestellt oder der Screen-Encoder entfernt wird
- **THEN** ist der zugehörige Screen-Encoder-Eintrag nicht mehr vorhanden und der Screen-Modus adressiert diesen Slot nicht mehr

#### Scenario: Modifier bearbeiten

- **WHEN** ein Modifier im Zuweisungsdialog auf Hardkey oder lokal umgestellt wird
- **THEN** enthält die Belegung genau eine der beiden Varianten und der Modifier ist in beiden Tabs sichtbar

### Requirement: Vollständiges Control-Inventar und Bankdaten

Beide Tabs SHALL ihre Control-Auswahl aus dem vollständigen Control-Inventar
eines Profils bilden, einschließlich Inventar, Noten, absoluten Werten,
Encodern und Bänken. Ein Control, das nur im Inventar oder nur in einer Bank
geführt wird, MUST in beiden Tabs auswählbar sein. Der Mapping-Tab MUST den
Bank-Scope anbieten; der Geräte-Tab MUST den globalen Scope anbieten.

#### Scenario: MIDICRAFT-Control im Mapping-Tab

- **WHEN** ein MIDICRAFT-Profil seine Fader nur über Inventar und Banknoten führt
- **THEN** erscheinen diese Fader im Mapping-Tab als auswählbare Controls

#### Scenario: Nur in einer Bank gebundenes Control

- **WHEN** ein Control ausschließlich in Bank 2 eine Note besitzt
- **THEN** ist es in beiden Tabs für Bank 2 auswählbar und zeigt dort seine Belegung

#### Scenario: Beschleunigung im Mapping-Tab

- **WHEN** ein Inventar-Encoder mit Fader-Ziel und `accelerated = true` konfiguriert ist
- **THEN** zeigt der Mapping-Tab dieselbe aktive Beschleunigungs-Checkbox wie der Geräte-Tab

### Requirement: Parität der Lernwege

Beide Tabs SHALL den jeweils passenden Lernweg anbieten: die Control-Erkennung
für logische Belegungen und das Noten-Anlernen für die physische Belegung einer
Bank. Der nicht zuständige Tab MUST auf den zuständigen Tab verweisen, wenn er
den Lernweg nicht selbst anbietet, und dessen Ergebnis und Status anzeigen. Ein
Timeout oder Abbruch MUST den Lernzustand in beiden Tabs zurücksetzen.

#### Scenario: Noten-Anlernen aus dem Mapping-Tab

- **WHEN** im Mapping-Tab für ein bankgebundenes MIDICRAFT-Control das Noten-Anlernen gestartet wird
- **THEN** wird die Sitzung für Gerät und Bank gestartet oder der Benutzer zum Geräte-Tab für genau diese Bank geführt

#### Scenario: Control-Erkennung aus dem Geräte-Tab

- **WHEN** im Geräte-Tab die logische Control-Erkennung gestartet wird
- **THEN** wird dieselbe Sitzung wie im Mapping-Tab verwendet und das erkannte Control in beiden Tabs angezeigt

#### Scenario: Timeout oder Abbruch

- **WHEN** eine Lern-Sitzung ohne Ergebnis endet oder abgebrochen wird
- **THEN** sind die Lern-Schaltflächen in beiden Tabs wieder bedienbar und es wurde keine Belegung gespeichert

#### Scenario: Nur eine Sitzung

- **WHEN** in einem Tab bereits eine Lern-Sitzung läuft
- **THEN** lehnt der andere Tab einen zweiten Start ab und zeigt die laufende Sitzung an

### Requirement: Gemeinsamer Zustand und Validierung

Beide Tabs SHALL denselben Konfigurationszustand verwenden. Eine in einem Tab
gespeicherte Änderung MUST im anderen Tab ohne vollständiges Neuladen sichtbar
sein. Validierungsfehler MUST am betroffenen Feld angezeigt werden. Ein
veralteter Entwurf MUST erkannt werden, bevor er eine neuere Konfiguration
überschreibt. Vorrangkonflikte zwischen Layer-Key, Playback und Modifier
MUST in beiden Tabs sichtbar sein.

#### Scenario: Änderung im anderen Tab sichtbar

- **WHEN** im Mapping-Tab eine Belegung gespeichert und anschließend zum Geräte-Tab gewechselt wird
- **THEN** zeigt der Geräte-Tab die neue Belegung ohne Seitenneuladen

#### Scenario: Feldfehler

- **WHEN** das Backend eine ungültige Page oder einen ungültigen Executor ablehnt
- **THEN** erscheint die Meldung am betroffenen Feld und die bisherige Konfiguration bleibt aktiv

#### Scenario: Veralteter Entwurf

- **WHEN** ein Tab einen Entwurf hält, während die Konfiguration an anderer Stelle weitergeschrieben wurde
- **THEN** meldet das Speichern den Konflikt und überschreibt die neuere Konfiguration nicht

#### Scenario: Vorrangkonflikt

- **WHEN** dasselbe Control gleichzeitig einen Layer-Key und ein Playback-Ziel besitzt
- **THEN** kennzeichnen beide Tabs den Vorrang des Layer-Keys gegenüber dem Playback-Ziel

### Requirement: Einheitliche Geräteauswahl

Beide Tabs SHALL dieselbe Menge an Geräten anbieten. Nicht erkannte Geräte
MUST in beiden Tabs ausgeblendet sein; ein erkanntes Gerät MUST in beiden Tabs
bearbeitbar sein. Die Auswahl eines Geräts oder einer Bank MUST beim Wechsel
des Tabs erhalten bleiben, sofern das Gerät weiterhin erkannt wird.

#### Scenario: Nicht erkanntes Gerät

- **WHEN** ein konfiguriertes Gerät nicht angeschlossen ist
- **THEN** erscheint es weder im Mapping- noch im Geräte-Tab als bearbeitbarer Eintrag

#### Scenario: Erkanntes Gerät

- **WHEN** ein Gerät erkannt wird
- **THEN** ist es in beiden Tabs mit denselben Controls und Bankdaten verfügbar

#### Scenario: Tab-Wechsel

- **WHEN** im Geräte-Tab ein Gerät und eine Bank gewählt sind und zum Mapping-Tab gewechselt wird
- **THEN** ist dieselbe Auswahl vorbelegt, sofern das Gerät weiterhin erkannt wird
