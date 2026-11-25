# 0013. LAN-Zugriffsmodell ohne Login

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

## Kontext und Problemstellung

Die Oberfläche muss aus dem LAN erreichbar sein, damit Zugangsdaten und Mapping
ohne SSH bearbeitet werden können. Das Gerät hängt nicht am Internet. Ein
Login-Verfahren in v1 würde zusätzlichen Aufwand und einen weiteren
Geheimnis-Speicher erfordern. Gleichzeitig kann jeder Client im LAN das Mapping
und die MA2-Zugangsdaten ändern, wenn die Oberfläche offen ist.

## Entscheidungstreiber

* Einfache Bedienung im vertrauenswürdigen LAN
* Keine Internet-Exposition
* Kein zusätzlicher Login-Aufwand in v1
* Kein Zurückgeben von Geheimnissen
* Späterer Ausbau um eine PIN ohne Architekturbruch

## Betrachtete Optionen

* Nur localhost, Zugriff über SSH-Tunnel
* Offenes LAN ohne Login
* LAN mit PIN-Login
* LAN mit TLS und Reverse Proxy
* Kein UI

## Entscheidung

Die Oberfläche ist im LAN ohne Login erreichbar. Bind-Adresse und Port sind
konfigurierbar, Default ist `0.0.0.0:8080`. Es gibt keine
Internet-Weiterleitung und keine Cloud-Anbindung. Schreibende API-Aufrufe
müssen `Content-Type: application/json` und den Header `X-Ma2pi-Request: 1`
tragen; einfache Formular-POSTs werden abgelehnt. Das MA2-Passwort wird nur
geschrieben und nie zurückgegeben. CORS wird nicht freigegeben.

Eine PIN-Sperre wird als Middleware-Hook und Konfigurationsfeld
`[web].pin_enabled = false` vorbereitet, in v1 aber nicht implementiert. Der
Besitzer akzeptiert bewusst, dass jeder Client im LAN die Konfiguration ändern
kann.

### Konsequenzen

* Gut, weil die Bedienung ohne Login und ohne Zusatzsoftware funktioniert.
* Gut, weil keine Internet-Abhängigkeit und kein Cloud-Dienst entstehen.
* Gut, weil die JSON-/Header-Pflicht triviale CSRF-Versuche erschwert.
* Schlecht, weil jeder im LAN das Mapping und die Zugangsdaten ändern kann.
* Schlecht, weil das Passwort bei der Eingabe unverschlüsselt über HTTP im LAN übertragen wird.
* Schlecht, weil eine spätere PIN-Sperre einen zusätzlichen Geheimnis-Speicher und Session-Handling braucht.

### Bestätigung

Accepted, wenn die UI aus dem LAN ohne Login erreichbar ist, schreibende
Aufrufe ohne JSON/Header abgelehnt werden, das Passwort in keiner Antwort
erscheint und der Besitzer das Restrisiko ausdrücklich bestätigt hat.

## Vor- und Nachteile der Optionen

### Nur localhost

* Gut, weil kein LAN-Zugriff möglich ist.
* Schlecht, weil Konfiguration ohne SSH-Tunnel nicht erreichbar wäre und der Komfort verloren geht.

### Offenes LAN

* Gut, weil einfach und für ein vertrauenswürdiges Netz ausreichend.
* Schlecht, weil kein Schutz gegen andere Clients im LAN besteht.

### LAN mit PIN

* Gut, weil ein einfacher Schutz gegen unbefugte Änderungen bestünde.
* Schlecht, weil PIN-Verwaltung, Session und Reset-Prozess zusätzlichen Aufwand erzeugen.

### LAN mit TLS und Reverse Proxy

* Gut, weil das Passwort verschlüsselt übertragen würde.
* Schlecht, weil Zertifikatsverwaltung und ein weiterer Dienst auf dem Pi nötig wären.

## Weitere Informationen

* Verwandt: ADR-0008, ADR-0009, ADR-0011
