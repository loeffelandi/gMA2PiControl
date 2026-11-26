# 0017. Netzwerkkonfiguration über NetworkManager mit Bestätigung und Rollback

* Datum: 2026-11-26
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

## Kontext und Problemstellung

Die IP-Adresse des Pi musste bisher über SSH und NetworkManager geändert werden.
Die Weboberfläche verwaltet bereits MA2-Zugang, Geräte und Mapping; sie soll auch
die kabelgebundene IPv4-Konfiguration lesen und ändern können. Eine falsche,
aber technisch gültige Adresse kann den einzigen Zugang zum Pi abschneiden.
Der Daemon läuft als unprivilegierter Benutzer `ma2pi` mit
`ProtectSystem=strict` und `NoNewPrivileges=true`.

## Entscheidungstreiber

* Bedienung ohne SSH und ohne Dienstneustart
* DHCP und statische Adresse inklusive Subnetzmaske, Gateway und DNS
* Schutz vor Aussperren, auch über einen Dienstneustart hinweg
* Kein root-Daemon und kein zusätzlicher privilegierter Dienst
* Nachvollziehbare, testbare Zustandsübergänge
* Nur eine kabelgebundene IPv4-Schnittstelle in v1

## Betrachtete Optionen

* IP direkt in Distribution-Dateien schreiben (`/etc/network/interfaces`, dhcpcd)
* `systemd-networkd`-Dateien schreiben und neu laden
* NetworkManager über D-Bus oder `nmcli`
* Ein root-Helper oder `sudo`-Regel für Netzwerkbefehle
* Keine Netzwerkverwaltung im UI

## Entscheidung

NetworkManager bleibt die einzige Quelle der Wahrheit. Der Daemon ruft
`/usr/bin/nmcli` mit festen Argumenten über `asyncio.create_subprocess_exec`
auf; es gibt keine Shell und keine vom Benutzer beeinflussbaren Argumente.
Verwaltet wird genau eine kabelgebundene IPv4-Schnittstelle.

Das Anwenden ist zweiphasig:

1. Kandidat validieren und als Pending-Zustand atomar unter
   `/var/lib/ma2pi/network-pending.json` speichern.
2. IPv4-Eigenschaften des Profils mit `nmcli connection modify --temporary`
   ändern und das Profil aktivieren; die HTTP-Antwort `202` geht vorher raus.
3. Nach erfolgreicher Aktivierung 180 Sekunden auf eine Bestätigung warten.
4. Bei Bestätigung das Profil dauerhaft schreiben; sonst die vorherigen rohen
   IPv4-Eigenschaften wiederherstellen und erneut aktivieren.
5. Beim Dienststart wird eine unterbrochene Phase zurückgerollt, ein noch
   gültiges Bestätigungsfenster fortgesetzt und ein abgelaufenes Fenster
   zurückgerollt.
6. Schlägt die Wiederherstellung fehl, wird die Notfall-Adresse
   `192.168.178.254/24` ohne Gateway und DNS gesetzt. Kurze
   Verbindungsabbrüche lösen keinen sofortigen Rollback aus; Auslöser ist nur
   das erfolglose Bestätigungsfenster oder ein fehlgeschlagener Rollback.

Der Benutzer `ma2pi` erhält eine eng begrenzte Polkit-Regel für
`org.freedesktop.NetworkManager.settings.modify.system` und
`org.freedesktop.NetworkManager.network-control`. Die systemd-Härtung bleibt
unverändert; `AF_UNIX` ist für den System-Bus bereits erlaubt.

### Konsequenzen

* Gut, weil die Netzwerkkonfiguration ohne Dienstneustart und ohne SSH änderbar ist.
* Gut, weil die temporäre Aktivierung und der automatische Rollback Aussperrungen begrenzen.
* Gut, weil NetworkManager DHCP, Lease-Erneuerung und Link-Erkennung selbst übernimmt.
* Gut, weil der Daemon unprivilegiert bleibt und keine neue Python-Abhängigkeit nötig ist.
* Schlecht, weil `nmcli`-Ausgaben textuell geparst werden und sich zwischen Versionen ändern können.
* Schlecht, weil die Polkit-Regel dem Benutzer `ma2pi` NetworkManager-Änderungen für alle Profile erlaubt; die Einschränkung auf eine Schnittstelle liegt im Daemon.
* Schlecht, weil die Oberfläche nach einem Adresswechsel neu geladen und die PIN erneut eingegeben werden muss.
* Schlecht, weil ein ARP-Konflikt mit einem anderen Host nicht erkannt wird.
* Schlecht, weil die Notfall-Adresse nur im Subnetz `192.168.178.0/24` ohne Client-Umkonfiguration erreichbar ist.
* Gut, weil kein Dienst- oder Pi-Neustart für eine IP-Änderung nötig ist.

### Bestätigung

Accepted, wenn auf einem Trixie-Pi ein Wechsel DHCP → statisch → DHCP gelingt,
die neue Adresse nach erneuter PIN-Eingabe bestätigt werden kann, ein nicht
bestätigter Wechsel nach 180 Sekunden zur alten Adresse zurückkehrt und ein
Dienstneustart im Bestätigungsfenster den Rollback korrekt fortsetzt.

## Vor- und Nachteile der Optionen

### Distributionsdateien direkt schreiben

* Gut, weil keine NetworkManager-Abhängigkeit bestünde.
* Schlecht, weil das Format je nach Distribution variiert und der Daemon Schreibrechte unter `/etc` bräuchte.

### `systemd-networkd`

* Gut, weil systemd bereits vorhanden ist.
* Schlecht, weil Raspberry Pi OS Trixie standardmäßig NetworkManager verwendet und ein zweiter Netzwerkdienst Konflikte erzeugt.

### NetworkManager über `nmcli`

* Gut, weil das vorhandene Systemwerkzeug DHCP, Profile und Aktivierung übernimmt.
* Gut, weil `--temporary` eine Aktivierung ohne sofortige dauerhafte Änderung erlaubt.
* Schlecht, weil die Ausgabe geparst werden muss und die Berechtigung über Polkit geregelt werden muss.

### Direkter D-Bus-Client

* Gut, weil strukturierte Antworten und `Update2`-Flags verfügbar wären.
* Schlecht, weil eine zusätzliche Python-Abhängigkeit und mehr Code nötig wären.

### Root-Helper oder `sudo`

* Gut, weil die Berechtigung eng auf ein Kommando begrenzt werden könnte.
* Schlecht, weil ein zusätzlicher privilegierter Dienst oder eine sudo-Regel die Angriffsfläche vergrößert und `NoNewPrivileges` umgangen werden müsste.

## Weitere Informationen

* Verwandt: ADR-0004 (Deployment), ADR-0008 (Web-UI), ADR-0013 (PIN-Zugriff)
* Change: `add-network-config-ui`
