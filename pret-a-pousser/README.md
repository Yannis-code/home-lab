# pret-a-pousser BLE bridge (Modulo2)

Bridge BLE -> MQTT for Pret a Pousser Modulo2.

This folder now uses a modular layout:

- `src/potager_ble.py`: CLI entrypoint (commands + config + logging).
- `src/ble_controller.py`: BLE discovery/read/write + auto-state snapshot/restore.
- `src/mqtt_bridge.py`: MQTT subscriptions/publications and protocol topic handlers.
- `src/modulo2_protocol.py`: protocol wrapper (UUIDs, presets, encoders, builders).
- `src/modulo2_mapping.json`: static protocol constants and channel groups.
- `src/app_defaults.json`: static app defaults.
- `src/config_models.py`: typed app config dataclass.

## 1) Requirements

- Linux host with BlueZ and BLE adapter (`hci0` recommended unless overridden).
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

Control topics:

- `<prefix>/set`: payload `ON` or `OFF`
- `<prefix>/channels/set`: JSON batch payload for protocol fields
- `<prefix>/left/intensity/set`: `off|photo|faible|printemps|ete|0..255`
- `<prefix>/right/intensity/set`: same as left
- `<prefix>/left/start/set`: `HH:MM[:SS]`
- `<prefix>/right/start/set`: `HH:MM[:SS]`
- `<prefix>/left/end/set`: `HH:MM[:SS]`
- `<prefix>/right/end/set`: `HH:MM[:SS]`
- `<prefix>/clock/set`: `NOW` or `HH:MM[:SS]` or seconds-from-midnight
- `<prefix>/left/profile-param/set`: raw byte payload (hex or decimal)
- `<prefix>/right/profile-param/set`: raw byte payload (hex or decimal)
- `<prefix>/reserved/set`: raw byte payload (hex or decimal)
- `<prefix>/auto/save/set`: trigger auto-save (`1|ON|SAVE` or empty)
- `<prefix>/auto/restore/set`: trigger auto-restore (`1|ON|RESTORE` or empty)

State topics:

- `<prefix>/availability`: `online|offline` (retained)
- `<prefix>/state`: last ON/OFF command state
- `<prefix>/error`: last error string (empty when clear)
- `<prefix>/auto/saved`: JSON status of latest snapshot
- `<prefix>/auto/restored`: JSON status of latest restore

`<prefix>/channels/set` example:

```json
{
  "left_intensity": "printemps",
  "right_intensity": "printemps",
  "left_start": "08:00",
  "right_start": "08:00",
  "left_end": "22:00",
  "right_end": "22:00",
  "clock_now": true,
  "mirror_sides": false
}
```

Optional raw fields in batch payload:

- `left_profile_param`
- `right_profile_param`
- `reserved`

Accepted raw formats for these fields:

- decimal byte: `195`
- hex byte: `0xC3`
- contiguous hex bytes: `c300` or `0xc300`
- spaced hex bytes: `c3 00`

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

`auto-save` writes JSON with:

- metadata (`schema`, `saved_at`, `device_name`, `device_address`)
- `channels.<key>.uuid`
- `channels.<key>.hex`

Default file is controlled by `POTAGER_AUTO_STATE_FILE`:

- local runs: `./.cache/auto_mode_state.json`
- container runs: `/data/auto_mode_state.json`

Restore behavior:

- by default, `clock` is overwritten with current local time
- `--use-saved-clock` restores `clock` from snapshot instead

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
- The source of truth for protocol constants is `src/modulo2_mapping.json`.
