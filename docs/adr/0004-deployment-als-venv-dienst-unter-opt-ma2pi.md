# 0004. Deployment als venv-Dienst unter /opt/ma2pi

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

Verifiziert 2026-11-26 (Tasks 6.1–6.3): `install.sh` zweimal auf Trixie fehlerfrei, venv unter `/opt/ma2pi/.venv`, systemd-Dienst `active`/`enabled`, udev-Regeln greifen, Geräte als `ma2pi` lesbar.

Amended by [0009. Konfigurationsspeicherung unter /var/lib/ma2pi](0009-konfigurationsspeicherung-unter-var-lib-ma2pi.md)

## Kontext und Problemstellung

Raspberry Pi OS Trixie (Debian 13) markiert das System-Python per PEP 668 als
„externally managed“. Ein `pip install` außerhalb einer venv ist damit blockiert.
Der Daemon braucht Zugriff auf `/dev/input/event*`, darf aber nicht als Root
laufen. Gleichzeitig soll er onPC-Neustarts und Geräte-Hotplug überleben.

## Entscheidungstreiber

* PEP-668-konforme Installation
* Kein Root-Betrieb, minimale Rechte
* Automatischer Neustart und Start nach Netzwerk
* Reproduzierbares, aktualisierbares Deployment
* Nachvollziehbare Logs ohne zusätzliche Log-Dateien

## Betrachtete Optionen

* System-Python mit `pip --break-system-packages`
* pipx
* venv unter `/opt/ma2pi/.venv` mit System-User und systemd
* Container (Docker/Podman)
* Root-Dienst mit direktem Gerätezugriff

## Entscheidung

Es wird ein venv unter `/opt/ma2pi/.venv` verwendet. Der Anwendungscode liegt
unter `/opt/ma2pi/app`, die Konfiguration unter `/etc/ma2pi/config.toml`, das
Passwort-Geheimnis unter `/etc/ma2pi/ma2pi.password` (Modus `0640`,
Eigentümer `root:ma2pi`). Ein System-User `ma2pi` ohne Login-Shell besitzt das
venv und den Code. udev-Regeln geben der Gruppe `ma2pi` Leserechte auf die
konfigurierten Event-Geräte. Die systemd-Unit startet direkt
`/opt/ma2pi/.venv/bin/python`, nicht `python3`.

Die Unit nutzt `Restart=always`, `After=network-online.target`,
`NoNewPrivileges=true`, `ProtectSystem=strict`, `ProtectHome=true`,
`PrivateTmp=true`, `PrivateDevices=false` (zwingend für `/dev/input`) und
`DeviceAllow=/dev/input/event* r`. Es gibt keine `ReadWritePaths`, weil der
Daemon ausschließlich in das Journal schreibt und `PYTHONDONTWRITEBYTECODE=1`
gesetzt ist. Optional kann das Passwort per `LoadCredential` bereitgestellt
werden.

### Konsequenzen

* Gut, weil PEP 668 eingehalten wird und System-Pakete unangetastet bleiben.
* Gut, weil der Dienst ohne Root und mit starkem systemd-Hardening läuft.
* Gut, weil Logs im Journal landen und keine zusätzlichen Schreibpfade nötig sind.
* Schlecht, weil Updates ein erneutes `pip install` im venv und einen Service-Restart erfordern.
* Schlecht, weil `PrivateDevices=false` ein bewusstes Zugeständnis an `/dev/input` ist.
* Schlecht, weil udev-Regeln und Gruppenmitgliedschaft bei der Installation gesetzt werden müssen.

### Bestätigung

Accepted, wenn eine frische Trixie-Installation den Dienst nach Reboot startet,
ein Gerät im laufenden Betrieb ein- und ausgesteckt werden kann und der Dienst
ohne Root-Rechte sowie ohne Schreibzugriff außerhalb des venv läuft.

## Vor- und Nachteile der Optionen

### System-Python mit `--break-system-packages`

* Gut, weil kein venv nötig wäre.
* Schlecht, weil PEP 668 umgangen und das System-Python beschädigt werden kann.
* Schlecht, weil Abhängigkeitskonflikte mit Debian-Paketen drohen.

### pipx

* Gut, weil isolierte Installationen verwaltet werden.
* Schlecht, weil pipx für CLI-Anwendungen gedacht ist und systemd-/udev-Integration zusätzlich gebaut werden müsste.

### venv unter /opt/ma2pi

* Gut, weil PEP-668-konform, isoliert und systemd-freundlich.
* Gut, weil der Interpreter-Pfad explizit und stabil ist.
* Schlecht, weil Update- und Backup-Prozess manuell dokumentiert werden müssen.

### Container

* Gut, weil reproduzierbar und isoliert.
* Schlecht, weil Geräte-Durchreichung, udev und Netzwerk-Hotplug zusätzliche Komplexität erzeugen.
* Schlecht, weil auf einem einzelnen Pi zusätzlicher Overhead ohne Nutzen entsteht.

### Root-Dienst

* Gut, weil Gerätezugriff sofort funktioniert.
* Schlecht, weil ein kompromittierter Dienst vollen Systemzugriff hätte.
* Schlecht, weil das Prinzip der minimalen Rechte verletzt wird.

## Weitere Informationen

* Verwandt: ADR-0003, ADR-0006
