# Proposal

## Why

Die LAN-Adresse des Pi lässt sich heute nur über SSH und NetworkManager ändern.
Wer den Pi in ein bestehendes Netz integriert, muss Adresse, Subnetzmaske,
Gateway und DNS an der Konsole setzen. Ein Tippfehler oder eine falsche Maske
schneidet den einzigen Zugang ab, ohne dass die Oberfläche helfen kann.

Die vorhandene Weboberfläche verwaltet bereits MA2-Zugang, Geräte und Mapping.
Sie soll deshalb auch den kabelgebundenen Netzwerkzugang lesen, validieren und
kontrolliert umstellen können – inklusive DHCP/statisch und einer automatischen
Rückkehr zur alten Adresse, wenn die neue Konfiguration nicht erreichbar ist.

## What Changes

- Neue Seite **Netzwerk** in der Svelte-Oberfläche: aktueller Zustand,
  Umschalter **DHCP/Statisch**, Felder für IP, Subnetzmaske, Gateway und DNS.
- Netzwerkverwaltung über **NetworkManager** (D-Bus/`nmcli`), ausschließlich
  kabelgebundenes IPv4. Die Schnittstelle wird automatisch bestimmt; WLAN,
  IPv6, VLAN und mehrere verwaltete Interfaces sind nicht enthalten.
- Zwei-Phasen-Apply mit Bestätigungsfenster: Die neue Konfiguration wird
  zunächst nur temporär aktiviert. Meldet sich die Oberfläche nicht innerhalb
  von 180 Sekunden über die neue Adresse zurück, wird automatisch die vorherige
  Konfiguration wiederhergestellt. Ein Dienst- oder Pi-Neustart ist dafür nicht
  nötig.
- **Notfall-Adresse**: Schlägt auch die Wiederherstellung fehl, setzt der
  Daemon `192.168.178.254/24` ohne Gateway und DNS. Kurze
  Verbindungsunterbrechungen lösen keinen sofortigen Rollback aus.
- Vor dem Anwenden: strikte Validierung von IPv4-Adresse, Subnetzmaske,
  Gateway und DNS sowie die NetworkManager-Validierung; ungültige oder
  widersprüchliche Eingaben werden mit Feldbezug abgelehnt.
- Neue JSON-API: Netzwerkstatus lesen, Änderung prüfen, anwenden, bestätigen
  und zurückrollen. Schreibende Aufrufe bleiben durch PIN-Session, JSON-Pflicht
  und `X-Ma2pi-Request` geschützt.
- Persistenter Pending-Zustand unter `/var/lib/ma2pi/network-pending.json`:
  Ein Dienstneustart während des Bestätigungsfensters setzt den Rollback-Timer
  fort beziehungsweise rollt eine abgelaufene Änderung zurück.
- Deployment: eng begrenzte Polkit-Regel für den Benutzer `ma2pi`, Prüfung auf
  NetworkManager und `nmcli` im Installer, README- und API-Dokumentation.
- Neue ADR-0017 für die Entscheidung „NetworkManager, temporäre Aktivierung,
  Bestätigung und Rollback“.

Nicht enthalten: WLAN-Zugang, IPv6, mehrere gleichzeitig verwaltete
Schnittstellen, VLANs, Bonding, DHCP-Server, Hostname, Firewall-Regeln,
Internet-Exposition, Konflikt-Erkennung per ARP und das Setzen der IP über
`config.toml`.

## Capabilities

### New Capabilities

- `network-config`: Lesen, Validieren, Anwenden, Bestätigen und Zurückrollen der
  kabelgebundenen IPv4-Konfiguration des Pi über die Weboberfläche, inklusive
  DHCP/statisch, Subnetzmaske, Gateway, DNS und Schutz vor Aussperren.

### Modified Capabilities

Keine. Die bestehende Capability `config-ui` bleibt unverändert; die neue Seite
nutzt ihre Shell, PIN-Sperre und API-Konventionen, ändert aber keine ihrer
Anforderungen. `config.toml` enthält weiterhin keine Netzwerkadresse.

## Impact

- **Code:** neues Backend-Modul (z. B. `ma2pi/network.py`) mit
  NetworkManager-Adapter und Pending-/Rollback-Zustandsmaschine; neue Handler
  in `ma2pi/web/`; neue Seite `web/src/lib/NetworkPage.svelte` und
  API-Typen in `web/src/lib/api.ts`.
- **Abhängigkeiten:** NetworkManager und `nmcli` (Systempakete, bereits auf
  Raspberry Pi OS Trixie vorhanden); keine neue Python-Laufzeitabhängigkeit,
  wenn der Adapter `nmcli` mit festen Argumenten aufruft. Alternativ ein
  gekapselter D-Bus-Client.
- **System:** Polkit-Regel für `ma2pi`; `/var/lib/ma2pi/network-pending.json`
  (0600) als einziger neuer Schreibpfad. Die systemd-Härtung bleibt bestehen.
- **Sicherheit:** Netzwerkänderungen sind mindestens so sensibel wie die
  MA2-Zugangsdaten. Sie bleiben hinter PIN, JSON-Header und LAN-Bindung; die
  Polkit-Regel erlaubt nur die für NetworkManager nötigen Aktionen.
- **Bedienung:** Nach einer IP-Änderung ist die Oberfläche unter der neuen
  Adresse zu öffnen und die PIN erneut einzugeben; das erklärt die Oberfläche
  vor dem Anwenden. Ohne Bestätigung fällt der Pi nach 180 Sekunden auf die
  alte Adresse zurück.
- **Risiko:** Eine falsche, aber technisch gültige Adresse kann den Pi vom
  gewünschten Netz trennen. Deshalb Bestätigungsfenster, Auto-Rollback,
  Validierung und eine deutlich sichtbare Warnung vor dem Anwenden.
