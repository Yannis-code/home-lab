# pret-a-pousser BLE bridge (Modulo2)

Bridge BLE -> MQTT for Pret a Pousser Modulo2.

This folder now uses a modular layout:

- `src/potager_ble.py`: CLI entrypoint (commands + config + logging).
- `src/ble_controller.py`: BLE read/write + robust connect retry + auto-state snapshot/restore.
- `src/mqtt_bridge.py`: MQTT subscriptions/publications and protocol topic handlers.
- `src/modulo2_protocol.py`: protocol wrapper (UUIDs, presets, encoders, builders).
- `src/config/modulo2_mapping.json`: static protocol constants and channel groups.
- `src/config/preconfigured_state_profiles.json`: preconfigured state profiles (human-readable).
- `src/config/app_defaults.json`: static app defaults.
- `src/config_models.py`: typed app config dataclass.

## 1) Requirements

- Linux host with BlueZ and BLE adapter (`hci0` recommended unless overridden).
- Fixed BLE MAC address configured via `POTAGER_ADDRESS` (or `--address`).
- Python >= 3.11 (project tested with venv).
- MQTT broker reachable from this host.

Python dependencies:

- `bleak`
- `paho-mqtt`

Install with uv (recommended):

```bash
just sync
```

## 2) Quick start

Health check:

```bash
just doctor
```

Start MQTT daemon bridge:

```bash
just run-daemon
```

With debug logs:

```bash
just run-daemon-debug
```

One-shot BLE command (no MQTT):

```bash
just send on
just send off
```

## 3) CLI commands

Main command:

```bash
python3 src/potager_ble.py [global options] <command>
```

Commands:

- `send on|off`
- `set` (write one or more protocol channels)
- `auto-save` (snapshot current auto-mode values)
- `auto-restore` (replay snapshot values)
- `daemon` (continuous MQTT bridge; default if command omitted)

Useful examples:

```bash
# Set both intensities
python3 src/potager_ble.py set --left-intensity printemps --right-intensity printemps

# Set daily window
python3 src/potager_ble.py set --left-start 08:00 --right-start 08:00 --left-end 22:00 --right-end 22:00

# Sync device clock to local clock
python3 src/potager_ble.py set --clock-now

# Save and restore auto state
python3 src/potager_ble.py auto-save
python3 src/potager_ble.py auto-restore
python3 src/potager_ble.py auto-restore --use-saved-clock
```

## 4) MQTT contract

All topics are based on `POTAGER_TOPIC_PREFIX` (default: `potager/modulo2`).

Input topics:

- `<prefix>/state/set`: `off|auto|manuel|printemps|ete|été|photo`.
- `<prefix>/save`: payload `trigger` (fetch BLE profile and update MQTT retained topics).
- `<prefix>/auto`: JSON profile payload.
- `<prefix>/manuel`: JSON profile payload.

State semantics:

- `auto` and `manuel` use their corresponding JSON profiles (`<prefix>/auto` and `<prefix>/manuel`).
- `off`, `printemps`, `ete|été`, and `photo` are preconfigured profiles defined in the protocol layer.
- MQTT payloads remain human-readable; numeric BLE conversion is handled by `modulo2_protocol` and mapping files.

Profile payload format (same for auto/manuel):

```json
{
  "left_intensity": "printemps",
  "right_intensity": "printemps",
  "left_start": "08:00",
  "right_start": "08:00",
  "left_end": "22:00",
  "right_end": "22:00"
}
```

Output/status topics:

- `<prefix>/availability`: `online|offline` (retained).
- `<prefix>/state`: current mode value (`off|auto|manuel|printemps|ete|photo`) or `null` (retained).
- `<prefix>/clock`: current clock seconds value (read-only, retained).
- `<prefix>/auto`: JSON profile snapshot (retained).
- `<prefix>/manuel`: JSON profile snapshot (retained).
- `<prefix>/status/device-write`: transient status (`sent|skipped|error`).
- `<prefix>/status/active-profile`: transient status for active profile completeness.
- `<prefix>/status/last-command`: transient status with last interpreted command.

Null semantics:

- If a profile field is `null`, it is kept as `null` in the retained profile topic.
- If at least one required profile field is `null`, no BLE write is sent when that profile is activated.
- Channels not listed in the profile payload are ignored and never written by this contract.

Read-only semantics:

- `<prefix>/clock` is not a command topic.
- Clock is refreshed from BLE on each `save` trigger read.

Save semantics:

- Publishing `trigger` on `<prefix>/save` reads current BLE profile fields.
- Bridge updates `<prefix>/auto` with fetched profile values.
- Bridge also updates `<prefix>/clock` with the device clock read during save.

BLE address semantics:

- The bridge uses configured `POTAGER_ADDRESS` / `--address` as the single BLE target.
- Name-based BLE scan has been removed in favor of robust connection retries.

## 5) BLE protocol mapping (Modulo2)

Service UUID:

- `0000fe95-0000-1000-8000-00805f9b34fb`

Characteristics:

| UUID | Key | Role | Scope | Format | Confidence |
| --- | --- | --- | --- | --- | --- |
| `c9d9bff2-324c-4b79-bbaf-8a473e6540ec` | `clock` | Internal clock / time counter | Global | u32 little-endian seconds since midnight | High |
| `c9d9bff3-324c-4b79-bbaf-8a473e6540ec` | `left_profile_param` | Left preset parameter | Left | 1 byte | Medium |
| `c9d9bff4-324c-4b79-bbaf-8a473e6540ec` | `right_profile_param` | Right preset parameter | Right | 1 byte | Medium |
| `c9d9bff5-324c-4b79-bbaf-8a473e6540ec` | `left_intensity` | Left intensity | Left | 1 byte | Very high |
| `c9d9bff6-324c-4b79-bbaf-8a473e6540ec` | `right_intensity` | Right intensity | Right | 1 byte | Very high |
| `c9d9bff7-324c-4b79-bbaf-8a473e6540ec` | `left_start` | Left start time | Left | u32 LE seconds since midnight | High |
| `c9d9bff8-324c-4b79-bbaf-8a473e6540ec` | `right_start` | Right start time | Right | u32 LE seconds since midnight | High |
| `c9d9bff9-324c-4b79-bbaf-8a473e6540ec` | `left_end` | Left end time | Left | u32 LE seconds since midnight | High |
| `c9d9bffa-324c-4b79-bbaf-8a473e6540ec` | `right_end` | Right end time | Right | u32 LE seconds since midnight | High |
| `c9d9bffb-324c-4b79-bbaf-8a473e6540ec` | `flags` | Capability/version flag | Global | 1 byte (observed RO) | Medium |
| `c9d9bffc-324c-4b79-bbaf-8a473e6540ec` | `reserved` | Reserved/auxiliary field | Global | 4 bytes | Low/Medium |

Intensity scale (`left_intensity`, `right_intensity`):

- `0x00` -> `off`
- `0x14` -> `photo`
- `0x32` -> `faible`
- `0x4B` -> `printemps`
- `0x64` -> `ete`

Time encoding examples:

- `0x00007080` LE (`80 70 00 00`) = `28800` = `08:00:00`
- `0x000123CC` LE (`cc 23 01 00`) = `74700` = `20:45:00`

## 6) Auto-state snapshot format

Daemon MQTT mode uses broker-retained data (no local profile file persistence):

- `<prefix>/auto` is the source of truth for auto profile data.
- `<prefix>/save` updates this retained profile from BLE fetch.
- Setting state to `auto` reapplies retained `<prefix>/auto` to BLE when profile is complete.

CLI `auto-save` / `auto-restore` commands remain available as local file workflow for one-shot/manual operations.

## 7) Docker/compose

Build image:

```bash
just docker-build
```

Start stack:

```bash
just compose-up
just compose-logs
```

Stop stack:

```bash
just compose-down
```

MQTT web client:

- Service: `mqtt-web-client` in `docker-compose.yml`
- URL: `https://<MQTT_WEB_HOST>` (default `https://mqtt.doudou.house`)
- Protection: Traefik basic auth middleware `auth@docker` (same password file as Traefik dashboard)

## 8) Notes

- No `sudo` is used in scripts/recipes.
- If BLE cannot connect, check adapter name, bluetooth service state, and scan visibility with `just doctor`.
- The source of truth for protocol constants is `src/config/modulo2_mapping.json`.
