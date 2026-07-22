# Cockpit setup

Structure:

- `cockpit-machines.sh`: setup script (install/revert/status/check/doctor/logs/url)
- `config/cockpit-machines.conf.example`: configurable defaults example
- `config/cockpit-machines.conf`: local config (not tracked)
- `state/`: local runtime/state artifacts directory

Quick start:

```bash
cd cockpit
just init-config
just check
just url
```

Common commands:

- `just install`
- `just status`
- `just check`
- `just doctor`
- `just logs`
- `just url`
- `just revert`

Notes:

- The script auto-loads `COCKPIT_ENV_FILE` if set, else `./config/cockpit-machines.conf`.
- Set `COCKPIT_MANAGE_FIREWALL=true` in config to automatically manage port 9090 rules.
