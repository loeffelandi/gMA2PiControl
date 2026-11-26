# gMA2PiControl JSON-API

Die Oberfläche spricht ausschließlich über diese API mit dem Daemon. Alle
Antworten sind JSON; die WebSocket-Verbindung liefert Live-Ereignisse. Die
Referenz beschreibt den Stand dieser Änderung und deckt alle registrierten
Handler ab.

Basis: `http://<pi-adresse>:8080`

## Schreibende Aufrufe

`POST`, `PUT`, `PATCH` und `DELETE` unter `/api/` benötigen:

```http
Content-Type: application/json
X-Ma2pi-Request: 1
```

Einfache Formular-POSTs werden mit `415` oder `403` abgelehnt. Oberfläche und
API können zusätzlich durch eine PIN geschützt werden; die PIN ist
standardmäßig nicht gesetzt. Nur `/api/health`, `/api/version` und die
Auth-Endpunkte sind ohne PIN erreichbar. Die PIN ist ein LAN-Schutz, keine
Internet-Absicherung.

## PIN-Anmeldung

Ist eine PIN konfiguriert, zeigt die Oberfläche eine Sperrseite. Nach
erfolgreicher Anmeldung setzt der Daemon ein `HttpOnly`-Cookie (`ma2pi_pin`);
die Session liegt im Speicher und endet beim Dienstneustart. Ohne PIN bleibt
die API offen und die Oberfläche zeigt einen Warnbanner.

### `GET /api/auth/status`

```json
{ "pin_enabled": false, "pin_set": false, "authenticated": true }
```

### `POST /api/auth/login`

```json
{ "pin": "<PIN>" }
```

Bei Erfolg `{"ok": true}` und ein Session-Cookie. Bei falscher PIN `401`
(`pin_invalid`).

### `POST /api/auth/logout`

Löscht die Session und das Cookie.

Alle anderen `/api/`-Pfade liefern ohne gültige PIN `401` mit
`{"error": "pin_required"}`.

## Konfigurations-Patches

`PUT /api/config`, `POST /api/config/validate` und die Wiederherstellung
arbeiten mit einem JSON-Merge-Patch nach RFC 7386:

* Ein Objekt wird rekursiv zusammengeführt.
* `null` entfernt den Schlüssel.
* Arrays werden vollständig ersetzt.

Unveränderte Bereiche und ihre TOML-Kommentare bleiben erhalten. Das Passwort
wird nie gelesen; es kann nur als `ma2.password` geschrieben werden.

## Endpunkte

### `GET /api/health`

```json
{ "status": "ok" }
```

### `GET /api/version`

```json
{ "api": "1", "package": "0.1.0", "ui": "1764...-79463" }
```

Die Oberfläche vergleicht `api` mit ihrer erwarteten Version und zeigt bei einem
Mismatch einen Hinweis. `ui` ist ein Build-Stempel aus `web/dist/index.html`.

### `GET /api/status`

```json
{
  "connected": true,
  "authenticated": true,
  "session": 7,
  "queue_depth": 0,
  "rate": 25.0,
  "screen_mode": false,
  "frames_sent": 142,
  "last_frame_types": ["keyname", "encoder"],
  "reconnects": 0,
  "last_error": null,
  "generation": 3,
  "busy": false,
  "activity": {
    "devices": {
      "cherry": { "rx": 120, "tx": 0, "last_rx": 1790000000.12, "last_tx": null },
      "midicraft": { "rx": 34, "tx": 12, "last_rx": 1790000000.9, "last_tx": 1790000000.88 }
    },
    "log": [
      { "seq": 210, "ts": 1790000000.91, "direction": "tx",
        "device": "ma2", "kind": "playbacksRequest",
        "summary": "playbacksRequest" }
    ]
  }
}
```

`generation` steigt nach jedem erfolgreichen Apply. `busy` ist `true`, während
ein Apply läuft. Zugangsdaten sind nie enthalten.

`activity` zählt RX (vom Gerät gelesen) und TX (zum Gerät geschrieben) seit dem
Prozessstart. Zeitstempel sind Sekunden seit der Epoche. `log` ist ein Ring der
letzten 100 Ereignisse mit monotoner `seq`; Summary-Texte enthalten keine
Kommandotexte oder Zugangsdaten. Frames an onPC erscheinen nur im Log unter der
Kennung `ma2` und zählen nicht als Gerät. Wiederkehrende Polling-Frames
(`playbacksRequest`) werden nicht protokolliert, damit echte Eingaben im Ring
bleiben.

### `GET /api/events` (WebSocket)

Beim Verbinden wird ein `status`-Ereignis gesendet. Danach folgen:

| `type` | Bedeutung |
| --- | --- |
| `status` | Laufzeitstatus, etwa einmal pro Sekunde; enthält den vollständigen Aktivitäts-Ring als Resync |
| `activity` | Neue RX-/TX-Aktivität und aktuelle Zähler, gebündelt höchstens alle 250 ms; höchstens 100 Einträge pro Event |
| `learn` | Learn-Sitzung gestartet, erfasst, abgebrochen oder abgelaufen |
| `config` | Konfiguration wurde angewendet (`generation`) |
| `backup` | Backup wurde angelegt |
| `backup_restored` | Backup wurde wiederhergestellt (`id`, `generation`) |
| `network` | Netzwerkänderung gestartet, bestätigt, zurückgerollt oder fehlgeschlagen (`pending`, `last_result`) |

Beispiel:

```json
{ "type": "learn", "data": {
  "kind": "key", "status": "captured", "control": "fix",
  "device": "cherry", "raw": "KEY_HOME", "direction": 0,
  "detents": 0, "elapsed": 0.42, "timed_out": false
} }
```

```json
{ "type": "activity", "data": {
  "devices": {
    "cherry": { "rx": 121, "tx": 0, "last_rx": 1790000000.95, "last_tx": null }
  },
  "entries": [
    { "seq": 211, "ts": 1790000000.95, "direction": "rx",
      "device": "cherry", "kind": "key",
      "summary": "ch_pg_plus · value 1 · note 42 · bank 1" }
  ]
} }
```

Clients deduplizieren `entries` über `seq` und begrenzen ihren Log-Stand auf 100
Zeilen. Ein `status`-Snapshot ersetzt den lokalen Stand vollständig.

Die Oberfläche verbindet sich nach einer Unterbrechung automatisch neu.

### `GET /api/config`

Liefert die aktive Konfiguration ohne Passwortmaterial. Statt `password_file`
und `password_env` erscheint `password_set`:

```json
{
  "schema_version": 1,
  "ma2": {
    "host": "192.168.0.10",
    "port": 80,
    "path": "/?ma=1",
    "username": "ma2pi",
    "password_set": true
  },
  "web": {
    "bind": "0.0.0.0",
    "port": 8080,
    "pin_enabled": true,
    "pin_set": true
  },
  "devices": { "...": {} },
  "profiles": { "...": {} },
  "mapping": {
    "keys": { "fix": { "hardkey": "Fix" } },
    "encoders": [ { "id": 1, "slot": 1 } ]
  }
}
```

### `PUT /api/config`

Validiert, speichert und wendet einen Merge-Patch an. Das Passwort ist optional
und write-only:

```bash
curl -X PUT http://pi:8080/api/config \
  -H 'Content-Type: application/json' \
  -H 'X-Ma2pi-Request: 1' \
  -d '{
    "ma2": { "host": "192.168.0.10", "password": "geheim" },
    "mapping": { "keys": { "fix": { "hardkey": "Store" } } }
  }'
```

Erfolg (`200`):

```json
{ "generation": 4, "config": { "ma2": { "host": "192.168.0.10", "password_set": true } } }
```

Bei geänderten Zugangsdaten wird vorher ein Verbindungstest ausgeführt. Reine
Mapping-Änderungen lassen die laufende Session bestehen.

### `POST /api/config/validate`

Prüft denselben Patch ohne zu schreiben:

```json
{ "valid": true }
```

### `POST /api/test-connection`

Testet Zugangsdaten, ohne die Konfiguration zu verändern. Felder dürfen direkt
oder unter `ma2` stehen; `password` ist optional.

```json
{ "host": "192.168.0.10", "port": 80, "username": "ma2pi", "password": "geheim" }
```

```json
{ "session": 7, "username": "ma2pi", "target": "ws://192.168.0.10:80/?ma=1", "reused": true }
```

`reused` ist `true`, wenn die bestehende Session geprüft wurde und keine zweite
Verbindung geöffnet wurde.

### `GET /api/devices`

```json
{ "devices": [ {
  "name": "cherry",
  "backend": "evdev",
  "profile": "cherry-g86",
  "vendor_id": 1130,
  "product_id": 0,
  "vendor_product": "046a:0000",
  "name_contains": "Cherry",
  "detected": { "path": "/dev/input/event0", "readable": true },
  "controls": {
    "keys": [ { "code": "KEY_HOME", "control": "fix" } ],
    "notes": [],
    "encoders": [],
    "midi_encoders": [],
    "logical": ["fix"]
  }
} ] }
```

`detected` ist `null`, wenn das Gerät gerade nicht erkannt wird.
Encoder-Controls heißen `encoder.<id>`.

### `POST /api/learn/start`

```json
{ "kind": "key", "device": "cherry" }
```

`kind` ist `key` oder `encoder`; `device` ist optional. Es läuft höchstens eine
Sitzung. Antwort und WebSocket-Ereignis enthalten den aktiven Zustand. Timeout
ist 15 s, das Encoder-Fenster 2 s. Während des Lernens werden keine
Mapping-Frames gesendet.

### `POST /api/learn/cancel`

```json
{ "cancelled": true, "learn": { "kind": "key", "status": "cancelled" } }
```

Ohne aktive Sitzung ist `cancelled` `false`, der Status bleibt `200`.

### `GET /api/backups`

```json
{ "backups": [
  { "id": "config-20261126-010000.toml", "size": 14210,
    "modified": "2026-11-26T01:00:00", "last_good": false },
  { "id": "last-good.toml", "size": 14180,
    "modified": "2026-11-26T01:00:00", "last_good": true }
] }
```

### `POST /api/backups`

Legt ein Backup der aktiven Konfiguration an. Antwort `201` mit dem Eintrag.

### `POST /api/backups/{id}/restore`

Validiert das Backup und wendet es an. `{id}` ist ein Dateiname aus
`GET /api/backups`; Pfadwechsel (`../`) werden abgelehnt. Erfolg:

```json
{ "ok": true, "id": "config-20261126-010000.toml", "generation": 5,
  "ma2": { "host": "192.168.0.10", "port": 80,
           "path": "/?ma=1", "username": "ma2pi" } }
```

Ein ungültiges Backup liefert `422` und verändert die aktive Konfiguration
nicht.

## Netzwerk

Die Netzwerk-API verwaltet genau eine kabelgebundene IPv4-Schnittstelle über
NetworkManager. Sie ändert nicht `config.toml`. Schreibende Aufrufe benötigen
JSON und `X-Ma2pi-Request: 1`; die PIN-Sperre gilt auch hier.

### `GET /api/network`

```json
{
  "backend": "networkmanager",
  "available": true,
  "can_manage": true,
  "interface": {
    "name": "eth0", "type": "ethernet", "state": "connected",
    "connection": "Wired connection 1"
  },
  "mode": "static",
  "current": {
    "address": "192.168.10.50", "subnet_mask": "255.255.255.0",
    "gateway": "192.168.10.1", "dns": ["192.168.10.1"]
  },
  "pending": null,
  "last_result": null,
  "self_connection": false,
  "error": null,
  "warnings": []
}
```

`available` ist `false`, wenn NetworkManager oder `nmcli` fehlt. `can_manage`
ist `false`, wenn keine kabelgebundene Schnittstelle gefunden wurde oder das
Profil nicht unterstützt wird. `self_connection` ist `true`, wenn die verwaltete
Adresse die aktuelle Browser-Verbindung trägt. `last_result.status` ist
`confirmed`, `rolled_back`, `failed` oder `fallback`.

Eine offene Änderung erscheint unter `pending`:

```json
{
  "mode": "static", "address": "192.168.10.60",
  "subnet_mask": "255.255.255.0", "gateway": "192.168.10.1",
  "dns": ["192.168.10.1"],
  "phase": "awaiting_confirmation",
  "started_at": "2026-11-26T12:00:00Z",
  "deadline": "2026-11-26T12:03:00Z",
  "target_url": "http://192.168.10.60:8080/",
  "error": null
}
```

### `POST /api/network/validate`

Prüft einen Kandidaten ohne Änderung:

```json
{
  "mode": "static",
  "address": "192.168.10.60",
  "subnet_mask": "255.255.255.0",
  "gateway": "192.168.10.1",
  "dns": ["192.168.10.1"]
}
```

```json
{ "valid": true, "target_url": "http://192.168.10.60:8080/", "warnings": [] }
```

Im DHCP-Modus nur `{"mode": "dhcp"}` senden. Statische Felder sind dann nicht
erlaubt. Subnetzmasken werden in Punktnotation angegeben und serverseitig in
eine Prefix-Länge umgerechnet.

### `PUT /api/network`

Validiert den Kandidaten, speichert den Pending-Zustand und startet die
temporäre Aktivierung. Die Antwort kommt mit `202`, bevor die Verbindung durch
den Adresswechsel abbrechen kann:

```json
{
  "pending": {
    "mode": "static", "address": "192.168.10.60",
    "subnet_mask": "255.255.255.0", "phase": "activating",
    "target_url": "http://192.168.10.60:8080/", "deadline": null
  },
  "target_url": "http://192.168.10.60:8080/"
}
```

Die Aktivierung kann die laufende HTTP-Verbindung trennen. Die neue Adresse im
Browser öffnen, dort die PIN erneut eingeben und bestätigen.

### `POST /api/network/confirm`

```json
{}
```

Speichert die offene Änderung dauerhaft und beendet das Bestätigungsfenster.
Antwort ist der neue Status wie bei `GET /api/network`. Ohne offene Änderung
`409 no_pending`; während der Aktivierung `409 pending_exists`.

### `POST /api/network/rollback`

```json
{}
```

Stellt die vorherige IPv4-Konfiguration sofort wieder her. Antwort ist der neue
Status. Ohne offene Änderung `409 no_pending`.

### Rettungs-WLAN

Der Rettungs-Hotspot spannt auf `wlan0` ein WPA2-WLAN auf, vergibt per DHCP
Adressen aus `192.168.50.0/24` und ist unter `http://192.168.50.1:8080/`
erreichbar. Er ist standardmäßig aus. Die Einstellungen liegen unter
`/var/lib/ma2pi/recovery.json` (0600).

#### `GET /api/recovery`

```json
{
  "available": true, "enabled": false, "active": false,
  "ssid": "ma2pi-recovery", "password": "ma2pi-recovery",
  "auto": true, "auto_triggered": false,
  "address": null, "url": "http://192.168.50.1:8080/", "error": null
}
```

#### `PUT /api/recovery`

```json
{ "enabled": true, "ssid": "ma2pi-recovery", "password": "geheim-123", "auto": true }
```

Alle Felder sind optional. `ssid` 1–32 Zeichen, `password` 8–63 Zeichen. Ein
ungültiger Wert liefert `422` mit `field`. Die Antwort hat dasselbe Format wie
`GET /api/recovery`.

Die Automatik (`auto`) schaltet den Hotspot ein, wenn das kabelgebundene Netz
länger als 60 Sekunden keine nutzbare Adresse hat oder die Schnittstelle auf
der Notfall-Adresse `192.168.178.254` liegt. Er schaltet sich wieder aus, wenn
das Netz danach 60 Sekunden stabil ist und der Hotspot automatisch eingeschaltet
wurde. Beim Aktivieren wird eine bestehende WLAN-Verbindung auf `wlan0`
getrennt.

### Netzwerk-Fehlercodes

| Status | `error` | Bedeutung |
| --- | --- | --- |
| 409 | `apply_busy` | Es läuft bereits ein Netzwerk-Apply |
| 409 | `pending_exists` | Eine offene Änderung blockiert den Aufruf |
| 409 | `no_pending` | Keine offene Änderung zum Bestätigen/Zurückrollen |
| 409 | `link_down` | Die Schnittstelle hat keinen Link |
| 422 | `validation_error` | Feld ist ungültig; `field` nennt es |
| 500 | `apply_failed` | Aktivierung, Persistenz oder Rollback fehlgeschlagen |
| 503 | `network_unavailable` | NetworkManager, `nmcli` oder Berechtigung fehlt |

## Fehler

Fehler haben die Form:

```json
{ "error": "validation_error", "detail": "mapping.encoders[0].slot: muss zwischen 1 und 8 liegen" }
```

| Status | `error` | Bedeutung |
| --- | --- | --- |
| 400 | `invalid_json` | Körper ist kein JSON-Objekt |
| 401 | `pin_required` | PIN-Session fehlt oder ist abgelaufen |
| 401 | `pin_invalid` | PIN falsch |
| 403 | `missing_request_header` | `X-Ma2pi-Request: 1` fehlt |
| 409 | `apply_busy` | Es läuft bereits ein Apply |
| 409 | `learn_busy` | Es läuft bereits eine Learn-Sitzung |
| 415 | `unsupported_media_type` | Kein `application/json` bei einem Schreibaufruf |
| 422 | `validation_error` | Konfiguration ist schemawidrig; `detail` nennt das Feld |
| 422 | `connection_failed` | Zugangsdaten oder Handshake scheitern |
| 422 | `invalid_backup` | Backup-ID unbekannt oder Backup ungültig |
| 422 | `invalid_learn_request` | Unbekannter Learn-Typ |
| 422 | `invalid_request` | Ungültiger Feldtyp |
| 500 | `config_failed` / `backup_failed` / `restore_failed` | Schreibfehler |
| 502 | `unreachable` | Ziel ist nicht erreichbar |
| 503 | `config_store_unavailable` / `learn_unavailable` | Dienstteil nicht aktiv |
| 503 | `network_unavailable` | Netzwerkverwaltung nicht aktiv oder nicht verfügbar |
| 503 | `recovery_unavailable` | Rettungs-WLAN nicht aktiv |
| 500 | `recovery_failed` | Hotspot konnte nicht angewendet werden (z. B. fehlende Polkit-Berechtigung) |
| 503 | `ui_not_built` | `web/dist` fehlt |

Antworten und Logs enthalten nie das MA2-Passwort oder dessen Hash.
