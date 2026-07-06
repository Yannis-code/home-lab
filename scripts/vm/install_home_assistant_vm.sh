#!/usr/bin/env bash
set -euo pipefail

# Installe KVM/libvirt + Home Assistant OS (derniere version) en VM
# sur Raspberry Pi OS Trixie (arm64), avec bridge reseau Linux.
#
# Reversibilite:
#   - ./scripts/vm/install_home_assistant_vm.sh           -> installation
#   - ./scripts/vm/install_home_assistant_vm.sh revert    -> rollback

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

VM_NAME="${VM_NAME:-home-assistant}"
VM_RAM_MB="${VM_RAM_MB:-4096}"
VM_VCPUS="${VM_VCPUS:-2}"
VM_DISK_DIR="${VM_DISK_DIR:-/var/lib/libvirt/images/${VM_NAME}}"
BRIDGE_NAME="${BRIDGE_NAME:-br0}"
PHYS_IFACE="${PHYS_IFACE:-wlan0}"
HA_RELEASE_API="https://api.github.com/repos/home-assistant/operating-system/releases/latest"
STATE_DIR="${STATE_DIR:-/var/lib/home-lab-ha-vm}"
STATE_FILE="${STATE_DIR}/state.env"

BRIDGE_CIDR="${BRIDGE_CIDR:-}"
BRIDGE_GW="${BRIDGE_GW:-}"
BRIDGE_DNS="${BRIDGE_DNS:-1.1.1.1,8.8.8.8}"
PURGE_PACKAGES="${PURGE_PACKAGES:-0}"

ensure_iface_exists() {
  if ! ip link show "${PHYS_IFACE}" >/dev/null 2>&1; then
    echo "Interface ${PHYS_IFACE} introuvable."
    exit 1
  fi
}

save_state() {
  mkdir -p "${STATE_DIR}"
  cat >"${STATE_FILE}" <<EOF
VM_NAME=${VM_NAME}
VM_DISK_DIR=${VM_DISK_DIR}
BRIDGE_NAME=${BRIDGE_NAME}
PHYS_IFACE=${PHYS_IFACE}
NETWORK_BACKEND=${1}
EOF
}

load_state() {
  if [[ -f "${STATE_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${STATE_FILE}"
  fi
}

revert_network_nmcli() {
  nmcli connection delete "${BRIDGE_NAME}-slave-${PHYS_IFACE}" >/dev/null 2>&1 || true
  nmcli connection delete "${BRIDGE_NAME}" >/dev/null 2>&1 || true

  if nmcli -t -f NAME connection show | grep -Fxq "${PHYS_IFACE}"; then
    nmcli connection modify "${PHYS_IFACE}" ipv4.method auto ipv6.method auto || true
    nmcli connection up "${PHYS_IFACE}" || true
  fi
}

revert_network_networkd() {
  rm -f "/etc/systemd/network/10-${BRIDGE_NAME}.netdev"
  rm -f "/etc/systemd/network/11-${BRIDGE_NAME}.network"
  rm -f "/etc/systemd/network/12-${PHYS_IFACE}.network"
  systemctl restart systemd-networkd || true
}

revert_all() {
  echo "[1/5] Chargement etat precedent..."
  load_state

  echo "[2/5] Arret/suppression VM ${VM_NAME}..."
  virsh destroy "${VM_NAME}" >/dev/null 2>&1 || true
  virsh undefine "${VM_NAME}" --remove-all-storage >/dev/null 2>&1 || true
  rm -rf "${VM_DISK_DIR}" || true

  echo "[3/5] Suppression configuration bridge..."
  if command -v nmcli >/dev/null 2>&1 && [[ "${NETWORK_BACKEND:-nmcli}" == "nmcli" ]]; then
    revert_network_nmcli
  else
    revert_network_networkd
  fi

  echo "[4/5] Nettoyage etat local..."
  rm -f "${STATE_FILE}" || true

  echo "[5/5] Termine."
  if [[ "${PURGE_PACKAGES}" == "1" ]]; then
    echo "PURGE_PACKAGES=1 detecte: suppression paquets KVM/libvirt..."
    apt-get purge -y \
      qemu-system-arm \
      qemu-system-aarch64 \
      qemu-efi-aarch64 \
      qemu-utils \
      libvirt-daemon-system \
      libvirt-clients \
      virtinst \
      bridge-utils
    apt-get autoremove -y
  fi

  cat <<EOF
Rollback applique.

Note:
  - Si vous etiez connecte en SSH via l'interface modifiee, verifiez la connectivite.
  - Le fichier d'etat utilise etait: ${STATE_FILE}
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

ensure_iface_exists

if [[ -z "${BRIDGE_CIDR}" || -z "${BRIDGE_GW}" ]]; then
  cat <<EOF
Variables requises:
  BRIDGE_CIDR  ex: 192.168.1.66/24
  BRIDGE_GW    ex: 192.168.1.1

Exemple:
  sudo BRIDGE_CIDR=192.168.1.66/24 BRIDGE_GW=192.168.1.1 ./scripts/vm/install_home_assistant_vm.sh
EOF
  exit 1
fi

echo "[1/8] Installation des paquets KVM/libvirt..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  qemu-system-arm \
  qemu-system-aarch64 \
  qemu-efi-aarch64 \
  qemu-utils \
  libvirt-daemon-system \
  libvirt-clients \
  virtinst \
  bridge-utils \
  curl \
  xz-utils \
  jq

echo "[2/8] Activation de libvirtd..."
systemctl enable --now libvirtd

echo "[3/8] Verification acceleration KVM..."
if [[ ! -e /dev/kvm ]]; then
  echo "Attention: /dev/kvm absent. La VM fonctionnera potentiellement sans acceleration (plus lente)."
fi

echo "[4/8] Configuration du bridge ${BRIDGE_NAME} sur ${PHYS_IFACE}..."
if command -v nmcli >/dev/null 2>&1; then
  if ! nmcli -t -f NAME connection show | grep -Fxq "${BRIDGE_NAME}"; then
    nmcli connection add type bridge ifname "${BRIDGE_NAME}" con-name "${BRIDGE_NAME}"
  fi

  if ! nmcli -t -f NAME connection show | grep -Fxq "${BRIDGE_NAME}-slave-${PHYS_IFACE}"; then
    nmcli connection add type bridge-slave ifname "${PHYS_IFACE}" master "${BRIDGE_NAME}" con-name "${BRIDGE_NAME}-slave-${PHYS_IFACE}"
  fi

  nmcli connection modify "${BRIDGE_NAME}" ipv4.method manual ipv4.addresses "${BRIDGE_CIDR}" ipv4.gateway "${BRIDGE_GW}" ipv4.dns "${BRIDGE_DNS}" ipv6.method ignore
  nmcli connection modify "${PHYS_IFACE}" ipv4.method disabled ipv6.method ignore || true

  nmcli connection up "${BRIDGE_NAME}" || true
  nmcli connection up "${BRIDGE_NAME}-slave-${PHYS_IFACE}" || true
else
  mkdir -p /etc/systemd/network

  cat >/etc/systemd/network/10-${BRIDGE_NAME}.netdev <<EOF
[NetDev]
Name=${BRIDGE_NAME}
Kind=bridge
EOF

  cat >/etc/systemd/network/11-${BRIDGE_NAME}.network <<EOF
[Match]
Name=${BRIDGE_NAME}

[Network]
Address=${BRIDGE_CIDR}
Gateway=${BRIDGE_GW}
DNS=${BRIDGE_DNS%%,*}
EOF

  cat >/etc/systemd/network/12-${PHYS_IFACE}.network <<EOF
[Match]
Name=${PHYS_IFACE}

[Network]
Bridge=${BRIDGE_NAME}
EOF

  systemctl enable --now systemd-networkd
  systemctl restart systemd-networkd
  save_state "networkd"
fi

if command -v nmcli >/dev/null 2>&1; then
  save_state "nmcli"
fi

echo "[5/8] Recuperation de la derniere image Home Assistant OS (aarch64)..."
mkdir -p "${VM_DISK_DIR}"
cd "${VM_DISK_DIR}"

QCOW2_XZ_URL="$(curl -fsSL "${HA_RELEASE_API}" | jq -r '.assets[]?.browser_download_url' | grep -E 'haos_generic-aarch64-[0-9.]+\.qcow2\.xz$' | head -n1)"
if [[ -z "${QCOW2_XZ_URL}" ]]; then
  echo "Impossible de trouver l'image haos_generic-aarch64 dans la derniere release."
  exit 1
fi

QCOW2_XZ_FILE="${QCOW2_XZ_URL##*/}"
QCOW2_FILE="${QCOW2_XZ_FILE%.xz}"

curl -fL "${QCOW2_XZ_URL}" -o "${QCOW2_XZ_FILE}"
xz -df "${QCOW2_XZ_FILE}"

echo "[6/8] Installation de la VM ${VM_NAME}..."
if virsh dominfo "${VM_NAME}" >/dev/null 2>&1; then
  echo "La VM ${VM_NAME} existe deja, etape creation ignoree."
else
  virt-install \
    --name "${VM_NAME}" \
    --memory "${VM_RAM_MB}" \
    --vcpus "${VM_VCPUS}" \
    --cpu host-passthrough \
    --import \
    --disk "path=${VM_DISK_DIR}/${QCOW2_FILE},format=qcow2,bus=virtio" \
    --network "bridge=${BRIDGE_NAME},model=virtio" \
    --os-variant generic \
    --graphics none \
    --noautoconsole
fi

echo "[7/8] Demarrage + autostart..."
virsh start "${VM_NAME}" || true
virsh autostart "${VM_NAME}"

echo "[8/8] Termine."
cat <<EOF
VM Home Assistant deployee.

Points importants:
  - L'IP de Home Assistant sera attribuee sur votre LAN via le bridge ${BRIDGE_NAME}.
  - URL locale probable: http://homeassistant.local:8123 (ou IP DHCP de la VM)
  - Pour voir l'IP depuis l'hote: virsh domifaddr ${VM_NAME}

Pensez a aligner Traefik sur l'IP de la VM (variable HA_VM_IP).
EOF
