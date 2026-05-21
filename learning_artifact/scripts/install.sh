#!/usr/bin/env bash
# netwatch installer for Rocky 9 / Ubuntu 22+ / Debian 12.
# Idempotent: safe to re-run for upgrades.
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo "must run as root" >&2; exit 1
fi

PREFIX="${PREFIX:-/usr/local}"
CONFIG_DIR="/etc/netwatch"
LIB_DIR="/var/lib/netwatch"
LOG_DIR="/var/log/netwatch"
RUN_DIR="/run/netwatch"
SVC_USER="netwatch"

echo "[1/6] dedicated system user"
getent group  "$SVC_USER" >/dev/null || groupadd --system "$SVC_USER"
getent passwd "$SVC_USER" >/dev/null || useradd  --system -g "$SVC_USER" -d "$LIB_DIR" -s /usr/sbin/nologin "$SVC_USER"

echo "[2/6] directories"
install -d -m 0750 -o "$SVC_USER" -g "$SVC_USER" "$LIB_DIR" "$LOG_DIR" "$RUN_DIR"
install -d -m 0755 "$CONFIG_DIR"

echo "[3/6] python package"
python3 -m pip install --upgrade --root-user-action=ignore .

echo "[4/6] default config"
if [[ ! -f "$CONFIG_DIR/netwatch.yaml" ]]; then
    python3 -c "from netwatch.config import dump_default_yaml; print(dump_default_yaml())" > "$CONFIG_DIR/netwatch.yaml"
    chmod 0644 "$CONFIG_DIR/netwatch.yaml"
fi

echo "[5/6] set unlock password"
if [[ ! -f "$CONFIG_DIR/auth.json" ]]; then
    netwatch setpassword
    chown root:"$SVC_USER" "$CONFIG_DIR/auth.json"
    chmod 0640 "$CONFIG_DIR/auth.json"
fi

echo "[6/6] systemd unit"
install -m 0644 systemd/netwatch.service /etc/systemd/system/netwatch.service
systemctl daemon-reload
systemctl enable --now netwatch.service
systemctl --no-pager --lines=15 status netwatch.service || true

echo "done. logs: journalctl -u netwatch -f"
