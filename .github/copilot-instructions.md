# Copilot instructions for `home-lab`

## Repository shape

This is a self-hosted infrastructure repository with three operational areas:

- The root `justfile` exposes namespaced commands for the `cockpit/` and `haos/` modules.
- `traefik/` contains the reverse proxy and TLS termination Compose service. The root `docker-compose.yml` includes it and the `pret-a-pousser` stack on the external Docker network `proxy`.
- `haos/` provisions Home Assistant OS as a libvirt/KVM VM with OpenTofu/Terraform.
- `cockpit/` contains a Bash installer, diagnostics, and configuration for `cockpit-machines`.
- `pret-a-pousser/` is a Python 3.11+ BLE-to-MQTT bridge for a Pret a Pousser Modulo2 device, plus its Docker and Home Assistant configuration.

The important runtime topology is Traefik -> Home Assistant's management NAT address (`192.168.150.10:8123`) and Traefik/MQTT Explorer on the external `proxy` network. The HAOS VM can use a LAN macvtap NIC, a libvirt NAT NIC, or both; the management NAT NIC is what permits same-host reverse-proxy access when macvtap host access is unavailable.

## Build, run, and infrastructure commands

Run commands from the repository root unless noted otherwise. Use `just` to discover recipes (`just`, `just cockpit`, or `just haos`).

### Python BLE/MQTT bridge

From `pret-a-pousser/`:

```bash
just sync                         # install the locked runtime dependencies
just doctor                       # inspect Python, BlueZ, service, and adapter state
just run-daemon ADDRESS ADAPTER   # run the MQTT bridge; address is required
just send on ADDRESS ADAPTER      # one-shot BLE command
just set-intensity printemps ADDRESS ADAPTER
just set-cycle 08:00 22:00 ADDRESS ADAPTER
just set-clock-now ADDRESS ADAPTER
```

The recipes use local `uv`/Python when available and fall back to the documented containerized `uv` workflow. The production image is built with `just docker-build`; the Compose stack is managed with `just compose-up`, `just compose-logs`, `just compose-restart`, and `just compose-down`.

There is currently no Python test suite or configured test runner. For a targeted syntax/import smoke check, run from `pret-a-pousser/`:

```bash
just py "-m py_compile src/potager_ble.py src/ble_controller.py src/mqtt_bridge.py src/modulo2_protocol.py src/config_models.py"
```

### Home Assistant OS infrastructure

From `haos/`:

```bash
just init       # initialize providers and backend
just plan       # plan using ../config/terraform.tfvars
just apply
just output
just destroy
```

The root equivalents are `just haos::init`, `just haos::plan`, `just haos::apply`, `just haos::output`, and `just haos::destroy`. The `haos/iac/` local backend writes state under `haos/state/`; do not commit state, plans, or local variable files.

### Cockpit host setup

From `cockpit/`:

```bash
just init-config
just check
just doctor
just install
just status
just logs
just url
just revert
```

The root equivalents use the `cockpit::` namespace. Installation, status, checks, diagnostics, logs, and revert require the recipe's `sudo` invocation. Runtime configuration is loaded from `COCKPIT_ENV_FILE` or `cockpit/config/cockpit-machines.conf`.

## Architecture and data flow

### BLE bridge

`src/potager_ble.py` is the CLI entry point. It parses CLI/environment configuration into `AppConfig`, validates it, then dispatches one-shot commands or starts `MqttBridge`.

`PotagerController` owns device connections, BlueZ cleanup hints, retry/hard-connect behavior, GATT reads/writes, and auto-state snapshot files. It targets the configured BLE MAC address; do not reintroduce name-based discovery as the normal path.

`modulo2_protocol.py` is the conversion boundary between human-readable values and BLE bytes. UUIDs, intensity values, channel groups, and preconfigured profiles are loaded from `src/config/modulo2_mapping.json` and `src/config/preconfigured_state_profiles.json`. Preserve this data-driven boundary rather than duplicating protocol constants in controllers or MQTT handlers.

`MqttBridge` translates retained MQTT profiles and state commands into protocol writes, and publishes availability, state, clock, profile, and transient status topics. The retained `<prefix>/auto` profile is the daemon's auto-mode source of truth; CLI `auto-save`/`auto-restore` instead use the configured local JSON snapshot file.

Home Assistant configuration under `home-assistant/` publishes the MQTT contract and provides the dashboard controls. If MQTT topic names or profile fields change, update the bridge README, Home Assistant package, and dashboard together.

### HAOS provisioning

The Terraform/OpenTofu files are intentionally split by concern: `data.tf` discovers host architecture and the latest HAOS release, `locals.tf` selects the architecture-specific image and XSLT inputs, `storage.tf` downloads/extracts/resizes the disk, `network.tf` creates the optional NAT network and DHCP reservation, and `vm.tf` defines the libvirt domain.

The `network_mode` and `enable_management_nat_interface` variables jointly determine whether the VM receives a NAT management interface. Architecture and USB passthrough affect the generated domain XML in `config/templates/`; preserve those relationships when changing VM hardware.

### Traefik and Compose

Traefik is configured through Docker labels and static command-line flags in `traefik/docker-compose.yml`. Services that should be proxied must join the external `proxy` network and explicitly opt into Traefik. HTTPS uses the `leresolver` ACME resolver and the dashboard is protected by the mounted `.htpasswd` file.

## Codebase-specific conventions

- Prefer `just` recipes over ad-hoc commands so root namespacing, virtual-environment selection, locked dependency installation, and Terraform variable-file paths remain consistent.
- Keep secrets and machine-local state in ignored files: `haos/config/terraform.tfvars`, `haos/state/`, `cockpit/config/cockpit-machines.conf`, `.env`, and `.htpasswd`. Use the tracked `.example` files as templates.
- Python configuration follows environment-variable defaults plus CLI overrides. Normalize the MQTT topic prefix by stripping trailing slashes, and keep all derived topics under that prefix.
- MQTT profile fields are human-readable (`printemps`, `ete`, `HH:MM`/`HH:MM:SS`, or `null`); conversion to numeric intensity and little-endian seconds belongs in `modulo2_protocol.py`.
- A profile containing any `null` required field must not produce a BLE write. Retained profiles and transient status topics have different semantics: model/profile topics are retained, status topics are not.
- BLE writes use explicit GATT response writes and the controller's retry/hard-connect lifecycle. Preserve cleanup and disconnect behavior when adding operations.
- Shell scripts use Bash strict mode and configuration loaded from environment files. Keep diagnostics explicit and avoid hiding operational failures; firewall helpers are the deliberate exception and are best-effort by design.
- Terraform resources use local-exec for host-level `virsh`, `curl`, `xz`, and `qemu-img` operations. Changes to those commands should account for idempotence, `set -euo pipefail`, and the local backend/state dependency ordering.
- Keep infrastructure addresses, hostnames, and ports aligned across Terraform outputs, Traefik labels, Compose environment defaults, and the README. These files describe one deployed topology rather than independent examples.
