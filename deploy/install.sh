#!/usr/bin/env bash
# Idempotent installation for Raspberry Pi OS Trixie / Debian 13.
# Run as root from a checkout:  sudo deploy/install.sh
set -euo pipefail

APP_USER="ma2pi"
APP_GROUP="ma2pi"
BASE_DIR="/opt/ma2pi"
APP_DIR="${BASE_DIR}/app"
VENV_DIR="${BASE_DIR}/.venv"
CONFIG_DIR="/etc/ma2pi"
STATE_DIR="/var/lib/ma2pi"
BACKUP_DIR="${STATE_DIR}/backups"
SERVICE_FILE="/etc/systemd/system/ma2pi.service"
UDEV_FILE="/etc/udev/rules.d/99-ma2pi.rules"
POLKIT_FILE="/etc/polkit-1/rules.d/50-ma2pi-network.rules"
POLKIT_POWER_FILE="/etc/polkit-1/rules.d/50-ma2pi-power.rules"
JOURNALD_DIR="/etc/systemd/journald.conf.d"
JOURNALD_FILE="${JOURNALD_DIR}/50-ma2pi-volatile.conf"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
    echo "install.sh muss als root laufen (sudo deploy/install.sh)." >&2
    exit 1
fi

if [[ ! -x /usr/bin/python3 ]]; then
    echo "/usr/bin/python3 fehlt. Installiere python3 und python3-venv." >&2
    exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
    echo "nmcli fehlt. Installiere NetworkManager: sudo apt install network-manager" >&2
    exit 1
fi
if ! systemctl is-active --quiet NetworkManager.service; then
    echo "NetworkManager läuft nicht. Aktiviere ihn: sudo systemctl enable --now NetworkManager.service" >&2
    exit 1
fi
if [[ ! -d /etc/polkit-1/rules.d ]]; then
    echo "Polkit fehlt. Installiere policykit-1/polkitd, damit die Netzwerkseite Änderungen anwenden darf." >&2
    exit 1
fi

if ! getent group "${APP_GROUP}" >/dev/null; then
    groupadd --system "${APP_GROUP}"
fi
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${APP_GROUP}" --home-dir "${BASE_DIR}" \
        --shell /usr/sbin/nologin "${APP_USER}"
fi

install -d -o root -g root -m 0755 "${BASE_DIR}"
install -d -o root -g root -m 0755 "${APP_DIR}"
install -d -o root -g "${APP_GROUP}" -m 0750 "${CONFIG_DIR}"
install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0750 "${STATE_DIR}"
install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0750 "${BACKUP_DIR}"

# Application code (without tests, venv, caches or local config).
rm -rf "${APP_DIR}/ma2pi"
cp -a "${REPO_DIR}/ma2pi" "${APP_DIR}/ma2pi"
cp -a "${REPO_DIR}/pyproject.toml" "${APP_DIR}/pyproject.toml"
if [[ -f "${REPO_DIR}/README.md" ]]; then
    cp -a "${REPO_DIR}/README.md" "${APP_DIR}/README.md"
fi

WEB_DIST="${WEB_DIST:-${REPO_DIR}/web/dist}"
if [[ ! -f "${WEB_DIST}/index.html" ]]; then
    echo "web/dist fehlt. Baue die Oberfläche zuerst:" >&2
    echo "    cd ${REPO_DIR}/web && npm ci && npm run build" >&2
    echo "Oder kopiere den gebauten Ordner auf den Pi und setze WEB_DIST:" >&2
    echo "    sudo WEB_DIST=/pfad/zu/dist deploy/install.sh" >&2
    exit 1
fi
rm -rf "${APP_DIR}/web/dist"
install -d -o root -g root -m 0755 "${APP_DIR}/web"
cp -a "${WEB_DIST}" "${APP_DIR}/web/dist"

find "${APP_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} +
chmod -R u+rwX,go+rX "${APP_DIR}"
chown -R root:root "${APP_DIR}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    /usr/bin/python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/python" -m pip install --quiet --upgrade pip
"${VENV_DIR}/bin/python" -m pip install --quiet "${APP_DIR}"
chmod -R u+rwX,go+rX "${VENV_DIR}"
chown -R root:root "${VENV_DIR}"

install -m 0644 "${REPO_DIR}/deploy/ma2pi.service" "${SERVICE_FILE}"
install -m 0644 "${REPO_DIR}/deploy/99-ma2pi.rules" "${UDEV_FILE}"
install -m 0644 -o root -g root "${REPO_DIR}/deploy/50-ma2pi-network.rules" "${POLKIT_FILE}"
install -m 0644 -o root -g root "${REPO_DIR}/deploy/50-ma2pi-power.rules" "${POLKIT_POWER_FILE}"

# Reduce SD-card writes: the Pi is switched off by pulling the plug.
# 1. Keep the systemd journal in RAM.
install -d -o root -g root -m 0755 "${JOURNALD_DIR}"
JOURNALD_CHANGED=0
if ! cmp -s "${REPO_DIR}/deploy/journald-ma2pi.conf" "${JOURNALD_FILE}" 2>/dev/null; then
    install -m 0644 -o root -g root "${REPO_DIR}/deploy/journald-ma2pi.conf" "${JOURNALD_FILE}"
    JOURNALD_CHANGED=1
fi

# 2. Make sure the root file system is mounted with noatime (Raspberry Pi OS
#    already does).  /etc/fstab is only touched when the root line is a plain
#    ext4 entry without it, and a backup is kept next to it.
ensure_noatime() {
    local fstab="/etc/fstab" tmp
    if [[ ! -f "${fstab}" ]]; then
        return 0
    fi
    if [[ "$(findmnt -no OPTIONS / 2>/dev/null || true)" == *noatime* ]]; then
        echo "Root-Dateisystem: noatime ist bereits aktiv."
        return 0
    fi
    if ! awk '!/^[[:space:]]*#/ && NF >= 4 && $2 == "/" && $3 == "ext4" { found = 1 } END { exit !found }' "${fstab}"; then
        echo "Hinweis: kein ext4-Eintrag für / in ${fstab}; noatime bitte selbst setzen." >&2
        return 0
    fi
    tmp="$(mktemp)"
    awk '
        !/^[[:space:]]*#/ && NF >= 4 && $2 == "/" && $3 == "ext4" && $4 !~ /(^|,)noatime(,|$)/ {
            $4 = $4 ",noatime"
        }
        { print }
    ' "${fstab}" > "${tmp}"
    if [[ "$(diff "${fstab}" "${tmp}" | grep -c '^>')" -ne 1 ]]; then
        echo "Hinweis: ${fstab} nicht angepasst (unerwartetes Format); noatime bitte selbst setzen." >&2
        rm -f "${tmp}"
        return 0
    fi
    cp -a "${fstab}" "${fstab}.ma2pi-backup"
    cat "${tmp}" > "${fstab}"
    rm -f "${tmp}"
    mount -o remount,noatime / || echo "Hinweis: Remount fehlgeschlagen; noatime gilt nach dem nächsten Neustart." >&2
    echo "Root-Dateisystem: noatime in ${fstab} ergänzt (Backup: ${fstab}.ma2pi-backup)."
}
ensure_noatime

# 3. Swap on the SD card is not changed; only point it out.
if systemctl is-active --quiet dphys-swapfile.service 2>/dev/null; then
    echo "Hinweis: dphys-swapfile schreibt auf die SD-Karte. Abschalten (nur bei genug RAM):" >&2
    echo "    sudo systemctl disable --now dphys-swapfile.service" >&2
fi

# Never overwrite an existing configuration or password.  A legacy
# /etc/ma2pi/config.toml is migrated once into the writable state directory by
# the application's config-store helper, which also sets modes and owners.
if [[ ! -f "${STATE_DIR}/config.toml" && ! -f "${CONFIG_DIR}/config.toml" ]]; then
    install -m 0640 -o root -g "${APP_GROUP}" \
        "${REPO_DIR}/config.toml" "${CONFIG_DIR}/config.toml"
    echo "Beispielkonfiguration nach ${CONFIG_DIR}/config.toml kopiert."
fi
if [[ ! -f "${STATE_DIR}/ma2pi.password" && ! -f "${CONFIG_DIR}/ma2pi.password" ]]; then
    install -m 0640 -o root -g "${APP_GROUP}" /dev/null \
        "${CONFIG_DIR}/ma2pi.password"
    echo "Bitte das onPC-Passwort in ${CONFIG_DIR}/ma2pi.password eintragen (leer lassen, wenn der Benutzer kein Passwort hat)." >&2
fi

APP_USER="${APP_USER}" "${VENV_DIR}/bin/python" - <<'PY'
import os

from ma2pi.config_store import ConfigPaths, ensure_layout, migrate

owner = os.environ["APP_USER"]
paths = ConfigPaths()
ensure_layout(paths, owner=owner)
migrate(paths, owner=owner)
ensure_layout(paths, owner=owner)
PY

if [[ ! -f "${STATE_DIR}/ma2pi.password" ]]; then
    install -m 0600 -o "${APP_USER}" -g "${APP_GROUP}" /dev/null \
        "${STATE_DIR}/ma2pi.password"
    echo "Bitte das onPC-Passwort in ${STATE_DIR}/ma2pi.password eintragen (leer lassen, wenn der Benutzer kein Passwort hat)." >&2
fi

systemctl daemon-reload
if [[ "${JOURNALD_CHANGED}" -eq 1 ]]; then
    systemctl restart systemd-journald.service
    echo "Journal läuft jetzt im RAM (Storage=volatile). Ein altes Journal liegt noch in /var/log/journal;"
    echo "    zum Freigeben: sudo rm -rf /var/log/journal"
fi
udevadm control --reload-rules
udevadm trigger --subsystem-match=input --subsystem-match=sound
systemctl enable ma2pi.service

echo
echo "Installation abgeschlossen."
echo "1. ${STATE_DIR}/config.toml anpassen (Host, Benutzer, Geräte-IDs)."
echo "2. ${STATE_DIR}/ma2pi.password befüllen."
echo "3. sudo -u ${APP_USER} ${VENV_DIR}/bin/python -m ma2pi \\"
echo "       --config ${STATE_DIR}/config.toml --check-config"
echo "4. sudo systemctl restart ma2pi.service && journalctl -u ma2pi -f"
echo "5. Weboberfläche im LAN öffnen: http://<pi-adresse>:8080/"
echo "6. Pi ausschalten: Erweitert > Pi herunterfahren oder am Cherry MA + Off halten, dann 2x Please."
