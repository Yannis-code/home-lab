#!/usr/bin/env bash
set -euo pipefail

# Configure Cockpit + cockpit-machines sur l'hote (Raspberry Pi OS Trixie).
#
# Reversibilite:
#   - ./scripts/host/configure_cockpit_machines.sh           -> installation/config
#   - ./scripts/host/configure_cockpit_machines.sh revert    -> rollback

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ce script doit etre lance en root (sudo)."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.env"
  set +a
fi

ACTION="${1:-install}"
STATE_DIR="${STATE_DIR_COCKPIT:-/var/lib/home-lab-cockpit}"
STATE_FILE="${STATE_DIR}/state.env"

COCKPIT_FQDN="${COCKPIT_FQDN:-cockpit.doudou.house}"
COCKPIT_PORT="${COCKPIT_PORT:-9090}"
TARGET_USER="${TARGET_USER:-${SUDO_USER:-}}"
PURGE_PACKAGES="${PURGE_PACKAGES:-0}"

save_state() {
  mkdir -p "${STATE_DIR}"
  cat >"${STATE_FILE}" <<EOF
COCKPIT_FQDN=${COCKPIT_FQDN}
COCKPIT_PORT=${COCKPIT_PORT}
TARGET_USER=${TARGET_USER}
EOF
}

load_state() {
  if [[ -f "${STATE_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${STATE_FILE}"
  fi
}

configure_cockpit_proxy_origin() {
  mkdir -p /etc/cockpit
  cat >/etc/cockpit/cockpit.conf <<EOF
[WebService]
Origins = https://${COCKPIT_FQDN}
ProtocolHeader = X-Forwarded-Proto
EOF
}

configure_cockpit_socket_port() {
  local override_dir="/etc/systemd/system/cockpit.socket.d"
  local override_file="${override_dir}/override.conf"

  if [[ "${COCKPIT_PORT}" == "9090" ]]; then
    rm -f "${override_file}" || true
    rmdir "${override_dir}" 2>/dev/null || true
    return
  fi

  mkdir -p "${override_dir}"
  cat >"${override_file}" <<EOF
[Socket]
ListenStream=
ListenStream=0.0.0.0:${COCKPIT_PORT}
EOF
}

add_user_to_kvm_groups() {
  if [[ -n "${TARGET_USER}" ]] && id "${TARGET_USER}" >/dev/null 2>&1; then
    usermod -aG libvirt,kvm "${TARGET_USER}" || true
    echo "Utilisateur ${TARGET_USER} ajoute aux groupes libvirt,kvm (reconnexion requise)."
  else
    echo "TARGET_USER non defini ou introuvable: skip usermod."
  fi
}

install_all() {
  echo "[1/7] Installation Cockpit + Machines..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    cockpit \
    cockpit-machines \
    libvirt-daemon-system \
    libvirt-clients

  echo "[2/7] Configuration port cockpit.socket..."
  configure_cockpit_socket_port
  systemctl daemon-reload

  echo "[3/7] Activation services..."
  systemctl enable --now cockpit.socket
  systemctl enable --now libvirtd

  echo "[4/7] Config reverse proxy Cockpit (origins)..."
  configure_cockpit_proxy_origin

  echo "[5/7] Droits user pour libvirt/kvm..."
  add_user_to_kvm_groups

  echo "[6/7] Restart cockpit..."
  systemctl restart cockpit.socket || true

  echo "[7/7] Sauvegarde etat..."
  save_state

  cat <<EOF
Cockpit configure sur l'hote.

Acces local direct:
  https://<IP_HOTE>:${COCKPIT_PORT}

Acces via Traefik (apres maj labels):
  https://${COCKPIT_FQDN}
EOF
}

revert_all() {
  echo "[1/5] Chargement etat precedent..."
  load_state

  echo "[2/5] Retrait config cockpit reverse proxy..."
  rm -f /etc/cockpit/cockpit.conf || true

  echo "[3/5] Retrait override port cockpit.socket..."
  rm -f /etc/systemd/system/cockpit.socket.d/override.conf || true
  rmdir /etc/systemd/system/cockpit.socket.d 2>/dev/null || true
  systemctl daemon-reload || true

  echo "[4/5] Arret services cockpit..."
  systemctl disable --now cockpit.socket >/dev/null 2>&1 || true

  if [[ "${PURGE_PACKAGES}" == "1" ]]; then
    echo "PURGE_PACKAGES=1 detecte: purge Cockpit + Machines..."
    apt-get purge -y cockpit cockpit-machines
    apt-get autoremove -y
  fi

  echo "[5/5] Nettoyage etat local..."
  rm -f "${STATE_FILE}" || true

  cat <<EOF
Rollback Cockpit applique.

Note:
  - Les groupes utilisateur ne sont pas modifies en rollback automatique.
  - Pour retirer un groupe: gpasswd -d <user> libvirt ; gpasswd -d <user> kvm
EOF
}

if [[ "${ACTION}" == "revert" ]]; then
  revert_all
  exit 0
fi

if [[ "${ACTION}" != "install" ]]; then
  echo "Action invalide: ${ACTION}. Utilisez 'install' (defaut) ou 'revert'."
  exit 1
fi

install_all
