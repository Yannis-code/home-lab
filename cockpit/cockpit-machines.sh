#!/usr/bin/env bash

set -Eeuo pipefail

COCKPIT_PACKAGE="${COCKPIT_PACKAGE:-cockpit}"
COCKPIT_MACHINES_PACKAGE="${COCKPIT_MACHINES_PACKAGE:-cockpit-machines}"
COCKPIT_SERVICE="${COCKPIT_SERVICE:-cockpit.socket}"
COCKPIT_PORT="${COCKPIT_PORT:-9090}"

log() {
  printf '[cockpit-machines] %s\n' "$*"
}

fail() {
  printf '[cockpit-machines] error: %s\n' "$*" >&2
  exit 1
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

install_packages() {
  case "$(package_manager)" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y "$COCKPIT_PACKAGE" "$COCKPIT_MACHINES_PACKAGE"
      ;;
    dnf)
      dnf install -y "$COCKPIT_PACKAGE" "$COCKPIT_MACHINES_PACKAGE"
      ;;
  esac
}

remove_packages() {
  case "$(package_manager)" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get remove -y "$COCKPIT_MACHINES_PACKAGE" "$COCKPIT_PACKAGE"
      apt-get autoremove -y
      ;;
    dnf)
      dnf remove -y "$COCKPIT_MACHINES_PACKAGE" "$COCKPIT_PACKAGE"
      ;;
  esac
}

enable_service() {
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

  log "installation complete"
  log "web UI: https://<host>:$COCKPIT_PORT"
}

revert_cockpit() {
  require_root
  disable_service
  remove_packages

  log "revert complete"
}

status_cockpit() {
  require_root

  systemctl status "$COCKPIT_SERVICE" --no-pager || true
}

usage() {
  cat <<EOF
Usage: $0 <install|revert|status>
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
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"