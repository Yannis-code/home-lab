#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${COCKPIT_ENV_FILE:-$SCRIPT_DIR/config/cockpit-machines.conf}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

COCKPIT_PACKAGE="${COCKPIT_PACKAGE:-cockpit}"
COCKPIT_MACHINES_PACKAGE="${COCKPIT_MACHINES_PACKAGE:-cockpit-machines}"
COCKPIT_SERVICE="${COCKPIT_SERVICE:-cockpit.socket}"
COCKPIT_PORT="${COCKPIT_PORT:-9090}"
COCKPIT_LOG_LINES="${COCKPIT_LOG_LINES:-120}"
COCKPIT_MANAGE_FIREWALL="${COCKPIT_MANAGE_FIREWALL:-false}"
COCKPIT_PURGE="${COCKPIT_PURGE:-false}"
COCKPIT_STATE_DIR="${COCKPIT_STATE_DIR:-$SCRIPT_DIR/state}"

log() {
  printf '[cockpit-machines] %s\n' "$*"
}

fail() {
  printf '[cockpit-machines] error: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf '[cockpit-machines] warn: %s\n' "$*" >&2
}

require_root() {
  if [[ "$EUID" -ne 0 ]]; then
    fail "run this script as root or through sudo"
  fi
}

package_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    printf 'apt\n'
    return
  fi

  if command -v dnf >/dev/null 2>&1; then
    printf 'dnf\n'
    return
  fi

  fail "supported package manager not found; expected apt-get or dnf"
}

package_installed() {
  local package_name="$1"

  case "$(package_manager)" in
    apt)
      dpkg-query -W -f='${Status}' "$package_name" 2>/dev/null | grep -q "install ok installed"
      ;;
    dnf)
      rpm -q "$package_name" >/dev/null 2>&1
      ;;
  esac
}

service_exists() {
  systemctl list-unit-files --type=socket --type=service | awk '{print $1}' | grep -Fxq "$COCKPIT_SERVICE"
}

ensure_firewall_open() {
  if [[ "$COCKPIT_MANAGE_FIREWALL" != "true" ]]; then
    return
  fi

  if command -v ufw >/dev/null 2>&1; then
    ufw allow "${COCKPIT_PORT}/tcp" >/dev/null || true
    return
  fi

  if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --add-port="${COCKPIT_PORT}/tcp" --permanent >/dev/null || true
    firewall-cmd --reload >/dev/null || true
    return
  fi

  warn "firewall management requested but neither ufw nor firewalld is available"
}

ensure_firewall_closed() {
  if [[ "$COCKPIT_MANAGE_FIREWALL" != "true" ]]; then
    return
  fi

  if command -v ufw >/dev/null 2>&1; then
    ufw delete allow "${COCKPIT_PORT}/tcp" >/dev/null || true
    return
  fi

  if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --remove-port="${COCKPIT_PORT}/tcp" --permanent >/dev/null || true
    firewall-cmd --reload >/dev/null || true
    return
  fi
}

install_packages() {
  local to_install=()

  if ! package_installed "$COCKPIT_PACKAGE"; then
    to_install+=("$COCKPIT_PACKAGE")
  fi

  if ! package_installed "$COCKPIT_MACHINES_PACKAGE"; then
    to_install+=("$COCKPIT_MACHINES_PACKAGE")
  fi

  if (( ${#to_install[@]} == 0 )); then
    log "packages already installed"
    return
  fi

  case "$(package_manager)" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y "${to_install[@]}"
      ;;
    dnf)
      dnf install -y "${to_install[@]}"
      ;;
  esac
}

remove_packages() {
  local to_remove=()

  if package_installed "$COCKPIT_MACHINES_PACKAGE"; then
    to_remove+=("$COCKPIT_MACHINES_PACKAGE")
  fi

  if package_installed "$COCKPIT_PACKAGE"; then
    to_remove+=("$COCKPIT_PACKAGE")
  fi

  if (( ${#to_remove[@]} == 0 )); then
    log "packages already absent"
    return
  fi

  case "$(package_manager)" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      if [[ "$COCKPIT_PURGE" == "true" ]]; then
        apt-get purge -y "${to_remove[@]}"
      else
        apt-get remove -y "${to_remove[@]}"
      fi
      apt-get autoremove -y
      ;;
    dnf)
      dnf remove -y "${to_remove[@]}"
      ;;
  esac
}

enable_service() {
  if ! service_exists; then
    fail "service unit not found: $COCKPIT_SERVICE"
  fi

  systemctl enable --now "$COCKPIT_SERVICE"
}

disable_service() {
  if systemctl list-unit-files "$COCKPIT_SERVICE" >/dev/null 2>&1; then
    systemctl disable --now "$COCKPIT_SERVICE" || true
  fi
}

install_cockpit() {
  require_root
  install_packages
  enable_service
  ensure_firewall_open

  log "installation complete"
  log "web UI: $(cockpit_url)"
}

revert_cockpit() {
  require_root
  disable_service
  ensure_firewall_closed
  remove_packages

  log "revert complete"
}

status_cockpit() {
  require_root

  systemctl status "$COCKPIT_SERVICE" --no-pager || true
  printf '\n'
  ss -ltnp | grep -E ":${COCKPIT_PORT}[[:space:]]" || true
}

cockpit_url() {
  local host_ip

  host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -z "$host_ip" ]]; then
    host_ip="<host>"
  fi

  printf 'https://%s:%s\n' "$host_ip" "$COCKPIT_PORT"
}

print_url() {
  cockpit_url
}

check_cockpit() {
  require_root

  printf 'package manager: %s\n' "$(package_manager)"

  if package_installed "$COCKPIT_PACKAGE"; then
    printf 'package %s: installed\n' "$COCKPIT_PACKAGE"
  else
    printf 'package %s: missing\n' "$COCKPIT_PACKAGE"
  fi

  if package_installed "$COCKPIT_MACHINES_PACKAGE"; then
    printf 'package %s: installed\n' "$COCKPIT_MACHINES_PACKAGE"
  else
    printf 'package %s: missing\n' "$COCKPIT_MACHINES_PACKAGE"
  fi

  if systemctl is-active --quiet "$COCKPIT_SERVICE"; then
    printf 'service %s: active\n' "$COCKPIT_SERVICE"
  else
    printf 'service %s: inactive\n' "$COCKPIT_SERVICE"
  fi

  if ss -ltn | grep -qE ":${COCKPIT_PORT}[[:space:]]"; then
    printf 'port %s/tcp: listening\n' "$COCKPIT_PORT"
  else
    printf 'port %s/tcp: not listening\n' "$COCKPIT_PORT"
  fi

  printf 'url: %s\n' "$(cockpit_url)"
}

doctor_cockpit() {
  require_root
  check_cockpit

  printf '\nlibvirt checks:\n'
  if command -v virsh >/dev/null 2>&1; then
    printf '- virsh: available\n'
    if virsh -c qemu:///system uri >/dev/null 2>&1; then
      printf '- libvirt system URI: reachable\n'
    else
      printf '- libvirt system URI: unreachable\n'
    fi
  else
    printf '- virsh: missing\n'
  fi

  if systemctl is-active --quiet libvirtd || systemctl is-active --quiet virtqemud; then
    printf '- libvirt daemon: active\n'
  else
    printf '- libvirt daemon: inactive\n'
  fi
}

logs_cockpit() {
  require_root

  journalctl -u "$COCKPIT_SERVICE" -n "$COCKPIT_LOG_LINES" --no-pager || true
}

usage() {
  cat <<EOF
Usage: $0 <install|revert|status|check|doctor|logs|url>

Configuration file: $ENV_FILE
EOF
}

main() {
  local action="${1:-}"

  case "$action" in
    install)
      install_cockpit
      ;;
    revert)
      revert_cockpit
      ;;
    status)
      status_cockpit
      ;;
    check)
      check_cockpit
      ;;
    doctor)
      doctor_cockpit
      ;;
    logs)
      logs_cockpit
      ;;
    url)
      print_url
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"