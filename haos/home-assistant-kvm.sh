#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${HA_ENV_FILE:-$SCRIPT_DIR/homeassistant-kvm.conf}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

VM_NAME="${HA_VM_NAME:-home-assistant}"
VM_DESCRIPTION="${HA_VM_DESCRIPTION:-Home Assistant OS}"
VM_MEMORY_MB="${HA_VM_MEMORY_MB:-8192}"
VM_VCPUS="${HA_VM_VCPUS:-2}"
VM_DISK_SIZE="${HA_VM_DISK_SIZE:-32G}"
VM_MAC="${HA_VM_MAC:-52:54:00:ab:cd:10}"

NETWORK_NAME="${HA_NETWORK_NAME:-ha-net}"
NETWORK_BRIDGE="${HA_NETWORK_BRIDGE:-virbr-ha}"
NETWORK_GATEWAY="${HA_NETWORK_GATEWAY:-192.168.150.1}"
NETWORK_NETMASK="${HA_NETWORK_NETMASK:-255.255.255.0}"
NETWORK_DHCP_START="${HA_NETWORK_DHCP_START:-192.168.150.10}"
NETWORK_DHCP_END="${HA_NETWORK_DHCP_END:-192.168.150.200}"
VM_IP="${HA_VM_IP:-192.168.150.10}"

LIBVIRT_IMAGE_ROOT="${HA_LIBVIRT_IMAGE_ROOT:-/var/lib/libvirt/images}"
VM_STORAGE_DIR="${HA_VM_STORAGE_DIR:-$LIBVIRT_IMAGE_ROOT/$VM_NAME}"
VM_DISK_PATH="$VM_STORAGE_DIR/$VM_NAME.qcow2"
DOWNLOAD_PATH="$VM_STORAGE_DIR/haos-latest.qcow2.xz"
HOST_ARCH="$(uname -m)"
DISK_REPLACED=0

GITHUB_RELEASE_API="https://api.github.com/repos/home-assistant/operating-system/releases/latest"

log() {
  printf '[home-assistant-kvm] %s\n' "$*"
}

fail() {
  printf '[home-assistant-kvm] error: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [[ "$EUID" -ne 0 ]]; then
    fail "run this script as root or through sudo"
  fi
}

require_commands() {
  local missing=()
  local command_name

  for command_name in curl virsh virt-install qemu-img xz grep sed awk mktemp numfmt; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      missing+=("$command_name")
    fi
  done

  if (( ${#missing[@]} > 0 )); then
    fail "missing required commands: ${missing[*]}"
  fi
}

network_is_active() {
  virsh net-list --name | grep -Fxq "$NETWORK_NAME"
}

vm_is_running() {
  virsh list --name | grep -Fxq "$VM_NAME"
}

desired_domain_arch() {
  case "$HOST_ARCH" in
    aarch64|arm64)
      printf 'aarch64\n'
      ;;
    x86_64|amd64)
      printf 'x86_64\n'
      ;;
    *)
      fail "unsupported host architecture: $HOST_ARCH"
      ;;
  esac
}

desired_image_pattern() {
  case "$HOST_ARCH" in
    aarch64|arm64)
      printf 'haos_generic-aarch64-[0-9.]+\\.qcow2\\.xz\n'
      ;;
    x86_64|amd64)
      printf 'haos_ova-[0-9.]+\\.qcow2\\.xz\n'
      ;;
    *)
      fail "unsupported host architecture: $HOST_ARCH"
      ;;
  esac
}

image_matches_host_arch() {
  if [[ ! -f "$VM_DISK_PATH" ]]; then
    return 1
  fi

  case "$HOST_ARCH" in
    aarch64|arm64)
      grep -aq 'BOOTAA64 EFI' "$VM_DISK_PATH"
      ;;
    x86_64|amd64)
      grep -aq 'BOOTX64 EFI' "$VM_DISK_PATH"
      ;;
    *)
      return 1
      ;;
  esac
}

latest_image_url() {
  local release_json
  local image_pattern

  release_json="$(curl -fsSL "$GITHUB_RELEASE_API")"
  image_pattern="$(desired_image_pattern)"
  printf '%s\n' "$release_json" \
    | grep -Eo "https://[^\"]+/${image_pattern}" \
    | head -n 1
}

ensure_storage_dir() {
  mkdir -p "$VM_STORAGE_DIR"
}

ensure_network() {
  local network_xml

  if ! virsh net-info "$NETWORK_NAME" >/dev/null 2>&1; then
    network_xml="$(mktemp)"
    cat >"$network_xml" <<EOF
<network>
  <name>$NETWORK_NAME</name>
  <forward mode='nat'/>
  <bridge name='$NETWORK_BRIDGE' stp='on' delay='0'/>
  <ip address='$NETWORK_GATEWAY' netmask='$NETWORK_NETMASK'>
    <dhcp>
      <range start='$NETWORK_DHCP_START' end='$NETWORK_DHCP_END'/>
      <host mac='$VM_MAC' ip='$VM_IP'/>
    </dhcp>
  </ip>
</network>
EOF
    virsh net-define "$network_xml" >/dev/null
    rm -f "$network_xml"
  fi

  if ! network_is_active; then
    virsh net-start "$NETWORK_NAME" >/dev/null
  fi

  virsh net-autostart "$NETWORK_NAME" >/dev/null

  if ! virsh net-dumpxml "$NETWORK_NAME" | grep -Eq "<host[^>]*mac='$VM_MAC'[^>]*ip='$VM_IP'|<host[^>]*ip='$VM_IP'[^>]*mac='$VM_MAC'"; then
    virsh net-update "$NETWORK_NAME" add ip-dhcp-host "<host mac='$VM_MAC' ip='$VM_IP'/>" \
      --live --config >/dev/null
  fi
}

download_image() {
  local image_url

  if [[ -f "$VM_DISK_PATH" ]]; then
    if image_matches_host_arch; then
      log "disk already present at $VM_DISK_PATH"
      return
    fi

    log "existing disk does not match host architecture $HOST_ARCH, replacing it"

    if vm_is_running; then
      log "stopping virtual machine $VM_NAME before replacing its disk"
      virsh destroy "$VM_NAME" >/dev/null
    fi

    rm -f "$VM_DISK_PATH"
  fi

  rm -f "$DOWNLOAD_PATH"

  image_url="$(latest_image_url)"

  if [[ -z "$image_url" ]]; then
    fail "unable to resolve the latest Home Assistant OS qcow2 image"
  fi

  log "downloading $image_url"
  curl -fL "$image_url" -o "$DOWNLOAD_PATH"

  log "extracting image to $VM_DISK_PATH"
  xz -dc "$DOWNLOAD_PATH" > "$VM_DISK_PATH"
  rm -f "$DOWNLOAD_PATH"
  DISK_REPLACED=1
}

boot_args() {
  case "$HOST_ARCH" in
    aarch64|arm64)
      printf '%s\n' "loader=/usr/share/AAVMF/AAVMF_CODE.no-secboot.fd,loader.readonly=yes,loader.type=pflash,nvram.template=/usr/share/AAVMF/AAVMF_VARS.fd"
      ;;
    x86_64|amd64)
      printf '%s\n' "uefi"
      ;;
    *)
      fail "unsupported host architecture: $HOST_ARCH"
      ;;
  esac
}

desired_loader_path() {
  case "$HOST_ARCH" in
    aarch64|arm64)
      printf '%s\n' "/usr/share/AAVMF/AAVMF_CODE.no-secboot.fd"
      ;;
    x86_64|amd64)
      printf '\n'
      ;;
    *)
      fail "unsupported host architecture: $HOST_ARCH"
      ;;
  esac
}

resize_disk_if_needed() {
  local current_size_bytes
  local requested_size_bytes

  current_size_bytes="$(qemu-img info --output=json "$VM_DISK_PATH" \
    | sed -nE 's/^[[:space:]]*"virtual-size"[[:space:]]*:[[:space:]]*([0-9]+),?$/\1/p' \
    | tail -n 1)"
  requested_size_bytes="$(numfmt --from=iec "$VM_DISK_SIZE")"

  if [[ -z "$current_size_bytes" || -z "$requested_size_bytes" ]]; then
    fail "unable to determine disk sizes"
  fi

  if (( requested_size_bytes > current_size_bytes )); then
    log "resizing disk from $current_size_bytes bytes to $VM_DISK_SIZE"
    qemu-img resize "$VM_DISK_PATH" "$VM_DISK_SIZE" >/dev/null
  fi
}

ensure_vm() {
  local target_domain_arch
  local domain_xml
  local current_domain_arch
  local current_disk_bus
  local current_disk_source
  local current_loader_path
  local current_network
  local target_loader_path

  target_domain_arch="$(desired_domain_arch)"
  target_loader_path="$(desired_loader_path)"

  if virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    domain_xml="$(virsh dumpxml "$VM_NAME")"
    current_domain_arch="$(printf '%s\n' "$domain_xml" | sed -nE "s@.*<type arch='([^']+)'.*@\1@p" | head -n 1)"
    current_disk_bus="$(printf '%s\n' "$domain_xml" | sed -nE "s@.*<target dev='[^']+' bus='([^']+)'.*@\1@p" | head -n 1)"
    current_disk_source="$(printf '%s\n' "$domain_xml" | sed -nE "s@.*<source file='([^']+)'.*@\1@p" | head -n 1)"
    current_loader_path="$(printf '%s\n' "$domain_xml" | sed -nE 's@.*<loader[^>]*>([^<]+)</loader>.*@\1@p' | head -n 1)"
    current_network="$(printf '%s\n' "$domain_xml" | sed -nE "s@.*<source network='([^']+)'.*@\1@p" | head -n 1)"

    if [[ "$current_disk_source" != "$VM_DISK_PATH" ]] \
      || [[ "$current_disk_bus" != "virtio" ]] \
      || [[ "$current_network" != "$NETWORK_NAME" ]] \
      || [[ "$current_domain_arch" != "$target_domain_arch" ]] \
      || [[ -n "$target_loader_path" && "$current_loader_path" != "$target_loader_path" ]]; then
      log "recreating incompatible virtual machine definition for $VM_NAME"

      if vm_is_running; then
        virsh destroy "$VM_NAME" >/dev/null
      fi

      virsh undefine "$VM_NAME" --nvram >/dev/null
    else
      log "virtual machine $VM_NAME already exists"
      return
    fi
  fi

  log "creating virtual machine $VM_NAME"
  virt-install \
    --name "$VM_NAME" \
    --description "$VM_DESCRIPTION" \
    --os-variant generic \
    --memory "$VM_MEMORY_MB" \
    --vcpus "$VM_VCPUS" \
    --cpu host-passthrough \
    --import \
    --graphics none \
    --noautoconsole \
    --boot "$(boot_args)" \
    --disk "path=$VM_DISK_PATH,format=qcow2,bus=virtio" \
    --network "network=$NETWORK_NAME,model=virtio,mac=$VM_MAC"

  virsh autostart "$VM_NAME" >/dev/null
}

start_vm() {
  if ! vm_is_running; then
    virsh start "$VM_NAME" >/dev/null
  fi
}

install_vm() {
  require_root
  require_commands
  ensure_storage_dir
  ensure_network
  download_image
  resize_disk_if_needed
  ensure_vm
  start_vm

  log "installation complete"
  log "reserved IP: $VM_IP"
  log "open http://$VM_IP:8123 after the first boot finishes"
}

revert_vm() {
  require_root
  require_commands

  if virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    if vm_is_running; then
      log "stopping virtual machine $VM_NAME"
      virsh destroy "$VM_NAME" >/dev/null
    fi

    log "undefining virtual machine $VM_NAME"
    virsh undefine "$VM_NAME" --nvram >/dev/null
  fi

  if [[ -d "$VM_STORAGE_DIR" ]]; then
    log "removing $VM_STORAGE_DIR"
    rm -rf "$VM_STORAGE_DIR"
  fi

  if virsh net-info "$NETWORK_NAME" >/dev/null 2>&1; then
    if network_is_active; then
      log "stopping network $NETWORK_NAME"
      virsh net-destroy "$NETWORK_NAME" >/dev/null
    fi

    log "undefining network $NETWORK_NAME"
    virsh net-undefine "$NETWORK_NAME" >/dev/null
  fi

  log "revert complete"
}

print_status() {
  require_root
  require_commands

  if virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    virsh dominfo "$VM_NAME"
    printf '\n'
    virsh net-dhcp-leases "$NETWORK_NAME" || true
  else
    log "virtual machine $VM_NAME does not exist"
  fi
}

print_ip() {
  printf '%s\n' "$VM_IP"
}

usage() {
  cat <<EOF
Usage: $0 <install|revert|status|ip>

Configuration file: $ENV_FILE
EOF
}

main() {
  local action="${1:-}"

  case "$action" in
    install)
      install_vm
      ;;
    revert)
      revert_vm
      ;;
    status)
      print_status
      ;;
    ip)
      print_ip
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"