# 0005. Rate-Limiting gegen onPC-Lockup

* Datum: 2026-11-25
* Entscheider: Andreas
* Konsultiert: –
* Informiert: –

## Status

Proposed

## Kontext und Problemstellung

Die grandMA2 onPC kann bei zu hohen Request-Raten vollständig blockieren. Das
Chataigne-Referenzmodul drosselt deshalb Fader-Werte pro Executor mit einem
dynamischen Mindestabstand und einem Watchdog, der den letzten Zielwert
nachliefert. Für diesen Daemon entstehen Lastspitzen vor allem durch vier
Encoder, die bei schnellem Drehen viele Detents liefern, sowie durch
Hardkey-Releases, die nicht verloren gehen dürfen.

## Entscheidungstreiber

* onPC darf unter Last nicht blockieren
* Kein verlorener Hardkey-Release, keine hängenden Modifier
* Encoder-Deltas müssen auch bei Drosselung vollständig ankommen
* Begrenzter Speicher und begrenzte Latenz
* Nachvollziehbare, konfigurierbare Grenzen

## Betrachtete Optionen

* Kein Limit
* Fester Sleep zwischen allen Frames
* Globaler Token-Bucket
* Chataigne-artiges dynamisches Per-Stream-Limit
* Globaler Token-Bucket plus dynamisches Per-Encoder-Limit (Hybrid)

## Entscheidung

Es wird ein Hybrid aus globalem Token-Bucket und dynamischem Per-Encoder-Limit
umgesetzt:

* Global: Default 25 Nachrichten/s, Burst 10, konfigurierbar im Bereich 5–40.
  Jeder Anwendungs-Frame verbraucht ein Token; Keepalive hat höchste Priorität.
* Pro Encoder: Mindestabstand `25 ms + 2,4 ms × Anzahl aktiver Encoder`.
  Idle-Watchdog `40 ms + 2,2 ms × Anzahl aktiver Encoder`, damit der letzte
  akkumulierte Delta sicher ankommt. Die Formeln folgen dem Chataigne-Vorbild.
* Steuer-Frames (Hardkey-Press/Release, Kommandos, `closeConnection`) haben
  Vorrang vor Encoder-Flushes. Releases und Kommandos werden nie verworfen.
* Encoder-Deltas werden pro Ziel akkumuliert. Bei Sättigung wird weiter
  akkumuliert, aber der offene Delta auf `max_pending_delta` gekappt und das
  Kappen protokolliert.
* Eine Backpressure-Wache halbiert die globale Rate vorübergehend, wenn die
  Kontroll-Queue über zwei Sekunden mehr als 100 Einträge hält oder der
  WebSocket-Sendepuffer 64 KiB überschreitet; nach zehn Sekunden unterhalb der
  Schwelle kehrt die Rate zum konfigurierten Wert zurück.

### Konsequenzen

* Gut, weil Lastspitzen abgefedert werden, ohne Releases zu verlieren.
* Gut, weil Encoder trotz Drosselung kumulativ vollständig ankommen.
* Gut, weil die Grenzen konfigurierbar und testbar sind.
* Schlecht, weil Encoder-Reaktionen unter Last um bis zu ~40 ms verzögert werden.
* Schlecht, weil die dynamische Formel zusätzliche Zustände und Tests benötigt.
* Schlecht, weil ein bereits blockierter onPC nicht garantiert wieder frei wird; die Wache reduziert nur das Risiko.

### Bestätigung

Accepted, wenn ein Stresstest mit vier gleichzeitig schnell gedrehten Encodern
und zusätzlichem Hardkey-Spam über zehn Minuten keine Blockade der onPC erzeugt
und kein Release verloren geht. Falls die onPC früher blockiert, wird die
Default-Rate auf 20/s gesenkt und die ADR aktualisiert.

## Vor- und Nachteile der Optionen

### Kein Limit

* Gut, weil minimale Latenz.
* Schlecht, weil die onPC reproduzierbar blockieren kann.

### Fester Sleep

* Gut, weil einfach.
* Schlecht, weil unnötig langsam bei wenigen Frames und zu schnell bei vielen.

### Globaler Token-Bucket

* Gut, weil harte Obergrenze und faire Verteilung.
* Schlecht, weil ein einzelner Encoder alle Tokens verbrauchen und andere aushungern kann.

### Dynamisches Per-Stream-Limit

* Gut, weil nahe am Chataigne-Vorbild und gut erprobt.
* Schlecht, weil ohne globale Obergrenze viele Streams die Gesamtrate sprengen.

### Hybrid

* Gut, weil harte Obergrenze plus faire Per-Encoder-Drosselung.
* Gut, weil Releases priorisiert bleiben.
* Schlecht, weil mehr Konfiguration und Testfälle nötig sind.

## Weitere Informationen

* Chataigne: `update()` mit `rateLimitArray`, `commandSetExecutorValue`
* Verwandt: ADR-0001, ADR-0002, ADR-0006
