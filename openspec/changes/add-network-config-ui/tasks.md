# Tasks

## 1. NetworkManager-Adapter und Datenmodell

- [x] 1.1 `ma2pi/network.py` mit den Datentypen für Schnittstelle, aktuellen Zustand, Kandidat, Pending-Änderung und Fehlercodes anlegen; das Modell enthält noch keine Prozessaufrufe. Verifikation: Unit-Tests serialisieren und deserialisieren ein vollständiges Statusobjekt ohne Verlust von `None`-Werten und DNS-Listen.
- [x] 1.2 Einen `nmcli`-Adapter mit `asyncio.create_subprocess_exec`, festen Argumenten, `LC_ALL=C`, Timeout und austauschbarem Runner implementieren: Geräte lesen, Ethernet-Schnittstelle nach Standardroute/verbunden/erster auswählen, Modus und aktuelle IPv4-Werte lesen. Verifikation: Tests mit gespeicherten `nmcli`-Ausgaben prüfen Auswahl, DHCP/Statisch-Erkennung, Punktnotation und Fehler bei fehlendem Backend.
- [x] 1.3 Profilwahl und IPv4-Schreiboperationen implementieren: aktives Profil verwenden, sonst passendes Ethernet-Profil, sonst `ma2pi-<interface>` anlegen; `modify --temporary` für Aktivierung, `modify` für Persistenz, `connection up`, `--temporary`-Rollback und Profil-Löschung bei `created_profile`. Verifikation: Fake-Runner-Tests prüfen die exakten Argumente für DHCP, statisch, Bestätigen und Rollback sowie den Erhalt nicht-IPv4-bezogener Profilfelder.
- [x] 1.4 Validierung implementieren: IPv4-Adresse, zusammenhängende Subnetzmaske, Prefix 1–32, Netz-/Broadcast-Grenzen, Gateway im Subnetz, 0–3 DNS-Einträge, lokale Doppelbelegung, Modus-Kombination und Link-Zustand. Verifikation: Tabellentests decken gültige und ungültige Fälle inklusive `/31`, `/32`, leeres Gateway, leeres DNS und belegte Adresse ab; jeder Fehler nennt das Feld.

## 2. Pending-Zustand und Zustandsmaschine

- [x] 2.1 Persistenz für `/var/lib/ma2pi/network-pending.json` mit atomarem Schreiben (`fsync`, `os.replace`, Modus 0600) und Schema-Version anlegen; vorherige rohe IPv4-Eigenschaften, Kandidat, UUID, Deadline, Phase und Fehler speichern. Verifikation: Tests für Roundtrip, Abbruch vor dem Ersetzen, Rechte und beschädigte Datei.
- [x] 2.2 Wiederanlauf-Logik implementieren: `activating` und `failed` rollen zurück, `rolling_back` setzt den Rollback fort, `confirmed` löscht die Datei, `awaiting_confirmation` setzt den Timer fort oder rollt nach Ablauf zurück. Verifikation: Tests mit manipulierten Pending-Dateien und fester Uhr prüfen jede Phase.
- [x] 2.3 Zustandsmaschine mit `asyncio.Lock`, 202-Vorlauf, Aktivierungs-Polling (20 s), Bestätigungsfenster (180 s), Bestätigen, manuellem Rollback, Aktivierungsfehler und Rollback-Fehler implementieren. Verifikation: Tests mit Fake-Backend und steuerbarer Uhr prüfen `idle → activating → awaiting_confirmation → confirmed/rolled_back`, `409 apply_busy` und `409 no_pending`.
- [x] 2.4 `last_result` und den Fehlerzustand nach Rollback pflegen, ohne die aktive Konfiguration zu verändern. Verifikation: Test prüft, dass ein fehlgeschlagener Apply die vorherigen Werte als `current` meldet und `last_result` den Fehler enthält.

## 3. HTTP-API und Live-Ereignisse

- [x] 3.1 Service in `create_app()` verdrahten und `GET /api/network`, `POST /api/network/validate`, `PUT /api/network`, `POST /api/network/confirm` und `POST /api/network/rollback` implementieren; Feldbezogene 422-Antworten und die Fehlercodes aus dem Design verwenden. Verifikation: aiohttp-Tests prüfen Status, Payload, 202-Vorlauf, 409-Fälle, 415/403 und `503 network_unavailable`.
- [x] 3.2 PIN-Schutz und Request-Guard für alle neuen Pfade sicherstellen, insbesondere Bestätigen nach einem Adresswechsel ohne gültige Session. Verifikation: Tests prüfen `401 pin_required` ohne Session, Erfolg nach erneutem Login und unveränderte offene Änderung bei abgelehntem Aufruf.
- [x] 3.3 `network`-Ereignisse über den bestehenden EventBus veröffentlichen und den Status bei Apply-Start, Aktivierung, Bestätigung, Rollback und Fehler aktualisieren. Verifikation: WebSocket-Test mit zwei Clients prüft Empfang und dass der Status nach einem simulierten Reconnect vollständig nachladbar ist.
- [x] 3.4 `docs/api.md` um Netzwerk-Endpunkte, Payloads, Fehlercodes, Ziel-URL und Bestätigungsablauf erweitern. Verifikation: Jeder dokumentierte Aufruf wird gegen die implementierten Handler geprüft; die Beispiele sind gültiges JSON.

## 4. Svelte-Oberfläche

- [x] 4.1 Typen und Methoden für `GET /api/network`, Vorschau, Apply, Confirm und Rollback in `web/src/lib/api.ts` ergänzen. Verifikation: Vitest-Tests prüfen Request-Methode, Header, Body und die Behandlung von `409`/`503`.
- [x] 4.2 `NetworkPage.svelte` mit Statuskarte, Umschalter DHCP/Statisch, Feldern für Adresse, Subnetzmaske, Gateway und DNS sowie Vorschau und Feldmeldungen bauen. Verifikation: Komponententests prüfen Vorbelegung, Deaktivierung der statischen Felder im DHCP-Modus, Validierungsfehler und die Anzeige der tatsächlich vergebenen DHCP-Adresse.
- [x] 4.3 Warnung vor dem Anwenden, Ziel-URL und erneute PIN-Anmeldung umsetzen; die Warnung bei eigener Verbindung über die verwaltete Schnittstelle hervorheben. Verifikation: Komponententest prüft den Dialogtext, die Ziel-URL und dass ohne Bestätigung kein Apply ausgelöst wird.
- [x] 4.4 Pending-Ansicht mit Countdown, „Bestätigen“ und „Zurückrollen“ bauen; nach Adresswechsel den Status neu laden und bei Bedarf die PIN-Sperre zeigen. Verifikation: Tests mit Fake-Timern prüfen Countdown, Bestätigen, manuellen Rollback und die Anzeige von `last_result` nach einem Rollback.
- [x] 4.5 Seite in `App.svelte` einhängen und `StatusStore` um das `network`-Ereignis erweitern. Verifikation: Komponententest prüft Navigation, Live-Update und Reconnect nach Abbruch.
- [ ] 4.6 README-Abschnitt **Netzwerk** mit Bedienung, Warnung, Ziel-URL, PIN-Neuanmeldung und Rollback schreiben. Verifikation: Die beschriebenen Schritte werden auf einem Testsystem einmal ausgeführt und die Texte stimmen mit den UI-Beschriftungen überein.

## 5. Deployment und Berechtigungen

- [ ] 5.1 `deploy/50-ma2pi-network.rules` mit der auf zwei NetworkManager-Aktionen begrenzten Polkit-Regel für `ma2pi` anlegen. Verifikation: `pkaction`/`busctl` auf dem Pi zeigt, dass die Aktionen erlaubt sind und andere NetworkManager-Aktionen nicht.
- [ ] 5.2 `install.sh` um die Prüfung von `nmcli`, NetworkManager-Dienst und Polkit sowie die Installation der Regel erweitern; bei fehlenden Paketen mit Paket-Hinweis abbrechen. Verifikation: Test auf Trixie mit und ohne NetworkManager; die Installation ist idempotent und die Regel hat Modus 0644, root:root.
- [x] 5.3 ADR-0017 „Netzwerkkonfiguration über NetworkManager mit Bestätigung und Rollback“ anlegen und in `docs/adr/README.md` verlinken. Verifikation: ADR folgt der Vorlage, nennt Alternativen und Konsequenzen und ist im Design referenziert.
- [ ] 5.4 README-Anforderungen und Update-/Rollback-Abschnitt um NetworkManager, Polkit und die neue Seite ergänzen; die systemd-Härtung ausdrücklich als unverändert dokumentieren. Verifikation: `systemd-analyze verify deploy/ma2pi.service` ist grün und die dokumentierten Befehle laufen auf dem Pi.

## 6. Integration und Abnahme

- [x] 6.1 Integrationstest mit Fake-Backend über die HTTP-API: Status lesen, Vorschau, statisch anwenden, bestätigen, auf DHCP wechseln und zurückrollen. Verifikation: Der Test deckt alle Phasen und die Persistenz der bestätigten Konfiguration ab.
- [x] 6.2 Integrationstest für Aussperrschutz: Apply ohne Bestätigung lässt den Timer ablaufen, Rollback stellt die vorherige Konfiguration wieder her und ein Dienstneustart im Fenster setzt den Timer korrekt fort. Verifikation: Test mit steuerbarer Uhr und simuliertem Neustart ist grün.
- [ ] 6.3 Test auf dem Pi: DHCP → statisch → neue Adresse im Browser öffnen, PIN eingeben, bestätigen; danach statisch → DHCP. Verifikation: Die tatsächlich vergebene Adresse, Gateway und DNS werden im UI korrekt angezeigt; die MA2-Verbindung baut sich nach dem Wechsel wieder auf.
- [ ] 6.4 Rollback auf dem Pi: Änderung ohne Bestätigung starten, 180 s warten, alte Adresse erneut öffnen und den Status prüfen. Verifikation: Die alte Adresse ist erreichbar, die offene Änderung ist entfernt und `last_result` beschreibt den Rollback.
- [ ] 6.5 Sicherheits- und Härtungsabnahme: PIN-Pflicht, JSON-/Header-Pflicht, keine Geheimnisse in Antworten/Logs, fehlende Polkit-Berechtigung führt zu keiner Teiländerung, Dienst läuft weiter als `ma2pi`. Verifikation: Tests und ein Lauf auf dem Pi protokollieren die Ergebnisse.
- [x] 6.6 Vollständige Suite (`pytest`, `npm run check`, `npm run build`, `openspec validate --strict`) ausführen und das Ergebnis dokumentieren. Verifikation: Alle Tests und die strikte OpenSpec-Validierung sind grün.
- [x] 6.7 Notfall-Adresse implementieren: bei fehlgeschlagenem Rollback `192.168.178.254/24` ohne Gateway/DNS anwenden und als `last_result` melden; `POST /api/network/emergency` und eine bestätigte UI-Aktion ergänzen. Verifikation: Tests decken fehlgeschlagenen Rollback, manuellen Notfallbefehl und den Unterschied zu einem kurzen Verbindungsabbruch ab.
- [x] 6.8 Notfall-Verhalten in README, API-Referenz und ADR-0017 dokumentieren; erklären, dass kein Neustart nötig ist und `192.168.178.254` nur im Subnetz `192.168.178.0/24` ohne Client-Umkonfiguration erreichbar ist. Verifikation: Dokumentation und UI-Warnung nennen dieselbe Adresse, Maske und Einschränkung.

## Workflow follow-up

- Proposal, Spec, Design, Tasks und ADR-0017 zur Review vorlegen und Freigabe abwarten.
- Erst nach Freigabe implementieren und Tasks abhaken.
- Change nach bestandener Abnahme archivieren und die Haupt-Spec `network-config` synchronisieren.
