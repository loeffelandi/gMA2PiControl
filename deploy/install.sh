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
SERVICE_FILE="/etc/systemd/system/ma2pi.service"
UDEV_FILE="/etc/udev/rules.d/99-ma2pi.rules"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
    echo "install.sh muss als root laufen (sudo deploy/install.sh)." >&2
    exit 1
fi

if [[ ! -x /usr/bin/python3 ]]; then
    echo "/usr/bin/python3 fehlt. Installiere python3 und python3-venv." >&2
    exit 1
fi

if ! getent group "${APP_GROUP}" >/dev/null; then
    groupadd --system "${APP_GROUP}"
fi
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${APP_GROUP}" --home-dir "${BASE_DIR}" \
        --shell /usr/sbin/nologin "${APP_USER}"
fi

install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0755 "${BASE_DIR}"
install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0755 "${APP_DIR}"
install -d -o root -g "${APP_GROUP}" -m 0750 "${CONFIG_DIR}"

# Application code (without tests, venv, caches or local config).
rm -rf "${APP_DIR}/ma2pi"
cp -a "${REPO_DIR}/ma2pi" "${APP_DIR}/ma2pi"
cp -a "${REPO_DIR}/pyproject.toml" "${APP_DIR}/pyproject.toml"
if [[ -f "${REPO_DIR}/README.md" ]]; then
    cp -a "${REPO_DIR}/README.md" "${APP_DIR}/README.md"
fi
find "${APP_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} +
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    /usr/bin/python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/python" -m pip install --quiet --upgrade pip
"${VENV_DIR}/bin/python" -m pip install --quiet "${APP_DIR}"
chown -R "${APP_USER}:${APP_GROUP}" "${BASE_DIR}"

install -m 0644 "${REPO_DIR}/deploy/ma2pi.service" "${SERVICE_FILE}"
install -m 0644 "${REPO_DIR}/deploy/99-ma2pi.rules" "${UDEV_FILE}"

# Never overwrite an existing configuration or password.
if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
    install -m 0640 -o root -g "${APP_GROUP}" \
        "${REPO_DIR}/config.toml" "${CONFIG_DIR}/config.toml"
    echo "Beispielkonfiguration nach ${CONFIG_DIR}/config.toml kopiert."
fi
if [[ ! -f "${CONFIG_DIR}/ma2pi.password" ]]; then
    install -m 0640 -o root -g "${APP_GROUP}" /dev/null \
        "${CONFIG_DIR}/ma2pi.password"
    echo "Bitte das onPC-Passwort in ${CONFIG_DIR}/ma2pi.password eintragen (leer lassen, wenn der Benutzer kein Passwort hat)." >&2
fi

systemctl daemon-reload
udevadm control --reload-rules
udevadm trigger --subsystem-match=input --subsystem-match=sound
systemctl enable ma2pi.service

echo
echo "Installation abgeschlossen."
echo "1. ${CONFIG_DIR}/config.toml anpassen (Host, Benutzer, Geräte-IDs)."
echo "2. ${CONFIG_DIR}/ma2pi.password befüllen."
echo "3. sudo -u ${APP_USER} ${VENV_DIR}/bin/python -m ma2pi \\"
echo "       --config ${CONFIG_DIR}/config.toml --check-config"
echo "4. sudo systemctl restart ma2pi.service && journalctl -u ma2pi -f"
