# 26. Pi ausschalten über Web-UI und Cherry-Kombination

* Datum: 2026-11-27
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Related to [9. Konfigurationsspeicherung unter /var/lib/ma2pi](0009-konfigurationsspeicherung-unter-var-lib-ma2pi.md)

Related to [17. Netzwerkkonfiguration über NetworkManager mit Bestätigung und Rollback](0017-netzwerkkonfiguration-ueber-networkmanager-mit-rollback.md)

## Kontext und Problemstellung

Der Pi hat keinen Ausschalter und wird durch Ziehen des Netzsteckers
ausgeschaltet. Dabei kann ein laufender Schreibvorgang das Dateisystem auf der
SD-Karte beschädigen. Der Betreiber will den Pi nicht jedes Mal per SSH
herunterfahren. Der Daemon selbst schreibt seine Konfiguration atomar
(ADR-0009), aber das Betriebssystem schreibt im Hintergrund weiter, vor allem das
systemd-Journal.

## Entscheidungstreiber

* Sauber ausschalten ohne SSH und ohne Zusatzhardware.
* Keine versehentliche Auslösung während einer Show.
* Ein Ausschalten darf nie einen Befehl auf der onPC ausführen.
* Der Dienst läuft als unprivilegierter Benutzer mit `ProtectSystem=strict`
  und `NoNewPrivileges`.
* Der Pi hat kein eigenes Display, die onPC ist die einzige Rückmeldung.

## Betrachtete Optionen

* Nur Stecker ziehen, SD-Schreibzugriffe verringern
* Knopf in der Web-Oberfläche
* Knopf in der Web-Oberfläche und Tastenkombination am Cherry
* GPIO-Taster oder USV-HAT

## Entscheidung

Knopf in der Web-Oberfläche und Tastenkombination am Cherry, dazu weniger
Schreibzugriffe (`Storage=volatile` für das Journal, `noatime`).

* Beide Wege laufen durch `PowerService.shutdown`, das nach 1,5 s
  `systemctl poweroff` ausführt. Die Berechtigung kommt aus einer
  polkit-Regel, die genau `org.freedesktop.login1.power-off` (und die
  Multiple-Sessions-Variante) für den Benutzer `ma2pi` erlaubt. Reboot, Halt
  und Suspend bleiben verboten.
* Web: `POST /api/power/shutdown` mit `{"confirm": true}`, hinter der PIN-Sperre
  und dem Request-Header. Die Oberfläche fragt vorher noch einmal nach.
* Cherry: `hold_controls` (MA + Off) gedrückt halten und dabei
  `confirm_control` (Please) `confirm_presses`-mal (2) drücken. Es gibt keine
  Zeitfenster: Loslassen einer Kombi-Taste, eine andere Taste, Learn-Modus oder
  ein Geräteverlust brechen ab. Das Halten selbst ist die Absicherung.
* Die Kombination liegt **vor** dem Mapping-Engine: Die zuletzt gedrückte
  Kombi-Taste wird zurückgehalten, solange die Kombination gehalten wird, und jede
  Bestätigungstaste wird verschluckt. So landet weder `Off` noch `Please` in der
  Kommandozeile der onPC. Bricht die Kombination vor dem ersten Please ab, wird die
  zurückgehaltene Taste als normaler Druck nachgereicht; nach einem Please wird
  sie verworfen.
* Jeder Schritt wird auf der onPC mit `Echo "…"` gemeldet
  (`console_notice`), denn der Pi hat kein Display.
* `--dry-run` führt nichts aus, damit Entwicklungsrechner nicht ausgehen.
* `install.sh` setzt `Storage=volatile` (64 MB) per Drop-in, stellt `noatime` für
  `/` sicher (mit Backup der fstab) und meldet nur, wenn `dphys-swapfile` aktiv ist.

### Konsequenzen

* Gut, weil der Pi ohne SSH sauber herunterfährt und das Journal nicht mehr
  dauernd auf die SD-Karte schreibt.
* Gut, weil die Tastenkombination keinen Befehl auf der onPC auslösen kann.
* Schlecht, weil das Journal nach einem Neustart oder Stromverlust fehlt und
  Fehler nach einem harten Ausfall schwerer zu finden sind.
* Schlecht, weil ohne PIN jeder im LAN den Pi ausschalten kann
  (`[power] enabled = false` oder PIN setzen).
* Schlecht, weil MA + Off nicht mehr unmittelbar als Tastenpaar an die onPC
  geht: Off kommt erst beim Loslassen an, und ein langes Halten von MA + Off
  wirkt auf der onPC nicht mehr als „gehalten“.
* Schlecht, weil `Echo` in der MA im Befehlsverlauf erscheint. Es lässt sich mit
  `console_notice = false` abschalten.

### Bestätigung

Auf dem Pi: `install.sh` ausführen, dann (1) im Web „Pi herunterfahren“ drücken
und prüfen, dass der Pi herunterfährt und nicht von `ma2pi` blockiert wird,
(2) MA + Off halten und dabei zweimal Please drücken und prüfen, dass die
System-Monitor-Meldungen erscheinen, der Pi herunterfährt und die onPC keinen
Befehl ausführt, (3) `journalctl --disk-usage` zeigt nur RAM-Nutzung. Danach
den Status auf Accepted setzen.

## Vor- und Nachteile der Optionen

### Nur Stecker ziehen, SD-Schreibzugriffe verringern

* Gut, weil nichts Neues nötig ist.
* Schlecht, weil ein Restrisiko bleibt, besonders beim Journal und ext4.

### Knopf in der Web-Oberfläche

* Gut, weil einfach und ohne Eingabegerät.
* Schlecht, weil man dafür ein Gerät mit Browser braucht, was an der Konsole
  oft fehlt.

### Knopf in der Web-Oberfläche und Tastenkombination am Cherry

* Gut, weil das Gerät am Platz schon da ist und die Kombination bewusst
  umständlich ist.
* Schlecht, weil die Eingabe vor dem Mapping gefiltert werden muss.

### GPIO-Taster oder USV-HAT

* Gut, weil es unabhängig von der Software funktioniert.
* Schlecht, weil Hardware und Verdrahtung nötig sind.

## Weitere Informationen

* Verwandt: ADR-0013 (LAN-Zugriffsmodell mit PIN), ADR-0017 (polkit-Regel
  für den Dienst)
* Code: `ma2pi/power.py`, `deploy/50-ma2pi-power.rules`,
  `deploy/journald-ma2pi.conf`
