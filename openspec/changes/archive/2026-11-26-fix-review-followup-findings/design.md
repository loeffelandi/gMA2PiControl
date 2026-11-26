# Design

## Context

Nach Umsetzung, Test-Deploy und Archivierung von `fix-code-review-findings`
(Commit `5ea80e2`) haben die beiden spezialisierten Nach-Review-Läufe auf dem
Backend- und Frontend-Diff 26 konkrete Detail- und Randfallbefunde ermittelt.
Keiner erfordert neue Konfigurationsschlüssel oder Protokolländerungen, aber
mehrere betreffen reale Bedienabläufe (Seitenwechsel mit aktivem Feedback,
aufeinanderfolgende Learn-Läufe, Formularvalidierung im Dialog, PIN-Sessions im
Mehr-Browser-Betrieb).

## Goals / Non-Goals

**Goals:**

- Alle 26 Befunde aus dem Nach-Review ohne API-Bruch schließen und mit gezielten
  Regressions-Tests absichern.
- Volle Kompatibilität zu parallel laufenden Changes (`resolve-combined-executors`,
  `add-per-device-led-protocols`, `device-profile-files`).

**Non-Goals:**

- Keine Zusammenlegung von Mapping- und Geräte-Tab zu einem neuen Store-Modell
  (bleibt `mapping-device-feature-parity`).
- Keine Änderung am offenen Show-LAN-Modell oder den `[led]`/`[feedback]`-Schemas.

## Decisions

### D1: `"current"`-Blöcke und ungepaarte Releases (`feedback.py`, `playback.py`)

- **Entfernen der fehlerhaften `_known_current_page`-Sperre**: Weil
  `_request_block()` vor jeder Einzelanfrage `_drain_responses()` leert und immer
  höchstens eine Anfrage gleichzeitig offen hält, beantwortet eine eintreffende
  Antwort auf einen `"current"`-Request die aktuelle Master-Page — auch dann,
  wenn diese zufällig mit einer Seite in `_fixed_pages` übereinstimmt. Die
  Prüfung beschränkt sich daher wieder auf `items_type` und Executor-Bereich
  (bzw. in Kombination mit `resolve-combined-executors` auf die dort gemessene
  Seitenbasis).
- **Kein verwaistes `playback_button(..., False)`**: Ist `event.kind == "key"`
  und `event.value < 0.5`, gibt `PlaybackRouter.handle()` bei fehlendem Eintrag
  in `self._pressed`:
  - `False` zurück, wenn `engine.is_held(device, control)` gilt oder auf der
    aktiven Bank ein `layer.keys`-Override liegt;
  - `True` (still verworfen, ohne Frame und ohne `_maybe_page`), wenn das Control
    auf ein Playback-Button-Ziel zeigt, aber kein offener Press vorlag (z. B.
    nach `cleanup()`, `on_connection_lost()` oder Lernende).

### D2: Kurzes Drain-Fenster vor `rawmidi_drop_output` & `install.sh`-Modi (`midi_input.py`, `led_output.py`, `deploy/install.sh`)

- `SNDRV_RAWMIDI_IOCTL_DROP` leert den ALSA-Ausgabepuffer sofort und verwirft
  dadurch das unmittelbar zuvor geschriebene 3-Byte-`DISABLE`-Frame (`9F 7F 7E`)
  der ASL. `RealMidiHandle.close()` (und der Standalone-Pfad in `LedOutput.close()`)
  prüft zuerst `rawmidi_output_free`: Sind Bytes ausstehend, wartet `close()` in
  kurzen Schritten höchstens `30 ms` auf deren Abfluss; nur wenn danach weiter
  Bytes stehen (gestautes Gerät), verwirft `rawmidi_drop_output()` den Rest
  sofort. Damit erhält eine gesunde ASL zuverlässig `DISABLE` (< 2 ms), während
  der Dienststopp bei gestautem Gerät weiter unter `0,1 s` bleibt.
- `deploy/install.sh` führt vor bzw. nach `chown -R root:root "${APP_DIR}"` ein
  `chmod -R u+rwX,go+rX "${APP_DIR}" "${VENV_DIR}"` aus, damit restriktive
  `umask`-Werte beim Bauen den Dienstbenutzer `ma2pi` nicht aussperren.

### D3: Zweiphasige `encoder_id`-Auflösung, Geräte-API & Activity-Kurztext (`config.py`, `web/serialize.py`, `web/devices.py`, `activity.py`)

- `_parse_profiles()` sammelt in einem ersten Durchlauf alle expliziten
  Encoder-IDs (`encoders`, `midi_encoders`, `controls[].encoder_id` sowie
  `encoder.<N>`-Suffixe) über **alle** Profile hinweg und vergibt erst im
  zweiten Durchlauf freie `next_auto_id`-Werte an unbenannte `relative-encoder`.
- `serialize.py` schreibt `encoder_id` immer dann aus, wenn
  `ctrl.id != f"encoder.{ctrl.encoder_id}"`.
- `web/devices.py` liefert `encoder_id` in `controls.inventory` mit und nutzt
  für `device_summary()` dieselbe Sortierung und `claimed_paths`-Logik wie
  `select_devices()` und `select_midi_devices()`.
- `describe_midi()` zerlegt zusammenhängende 3-Byte-Note-On-Pakete: beginnt ein
  Paket mit `ENABLE` (`9F 7F 7F`) und folgen Kanal-/Noten-Frames (ASL-LED), wird
  die Ziel-Note samt Farb-/Helligkeitswert beschrieben; reines `ENABLE`/`DISABLE`
  erscheint als `"led enable"` bzw. `"led disable"`.

### D4: Learn-Freigabe, Rasten-Entprellung, `ScreenHelper` & Infrastruktur (`__main__.py`, `device_learn.py`, `screen_helper.py`, `network.py`, `recovery.py`, `web/events.py`, `logging_setup.py`)

- Da `LearnManager` während `learn.active` Eingaben aller Geräte abfängt, ruft
  `learn.on_start` unabhängig vom `device`-Filter immer `playback.cleanup()` und
  `engine.cleanup()` auf (`device_learn.on_start` bleibt gerätebezogen).
- `DeviceLearnManager`: Innerhalb von `SWEEP_SETTLE_SECONDS` (`0.35 s`) nach dem
  Erfassen eines Nicht-Button-Controls (`fader`, `poti`, `encoder`,
  `relative-encoder`) werden weitere Nachrichten derselben `(channel, note)` auch
  bei identischer Velocity (z. B. `127, 127` beim Relativ-Encoder oder Anschlag)
  absorbiert; `_conflict()` prüft defensiv `self.config.devices.get(device)`.
- `ScreenHelper` speichert den laufenden Resolver-Task sowie den zuletzt
  angeforderten `pending_screen`, sendet nach Abschluss den aktuellsten Wert und
  bricht den Task in `close()` sauber ab, ohne einen geschlossenen Socket wieder
  zu öffnen.
- `NetworkService.resume()` begrenzt `remaining` auf `min(self._confirm_timeout, ...)`;
  `RecoveryService._save_locked()` rollt bei einem Schreibfehler von
  `recovery.json` den Live-Zustand in NetworkManager auf `previous` zurück;
  `events_handler` versieht `ws.send_json` mit einem Timeout bzw. bricht bei
  `dropped` ab; `_SECRET_KEYS` berücksichtigt maskierte Anführungszeichen (`\"`, `\'`).

### D5: Svelte-5-UI-Konsistenz & gezielter PIN-Session-Widerruf (`web/__init__.py`, `web/src/**`)

- **`put_config` (`web/__init__.py`)**: `sessions.clear()` und `bus.close_all()`
  laufen nur, wenn `(config.web.pin_enabled, config.web.pin)` sich tatsächlich
  gegenüber `(prev_pin_enabled, prev_pin)` geändert hat.
- **`MappingPage.svelte`**: `learnStore.subscribe` dedupliziert `previousLearn`
  per Referenz/Status, `startLearn` übernimmt zunächst das aktive Start-Objekt
  vor Freigabe von `applyLearn`; `modifierRows` mit `kind === 'hardkey'` und
  leerem `hardkey` blockieren `save()` mit klarer Fehlermeldung; `encoderIds`,
  `deviceForControl` und `applyLearn` nutzen `inventory[].encoder_id`; unbelegte
  gebankte Wert-Controls zeigen `–` statt Note `0`.
- **`App.svelte`, `DevicesPage.svelte`, `LearnPanel.svelte`, `AssignDialog.svelte`**:
  - `App.svelte` übergibt `store={statusStore}` an `DevicesPage` → `LearnPanel`
    und löscht ein altes `versionError` nach erfolgreichem `refreshAuth`/`checkVersion`.
  - `LearnPanel.applyStatus` setzt `startedSession = false`, sobald
    `!next?.active` gilt, und formatiert `ApiError.detail`.
  - `DevicesPage.selectDevice()` schließt `dialog` und `showLearn` (inkl.
    sauberem Unmount/Cancel von `LearnPanel`) und setzt `learnControl = null`.
  - `AssignDialog` übergibt `encoderMode`, verlangt bei `encoderMode === 'attribute'`
    einen nichtleeren Attributnamen, validiert `Page` (`"current"` oder Zahl
    `>= 1`) und `step` (`>= 1` mit `required`), aktualisiert `encoderScreen` beim
    Slot-Wechsel aus einer übergebenen `screenEncoders`-Map, behandelt
    `dialogInherited` korrekt für `ma_page`, Teil-Overrides und Mehrfachauswahl
    und berücksichtigt/bereinigt `mapping.modifiers` beim Bearbeiten/Löschen.
- **`NetworkPage.svelte` & `StatusPage.svelte` (`status.ts`)**:
  - `NetworkPage` merkt sich `wasPending = pending !== null` **vor**
    `setPending(event.pending)` und ruft `load(false, wasPending)` auf, damit
    Formularfelder nach Rollback synchronisiert werden.
  - `status.ts` übernimmt `info.generation` bei `status`-Snapshots in
    `configGeneration`; `StatusPage` scrollt anhand von `entries.at(-1)?.seq`
    statt `entries.length` und erkennt Replugs anhand neuer Einträge mit
    `entry.seq > lostSeqByDevice[name]`.

## Risks / Trade-offs

- **[30-ms-Drain-Fenster beim MIDI-Schließen]** → Im Normalfall (< 2 ms USB-Drain)
  kehrt die Prüfung beim ersten Poll sofort zurück; selbst bei 2 gestauten
  MIDI-Geräten beträgt die Obergrenze zusammen `60 ms` (weit unter dem
  5-s-Shutdown-Budget).
