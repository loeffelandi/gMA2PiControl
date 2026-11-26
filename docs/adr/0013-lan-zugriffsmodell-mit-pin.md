# 0013. LAN-Zugriffsmodell mit einfacher PIN-Sperre

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Accepted

## Kontext und Problemstellung

Die Oberfläche muss aus dem LAN erreichbar sein, damit Zugangsdaten und Mapping
ohne SSH bearbeitet werden können. Das Gerät hängt nicht am Internet. Ein
vollständiges Login-Verfahren mit Rollen würde zusätzlichen Aufwand und einen
weiteren Geheimnis-Speicher erfordern. Gleichzeitig soll nicht jeder Client im
LAN ohne Weiteres das Mapping und die MA2-Zugangsdaten ändern können.

## Entscheidungstreiber

* Einfache Bedienung im vertrauenswürdigen LAN
* Keine Internet-Exposition
* Einfacher Schutz gegen unbefugte Änderungen
* Kein Zurückgeben von Geheimnissen
* Kein vollständiges Benutzer- und Rollenmodell

## Betrachtete Optionen

* Nur localhost, Zugriff über SSH-Tunnel
* Offenes LAN ohne Login
* LAN mit PIN-Login
* LAN mit TLS und Reverse Proxy
* Kein UI

## Entscheidung

Die Oberfläche ist im LAN erreichbar. Bind-Adresse und Port sind
konfigurierbar, Default ist `0.0.0.0:8080`. Es gibt keine Internet-Weiterleitung
und keine Cloud-Anbindung. Eine einfache PIN-Sperre ist optional und
standardmäßig aus. Ist eine PIN gesetzt (`[web].pin_enabled = true`,
`[web].pin`), besteht sie aus 4–12 Ziffern. Ohne PIN zeigt die Oberfläche einen
Warnbanner. Nach erfolgreicher PIN setzt der Daemon ein `HttpOnly`-Cookie mit
einer In-Memory-Session; alle API-Pfade außer Health, Version und Auth verlangen
diese Session. Die PIN ist in der Oberfläche unter **Erweitert** änderbar und
wird nie zurückgegeben.

Schreibende API-Aufrufe müssen `Content-Type: application/json` und den Header
`X-Ma2pi-Request: 1` tragen; einfache Formular-POSTs werden abgelehnt. Das
MA2-Passwort wird nur geschrieben und nie zurückgegeben. CORS wird nicht
freigegeben.

### Konsequenzen

* Gut, weil die Bedienung ohne vollständiges Login und ohne Zusatzsoftware funktioniert.
* Gut, weil keine Internet-Abhängigkeit und kein Cloud-Dienst entstehen.
* Gut, weil die JSON-/Header-Pflicht triviale CSRF-Versuche erschwert.
* Gut, weil ein einfacher Schutz gegen unbefugte Änderungen im LAN besteht.
* Schlecht, weil die PIN bei der Eingabe unverschlüsselt über HTTP im LAN übertragen wird.
* Schlecht, weil es keine Rollen, kein Audit-Log und keinen zentralen Reset gibt.

### Bestätigung

Accepted, wenn die UI aus dem LAN mit PIN erreichbar ist, falsche PINs
abgelehnt werden, schreibende Aufrufe ohne JSON/Header abgelehnt werden,
Passwort und PIN in keiner Antwort erscheinen und der Besitzer das Restrisiko
ausdrücklich bestätigt hat.

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
