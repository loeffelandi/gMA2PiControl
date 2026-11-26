# Design

## Context

Siehe `proposal.md` für Motivation und Scope. Die vorhandene Weboberfläche läuft
im Daemon-Prozess, ist per PIN geschützt und schreibt ihre Konfiguration über
`ConfigStore` nach `/var/lib/ma2pi/config.toml` (ADR-0008, 0009, 0010, 0013).
Der Dienst läuft als `ma2pi` mit `ProtectSystem=strict`,
`NoNewPrivileges=true` und `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`.

Die Netzwerkkonfiguration gehört nicht in `config.toml`: Sie wird vom
Betriebssystem verwaltet und muss auch dann gelten, wenn der Daemon nicht läuft.
Der Pi verwendet Raspberry Pi OS Trixie mit NetworkManager. Verwaltet wird genau
eine kabelgebundene IPv4-Schnittstelle; die IP-Änderung kann die laufende
HTTP-Verbindung der Oberfläche trennen.

## Goals / Non-Goals

**Goals:**

* Netzwerkstatus und Änderungen ohne SSH, ohne root-Daemon und ohne Neustart.
* DHCP/statisch inklusive IP, Subnetzmaske, Gateway und DNS.
* Strikte Validierung vor der Aktivierung.
* Aussperrschutz durch temporäre Aktivierung, Bestätigungsfenster und
  automatischen Rollback, auch über einen Dienstneustart hinweg.
* Klare Fehlerzustände und eine Oberfläche, die den Unterschied zwischen
  wirksamer, wartender und zurückgerollter Konfiguration zeigt.
* Testbarkeit ohne echten NetworkManager durch einen austauschbaren Adapter.

**Non-Goals:**

* WLAN, IPv6, VLAN, Bonding, Brücken, mehrere gleichzeitig verwaltete
  Schnittstellen, DHCP-Server oder DNS-Server.
* Änderung von Hostname, Firewall, Routing-Regeln oder Proxy-Einstellungen.
* Erkennung von IP-Konflikten per ARP-Scan; nur die lokale Belegung wird geprüft.
* Netzwerkkonfiguration in `config.toml` oder im Hot-Reload-Pfad.
* Ein root-Helper, `sudo` oder ein zweiter Dienst.

## Decisions

### NetworkManager über `nmcli` statt eigenem D-Bus-Client

Der Daemon ruft `/usr/bin/nmcli` mit festen Argumenten über
`asyncio.create_subprocess_exec` auf (keine Shell, `LC_ALL=C`, festes Timeout).
NetworkManager bleibt die einzige Quelle der Wahrheit. `nmcli --temporary`
ändert ein bestehendes Profil nur im Speicher; erst die Bestätigung schreibt es
dauerhaft. Das vermeidet eine neue Python-Abhängigkeit und nutzt die von
NetworkManager gepflegte Validierung.

Alternative: direkter D-Bus-Client (`dbus-next`, `jeepney`) mit
`Settings.Update2`. Genauer, aber deutlich mehr Code und eine zusätzliche
Laufzeitabhängigkeit. Für v1 wird `nmcli` gekapselt; ein späterer Wechsel bleibt
möglich, weil die Zustandsmaschine nur den Adapter kennt.

Alternative: `nmcli` über `sudo` oder einen root-Helper. Verworfen, weil
`NoNewPrivileges=true` setuid-Programme blockiert und ein zusätzlicher
Privilegien-Dienst die Angriffsfläche vergrößert.

### Berechtigungen über eine enge Polkit-Regel

Der Benutzer `ma2pi` erhält eine Regel unter
`/etc/polkit-1/rules.d/50-ma2pi-network.rules` für genau zwei Aktionen:

* `org.freedesktop.NetworkManager.settings.modify.system`
* `org.freedesktop.NetworkManager.network-control`

Damit darf der Dienst Systemprofile ändern und Verbindungen aktivieren, aber
keine WLAN-, Firewall- oder sonstigen Systemaktionen ausführen. `nmcli` spricht
über den System-Bus; `AF_UNIX` ist in der Unit bereits erlaubt,
`ProtectSystem=strict` und `NoNewPrivileges` bleiben unverändert.

Die Regel ist bewusst benutzerweit und nicht auf `eth0` begrenzt. Die
Einschränkung auf eine Schnittstelle liegt im Daemon-Code. Das ist ein
dokumentierter Trade-off; ein enger D-Bus-Proxy wäre für v1 zu aufwendig.

### Schnittstellenauswahl und Datenmodell

Verwaltet wird genau eine Schnittstelle:

1. kabelgebundene Schnittstelle mit Standardroute und Zustand `connected`,
2. sonst die erste verbundene kabelgebundene Schnittstelle,
3. sonst die erste kabelgebundene Schnittstelle.

`nmcli device status` liefert Typ und Zustand; virtuelle Geräte (`lo`, `docker`,
`veth`, `bridge`) werden ignoriert. Die Auswahl wird im UI sichtbar angezeigt,
ist aber in v1 nicht frei änderbar.

Die API verwendet Punktnotation für die Subnetzmaske, weil das die
Benutzereingabe ist. Intern rechnet `ipaddress` in eine Prefix-Länge um. Das
Statusmodell enthält sowohl die wirksamen Werte (`current`) als auch eine
mögliche offene Änderung (`pending`) und das letzte Ergebnis (`last_result`).

```json
{
  "backend": "networkmanager",
  "available": true,
  "can_manage": true,
  "interface": {
    "name": "eth0",
    "type": "ethernet",
    "state": "connected",
    "connection": "Wired connection 1"
  },
  "mode": "static",
  "current": {
    "address": "192.168.10.50",
    "subnet_mask": "255.255.255.0",
    "gateway": "192.168.10.1",
    "dns": ["192.168.10.1"]
  },
  "pending": {
    "mode": "static",
    "address": "192.168.10.60",
    "subnet_mask": "255.255.255.0",
    "gateway": "192.168.10.1",
    "dns": ["192.168.10.1"],
    "phase": "awaiting_confirmation",
    "started_at": "2026-11-26T12:00:00Z",
    "deadline": "2026-11-26T12:03:00Z",
    "target_url": "http://192.168.10.60:8080/",
    "error": null
  },
  "last_result": null
}
```

Im Modus `dhcp` sind `address`, `subnet_mask`, `gateway` und `dns` im
Kandidaten nicht erlaubt. Die API liefert im laufenden DHCP-Betrieb die
tatsächlich vergebene Adresse unter `current`, nicht die zuletzt statisch
eingetragenen Werte.

### Validierung

Vor jeder Vorschau und jedem Apply läuft dieselbe Prüfung:

| Feld | Regel |
| --- | --- |
| Adresse | gültige IPv4-Unicast-Adresse; nicht `0.0.0.0`, Loopback, Multicast, Broadcast oder `240.0.0.0/4`; Link-Local zulässig, aber mit Warnung |
| Subnetzmaske | zusammenhängende Punktnotation (`255.255.255.0`); Prefix 1–32 |
| Netz/Broadcast | bei Prefix ≤ 30 dürfen Adresse und Gateway weder Netz- noch Broadcast-Adresse sein |
| Gateway | optional; wenn gesetzt, gültige IPv4-Adresse im selben Subnetz und nicht die Host-Adresse; bei `/32` nur leer |
| DNS | 0–3 eindeutige IPv4-Adressen; Loopback ist als lokaler Resolver zulässig |
| Belegung | Adresse darf nicht bereits auf einer anderen Schnittstelle konfiguriert sein |
| Modus | `dhcp` ohne statische Felder; `static` mit Adresse und Maske |
| Link | Apply nur bei `connected`; sonst `409 link_down` |
| NetworkManager | `nmcli connection modify --temporary` und die dabei von NetworkManager ausgeführte Profilprüfung müssen erfolgreich sein |

Die Prüfung auf belegte Adressen liest alle `IP4.ADDRESS`-Werte der
NetworkManager-Geräte. Eine Adresse auf derselben Schnittstelle ist erlaubt
(idempotenter Apply). Ein ARP-Konflikt mit einem anderen Host wird nicht
erkannt; das bleibt ein dokumentiertes Restrisiko.

### Apply-Zustandsmaschine

```
idle
  │ PUT /api/network
  ▼
validating ── Fehler ──► 422, idle
  │
  ▼
write pending file (phase=activating) ── Fehler ──► 500, idle
  │ 202 + pending + target_url
  ▼
modify --temporary + connection up + auf IP warten
  │ Fehler ──► restore previous + phase=failed ──► idle (last_result)
  ▼
phase=awaiting_confirmation, deadline=now+180s
  │ POST /api/network/confirm            │ 180s / POST rollback
  ▼                                      ▼
persist (ohne --temporary)             restore previous
  │ Fehler ──► rollback                  │
  ▼                                      ▼
phase=confirmed ──► pending löschen    phase=rolled_back ──► pending löschen
```

Wichtige Details:

* Der Handler schreibt den Pending-Zustand atomar, startet die Aktivierung als
  Hintergrund-Task und antwortet mit `202`, bevor `nmcli connection up` läuft.
  Eine kurze Verzögerung von 100 ms im Task gibt dem Server Zeit, die Antwort
  zu senden; danach kann die Verbindung durch den Adresswechsel abbrechen.
* Die Aktivierung pollt `nmcli device status` und `IP4.ADDRESS` bis zu 20 s.
  Bei statischer Adresse muss die Zieladresse erscheinen, bei DHCP irgendeine
  IPv4-Adresse. Ohne Erfolg wird zurückgerollt.
* Das Bestätigungsfenster beginnt nach erfolgreicher Aktivierung und beträgt
  180 s. Während `activating` ist eine Bestätigung mit `409` abzulehnen.
* Genau ein Apply gleichzeitig: ein `asyncio.Lock` schützt die Zustandsmaschine;
  ein zweiter Aufruf erhält `409 apply_busy`. Eine offene Änderung blockiert
  weitere Apply- und Validate-Aufrufe.
* Ein manueller Rollback ist nur in `awaiting_confirmation` erlaubt.
* Nach einem Rollback bleibt die vorherige Konfiguration aktiv; die offene
  Änderung wird entfernt und `last_result` beschreibt das Ergebnis.

### Pending-Zustand und Neustart

`/var/lib/ma2pi/network-pending.json` wird mit `os.replace`, `fsync` und Modus
`0600` geschrieben. Es enthält die vorherigen rohen IPv4-Eigenschaften des
Profils (Methode, Adressen, Gateway, DNS, `ignore-auto-dns`), den Kandidaten,
die Schnittstelle, die Profil-UUID, den Ablaufzeitpunkt, die Phase und einen
optionalen Fehler. Die rohen Eigenschaften werden benötigt, weil ein Profil
mehrere Adressen oder DNS-Einträge enthalten kann; zurückgerollt wird exakt der
vorherige Zustand.

Phasen und Wiederanlauf:

| Phase | Verhalten beim Start |
| --- | --- |
| `activating` | Aktivierung war unterbrochen; vorherige Konfiguration wiederherstellen |
| `awaiting_confirmation` | Deadline prüfen: gültig → Timer fortsetzen, abgelaufen → Rollback |
| `confirmed` | Konfiguration ist dauerhaft gespeichert; Pending-Datei löschen |
| `rolling_back` | Rollback erneut ausführen |
| `failed` | Rollback erneut ausführen |

Beim Bestätigen wird zuerst die persistente NetworkManager-Konfiguration
geschrieben, dann `phase=confirmed` gesetzt und erst danach die Datei gelöscht.
Damit kann ein Absturz zwischen Schreiben und Löschen nicht zu einem
unerwünschten Rollback einer bereits bestätigten Konfiguration führen.

Ist die Datei beschädigt oder nicht lesbar, nimmt der Daemon keine automatische
Netzwerkänderung vor. Der Fehler wird geloggt und über `GET /api/network`
gemeldet; die aktive Konfiguration bleibt unangetastet.

### Notfall-Adresse und Erkennung

Ein sofortiger Rollback bei jeder unterbrochenen Verbindung wäre falsch: Der
Browser kann kurzzeitig neu verbinden, DHCP kann neu verhandeln, oder der
Benutzer öffnet die neue Adresse erst nach einigen Sekunden. Deshalb ist der
einzige automatische Auslöser das **erfolglose Bestätigungsfenster** von 180
Sekunden. Einzelne verlorene Pakete, ein WebSocket-Reconnect oder ein kurzer
HTTP-Abbruch lösen nichts aus.

Schlägt das Wiederherstellen der vorherigen Konfiguration fehl, wird als letzte
Stufe die Standard-Notfall-Adresse `192.168.178.254` mit Maske
`255.255.255.0`, ohne Gateway und ohne DNS angewendet und dauerhaft gespeichert.
Das ist eine gültige Host-Adresse im Netz `192.168.178.0/24`; sie darf nicht
bereits von einem anderen Gerät oder dem Router verwendet werden. Ein Client
muss für den Notzugriff eine Adresse aus `192.168.178.0/24` haben. Liegt das
normale Netz in einem anderen Subnetz, ist die Notfall-Adresse nur mit
entsprechender Client-Konfiguration erreichbar; das wird in der Oberfläche und
im README erklärt.

### Rettungs-WLAN

Der Rettungszugang ist ein NetworkManager-AP-Profil `ma2pi-recovery` auf
`wlan0` (WPA2-PSK, `192.168.50.1/24`, `ipv4.method=shared`). NetworkManager
startet den internen DHCP-Dienst selbst; es wird keine zusätzliche Software
installiert. Die Entscheidung ist in ADR-0018 festgehalten.

Der gewünschte Zustand (`enabled`, SSID, Passwort, `auto`) liegt in
`/var/lib/ma2pi/recovery.json` (0600). Ein Dienststart wendet ihn wieder an.
Die Automatik prüft alle 10 s, ob die verwaltete kabelgebundene Schnittstelle
eine nutzbare Adresse hat. Eine Adresse auf der Notfall-Adresse gilt als nicht
nutzbar. Der Hotspot wird nach 60 s Ausfall eingeschaltet und nach 60 s stabiler
Rückkehr wieder ausgeschaltet, aber nur, wenn die Automatik ihn selbst
eingeschaltet hat. Ein manueller Schalter bleibt unverändert.

Zusätzliche Polkit-Aktionen: `wifi.share.open` und `wifi.share.protected`.

### Profilwahl und Rollback

Es wird das aktive Profil der gewählten Schnittstelle geändert. Ist keines
aktiv, wird das passende Ethernet-Profil mit `autoconnect` gewählt; existiert
keines, legt der Daemon einmalig `ma2pi-<interface>` an und merkt sich
`created_profile=true`, damit ein Rollback dieses Profil wieder entfernen kann.

Geändert werden ausschließlich die IPv4-Eigenschaften; alle übrigen
Einstellungen des Profils bleiben erhalten. Für DHCP werden `ipv4.method=auto` und die
statischen Felder geleert, für statisch `ipv4.method=manual` mit
`ipv4.addresses=<adresse>/<prefix>`, `ipv4.gateway` und `ipv4.dns` gesetzt.

Beim Rollback werden die vorherigen IPv4-Eigenschaften mit `--temporary`
zurückgeschrieben und das Profil erneut aktiviert. War das Profil zuvor nicht
vorhanden, wird es gelöscht und die vorherige Verbindung wiederhergestellt.
Schlägt der Rollback fehl, bleibt die Pending-Datei mit `phase=failed` erhalten
und der Fehler ist sichtbar; ein erneuter Start versucht den Rollback erneut.

### API

| Methode | Pfad | Zweck |
| --- | --- | --- |
| GET | `/api/network` | Status, Schnittstelle, aktuelle Werte, offene Änderung, letztes Ergebnis |
| POST | `/api/network/validate` | Kandidat prüfen, Ziel-URL und Warnungen liefern, nichts ändern |
| PUT | `/api/network` | Kandidat validieren, Pending anlegen und temporär aktivieren; `202` |
| POST | `/api/network/confirm` | Offene Änderung dauerhaft speichern |
| POST | `/api/network/rollback` | Offene Änderung vorzeitig zurückrollen |

Alle Pfade liegen unter dem bestehenden PIN-Schutz. Schreibende Aufrufe
verlangen `Content-Type: application/json` und `X-Ma2pi-Request: 1`; die
bestehende Middleware bleibt unverändert. Die Confirm- und Rollback-Aufrufe
tragen einen leeren JSON-Body (`{}`), damit die JSON-Pflicht erfüllt ist.

Fehlercodes:

| Code | Bedeutung |
| --- | --- |
| `400 invalid_json` | kein JSON-Objekt |
| `401 pin_required` | keine gültige PIN-Session |
| `403 missing_request_header` | Header fehlt |
| `409 apply_busy` | ein Apply läuft bereits |
| `409 pending_exists` | offene Änderung blockiert den Aufruf |
| `409 no_pending` | Bestätigung/Rollback ohne offene Änderung |
| `409 link_down` | Kabel ist nicht verbunden |
| `415 unsupported_media_type` | kein JSON |
| `422 validation_error` | Feldbezogener Validierungsfehler |
| `503 network_unavailable` | NetworkManager/`nmcli`/Polkit nicht nutzbar |
| `500 apply_failed` | Aktivierung oder Persistenz fehlgeschlagen |

Die API-Version bleibt `1`, weil die neuen Endpunkte additiv sind. Der
Build-Stamp der SPA ändert sich und verhindert wie bisher einen alten
UI-Stand gegen die neue API.

### Frontend

Neue Seite **Netzwerk** in der bestehenden Navigation. Sie zeigt:

* Statuskarte mit Schnittstelle, Verbindungszustand, Modus, aktueller Adresse,
  Subnetzmaske, Gateway und DNS.
* Umschalter **DHCP** / **Statisch**; im statischen Modus die Felder Adresse,
  Subnetzmaske, Gateway und DNS (kommagetrennt, maximal drei Einträge).
* Vorschau-Button; Serverfehler werden am jeweiligen Feld angezeigt.
* Vor dem Anwenden einen Bestätigungsdialog mit Warnung, Ziel-URL und dem
  Hinweis, dass die PIN nach dem Adresswechsel erneut eingegeben werden muss.
* Nach dem Anwenden eine Pending-Ansicht mit Countdown, Ziel-URL,
  „Ich bin verbunden – bestätigen“ und „Zurückrollen“. Die Seite pollt den
  Status, solange eine Änderung läuft, und verbindet sich über die bestehende
  WebSocket-Logik neu.
* Kein Neustart-Popup und kein Neustartzwang: Die Änderung wird live angewendet;
  der Dialog erklärt die Trennung, die Ziel-URL und das Bestätigungsfenster.
* Bei nicht verfügbarem Backend eine schreibgeschützte Ansicht mit
  Fehlerhinweis; die zuletzt geladenen Werte bleiben sichtbar.

Der `StatusStore` wird um ein Feld `network` und die Behandlung des
WebSocket-Ereignisses `{"type":"network","data":...}` erweitert. `NetworkPage`
lädt den Status zusätzlich per `GET /api/network`, weil nach einem Adresswechsel
keine alte WebSocket-Verbindung mehr existiert. Der API-Client erhält typisierte
Methoden und Antworttypen.

Die Oberfläche erkennt die eigene Verbindung über die lokale Adresse des
HTTP-Requests (`sockname`) und vergleicht sie mit den Adressen der verwalteten
Schnittstelle. Bei Übereinstimmung erscheint die stärkere Warnung. Das ist eine
Heuristik; bei mehreren Adressen oder Proxy-Zugriffen kann sie fehlschlagen,
deshalb bleibt die Warnung vor jedem Apply sichtbar.

### Sicherheit und Aussperrschutz

* PIN-Session, JSON-Pflicht und Request-Header gelten unverändert.
* Nach einem Adresswechsel ist das PIN-Cookie an den alten Host gebunden. Die
  Oberfläche erklärt das und verlangt die PIN unter der neuen Adresse erneut;
  genau diese neue Session bestätigt die Änderung.
* Ohne Bestätigung wird nach 180 s zurückgerollt; der Benutzer kann die alte
  Adresse wieder öffnen.
* Schnittstelle und Profil-UUID stammen aus NetworkManager, nicht aus
  Benutzereingaben. `create_subprocess_exec` verhindert Shell-Injection.
* Fehlerantworten enthalten keine Passwörter, PINs oder vollständigen
  Kommandozeilen mit Geheimnissen.
* Die Polkit-Regel ist auf zwei Aktionen begrenzt; der Dienst bleibt
  unprivilegiert.

### Deployment

* `deploy/50-ma2pi-network.rules` wird nach
  `/etc/polkit-1/rules.d/50-ma2pi-network.rules` installiert (0644,
  root:root).
* `install.sh` prüft `nmcli`, den NetworkManager-Dienst und Polkit und bricht
  mit einem Paket-Hinweis ab, wenn sie fehlen. Es installiert keine Pakete
  automatisch.
* Die systemd-Unit bleibt unverändert. `StateDirectory=ma2pi` deckt die
  Pending-Datei ab; `ReadWritePaths=/var/lib/ma2pi` bleibt ausreichend.
* README und `docs/api.md` beschreiben Netzwerkseite, Ziel-URL, PIN-Neuanmeldung,
  Rollback und die Grenzen (nur Ethernet, nur IPv4).
* ADR-0017 hält die Entscheidung für NetworkManager, temporäre Aktivierung und
  Rollback fest.

## Risks / Trade-offs

* **Aussperren durch falsche, aber gültige Adresse** → Zwei-Phasen-Apply,
  sichtbare Ziel-URL, 180-s-Fenster, automatischer Rollback, persistenter
  Pending-Zustand.
* **Browser erreicht die neue Adresse nicht** → Rollback nach Ablauf; die
  Oberfläche nennt vorher die alte und die neue Adresse. Kein automatisches
  Bestätigen ohne erneute PIN.
* **PIN-Cookie gilt nicht für die neue IP** → bewusste erneute Anmeldung; sie
  ist zugleich der Nachweis, dass die neue Adresse erreichbar ist.
* **`nmcli`-Ausgabe ist textuell** → feste Felder, `-t`/`-g`, `LC_ALL=C`,
  Parser-Tests mit echten Ausgaben; der Adapter ist die einzige Stelle mit
  Kommandozeilenwissen.
* **Polkit-Regel erlaubt mehr als eine Schnittstelle** → Code beschränkt auf die
  gewählte Ethernet-Schnittstelle; Prozess läuft nur als `ma2pi`; Dienst ist
  PIN-geschützt. Ein enger D-Bus-Proxy bleibt eine spätere Option.
* **Netzwerkprofil hat mehrere Adressen oder DNS-Einträge** → rohe
  IPv4-Eigenschaften werden gesichert und exakt zurückgeschrieben; die UI
  verwaltet in v1 nur eine Adresse.
* **Daemon stirbt während der Aktivierung** → Phase `activating` wird beim Start
  als unterbrochen behandelt und rollt zurück; `confirmed` wird vor dem Löschen
  der Pending-Datei markiert.
* **Kabel ist nicht verbunden** → Apply wird mit `409 link_down` abgelehnt;
  die Oberfläche kann den Status weiterhin lesen.
* **DHCP liefert eine andere Adresse als erwartet** → nach der Aktivierung wird
  die tatsächlich vergebene Adresse angezeigt; die Bestätigung erfolgt über
  diese Adresse.
* **Kein ARP-Konfliktcheck** → dokumentiert; die lokale Belegungsprüfung
  verhindert nur Doppelbelegung auf dem Pi selbst.
* **Notfall-Adresse `192.168.178.254` ist im falschen Subnetz nicht erreichbar**
  → bewusst als letzte Rettung dokumentiert; der Client braucht eine Adresse aus
  `192.168.178.0/24`, und die Adresse muss frei sein.
* **Kurzer Verbindungsverlust wird als Aussperrung missverstanden** → kein
  sofortiger Rollback; nur das erfolglose 180-s-Bestätigungsfenster oder der
  Ausfall des Rollbacks lösen die Notfall-Adresse aus.
* **IPv6-only-Netze** → nicht unterstützt; die Oberfläche und die API arbeiten
  ausschließlich mit IPv4.

## Migration Plan

1. Neue Version installieren; `install.sh` prüft NetworkManager, `nmcli` und
   Polkit und installiert die Regel.
2. Dienst starten; `GET /api/network` muss die kabelgebundene Schnittstelle und
   die aktuelle DHCP-/statische Konfiguration lesen können.
3. Auf einem Testaufbau zuerst eine statische Adresse im selben Subnetz setzen,
   die neue Adresse öffnen, PIN eingeben und bestätigen.
4. Rollback testen: Änderung starten und nicht bestätigen; nach 180 s muss die
   alte Adresse wieder erreichbar sein.
5. Dienstneustart während des Fensters testen; der Timer muss fortgesetzt
   beziehungsweise die abgelaufene Änderung zurückgerollt werden.
6. Erst danach die produktive Adresse umstellen und die neue Adresse im README
   beziehungsweise in der Betreiberdokumentation eintragen.

Rollback der Funktion: Polkit-Regel entfernen, vorherige Version installieren.
Die Netzwerkkonfiguration bleibt bei NetworkManager und ist unabhängig von der
Anwendung; ein Rückbau der Anwendung ändert die zuletzt bestätigte IP nicht.

## ADR-Übersicht

| ADR | Thema | Status |
| --- | --- | --- |
| 0017 | Netzwerkkonfiguration über NetworkManager mit Bestätigung und Rollback | Proposed |
