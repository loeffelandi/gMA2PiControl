# 0018. Rettungs-WLAN als NetworkManager-Hotspot

* Datum: 2026-11-26
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

Related to [0017. Netzwerkkonfiguration über NetworkManager mit Bestätigung und Rollback](0017-netzwerkkonfiguration-ueber-networkmanager-mit-rollback.md)

## Kontext und Problemstellung

ADR-0017 sichert IP-Änderungen über Bestätigung und Rollback ab. Fällt das
kabelgebundene Netz trotzdem aus oder ist der Pi nach einem Rollback nur noch
auf der Notfall-Adresse `192.168.178.254` erreichbar, braucht der Benutzer einen
zweiten Zugangsweg zur Konfigurationsoberfläche. Ein separater Dienst oder
ein Zugang per SSH über WLAN wäre zusätzliche Infrastruktur beziehungsweise ist
im Notfall nicht bedienbar.

## Entscheidungstreiber

* Zugang zur Oberfläche, auch wenn das LAN ausfällt
* Keine neue Laufzeitabhängigkeit und kein zweiter Netzwerkdienst
* Bedienbar vom Handy oder Laptop ohne Konfiguration am Client
* Schutz durch WPA2 und die bestehende PIN-Sperre
* Kein Dauerbetrieb: der Hotspot soll nur bei Bedarf laufen

## Betrachtete Optionen

* Ad-hoc/IBSS-Netz ohne DHCP
* Hotspot über `hostapd` und `dnsmasq` als eigene Dienste
* NetworkManager-AP-Profil (`802-11-wireless.mode=ap`, `ipv4.method=shared`) auf `wlan0`
* Immer aktiver WLAN-Zugang neben dem LAN

## Entscheidung

Der Rettungszugang ist ein NetworkManager-AP-Profil `ma2pi-recovery` auf der
WLAN-Schnittstelle mit WPA2-PSK, Adresse `192.168.50.1/24` und dem internen
DHCP-Dienst von NetworkManager (`ipv4.method=shared`). SSID und Passwort sind in
der Oberfläche änderbar; das Standardpasswort ist `ma2pi-recovery`.

Der Hotspot ist standardmäßig aus. Er wird über die Oberfläche geschaltet oder
automatisch eingeschaltet, wenn das kabelgebundene Netz 60 Sekunden lang keine
nutzbare Adresse hat oder auf der Notfall-Adresse liegt. Er schaltet sich
wieder aus, wenn das Netz danach 60 Sekunden stabil ist. Der gewünschte Zustand
liegt in `/var/lib/ma2pi/recovery.json` und wird beim Dienststart wieder angewendet.

Das Aktivieren trennt eine bestehende WLAN-Verbindung auf `wlan0`. Das ist
beabsichtigt und wird in der Oberfläche erklärt.

Die Polkit-Regel erlaubt zusätzlich `org.freedesktop.NetworkManager.wifi.share.open`
und `org.freedesktop.NetworkManager.wifi.share.protected`. Mehr WLAN-Rechte
werden nicht vergeben.

### Konsequenzen

* Gut, weil ein Zugang zur Oberfläche auch bei LAN-Ausfall besteht.
* Gut, weil keine neue Software installiert werden muss; NetworkManager liefert AP und DHCP.
* Gut, weil der Hotspot standardmäßig aus ist und nur bei Bedarf läuft.
* Schlecht, weil das Aktivieren die bestehende WLAN-Verbindung trennt.
* Schlecht, weil das Standardpasswort öffentlich dokumentiert ist; es muss im Betrieb geändert werden.
* Schlecht, weil die WLAN-Freigabe in der Polkit-Regel die Angriffsfläche erweitert.
* Schlecht, weil die Automatik nur auf den Zustand des kabelgebundenen Netzes reagiert, nicht auf Dienstfehler.

### Bestätigung

Accepted, wenn auf dem Pi der Hotspot über die Oberfläche ein- und ausgeschaltet
werden kann, Clients per WPA2 eine Adresse aus `192.168.50.0/24` erhalten und
die Oberfläche unter `192.168.50.1` erreichbar ist. Zusätzlich muss die
Automatik bei einem echten LAN-Ausfall den Hotspot einschalten.

## Vor- und Nachteile der Optionen

### Ad-hoc/IBSS

* Gut, weil kein Access Point nötig wäre.
* Schlecht, weil ohne DHCP jeder Client manuell konfiguriert werden müsste.

### `hostapd` und `dnsmasq`

* Gut, weil die Konfiguration vollständig kontrollierbar wäre.
* Schlecht, weil zwei zusätzliche Dienste verwaltet und gegen NetworkManager abgegrenzt werden müssten.

### NetworkManager-AP-Profil

* Gut, weil es das vorhandene Netzwerk-Backend nutzt und Adressen selbst vergibt.
* Schlecht, weil `wlan0` für die Dauer des Betriebs nicht als Client verfügbar ist.

### Dauerhafter WLAN-Zugang

* Gut, weil der Zugang jederzeit verfügbar wäre.
* Schlecht, weil er die Angriffsfläche dauerhaft vergrößert.

## Weitere Informationen

* Change: `add-network-config-ui`, Capability `recovery-access`
* Umsetzung: `ma2pi/recovery.py`, `ma2pi/web/__init__.py` (`/api/recovery`)
