# 23. Produktname gMA2PiControl bei technischem Paketnamen ma2pi

* Datum: 2026-11-26
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

References [0011. Frontend mit Svelte 5 und Vite](0011-frontend-mit-svelte-5-und-vite.md)

## Kontext und Problemstellung

Das Projekt trägt seit Beginn den technischen Namen `ma2pi`: Python-Paket,
Entrypoint, systemd-Unit, Service-Benutzer, StateDirectory, Passwortdatei und
Recovery-SSID. In der Oberfläche und in der Außenkommunikation soll das Produkt
dagegen **gMA2PiControl** heißen. Eine vollständige Umbenennung würde Imports,
Deploy-Skripte, bestehende Installationen und dokumentierte Pfade brechen; ein
gar kein Umbenennen lässt Produkt und technische Kennung dauerhaft
auseinanderlaufen.

## Entscheidungstreiber

* Sichtbare Identität (Browser-Titel, Topbar, CLI, README, API-Doku) soll
  einheitlich gMA2PiControl sein.
* Bestehende Installationen und Deploy-Pfade müssen ohne Migration
  weiterlaufen.
* Der Name soll nur an einer Stelle je Laufzeit definiert sein, damit er nicht
  in Templates und Logs auseinanderläuft.
* Der technische Paketname bleibt für Importe, Tests und Werkzeuge stabil.

## Betrachtete Optionen

* Vollständige Umbenennung von Paket, Unit, Benutzer und Pfaden.
* Nur der sichtbare Produktname ändert sich; technische Bezeichner bleiben.
* Alias-Paket `gma2picontrol`, das `ma2pi` weiterreicht.

## Entscheidung

Der sichtbare Produktname ist **gMA2PiControl**. Er wird je Laufzeit über eine
Konstante geführt (`PRODUCT_NAME` in `ma2pi/__init__.py`, `PRODUCT_NAME` in
`web/src/lib/brand.ts`) und für Browser-Titel, Topbar, PIN-Gate, `--version`,
`--help`, Start-/Stopp-Log, API-Dokumentation und die systemd-`Description`
verwendet. Python-Paket, Entrypoint, Unit-Name, Service-Benutzer,
StateDirectory, Passwortdatei, Recovery-SSID und API-Routen bleiben `ma2pi`.

### Konsequenzen

* Gut, weil bestehende Installationen, Pfade und Deploy-Skripte unverändert
  funktionieren.
* Gut, weil der Produktname an genau einer Stelle je Laufzeit geändert werden
  kann.
* Schlecht, weil Dokumentation und Support beide Namen nebeneinander kennen
  müssen; das README nennt die Trennung ausdrücklich.
* Schlecht, weil Log-Ausgaben und Prozessnamen weiterhin `ma2pi` enthalten und
  bei der Fehlersuche vom Produktnamen abweichen.

### Bestätigung

Die Entscheidung gilt als bestätigt, wenn das README den Produktnamen trägt,
`--version` mit `gMA2PiControl` beginnt, die Web-Oberfläche den Namen zeigt und
`ma2pi.service` sowie das StateDirectory unverändert starten.

## Vor- und Nachteile der Optionen

### Vollständige Umbenennung

* Gut, weil ein einziger Name in Code, Doku und Betrieb gilt.
* Schlecht, weil Imports, Entrypoint, Unit, Benutzer, Pfade und bestehende
  Installationen migriert werden müssen.

### Nur sichtbarer Produktname

* Gut, weil kein Migrationsaufwand und kein Deploy-Bruch entsteht.
* Schlecht, weil zwei Namen gepflegt und erklärt werden müssen.

### Alias-Paket

* Gut, weil der neue Name importierbar wäre.
* Schlecht, weil zwei Paketnamen, zwei Entrypoints und doppelte Tests entstehen,
  ohne dass die Oberfläche davon profitiert.

## Weitere Informationen

Die Oberfläche verwendet lokale Schriften und Assets; das bleibt durch
[0011. Frontend mit Svelte 5 und Vite](0011-frontend-mit-svelte-5-und-vite.md)
vorgegeben. Die sichtbare Gestaltung orientiert sich an
[sustain-vt.de](https://www.sustain-vt.de).
