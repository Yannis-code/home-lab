# home-lab

This repository contains self-hosted infrastructure automation and runtime configuration.

## Components

- `haos/`: Home Assistant OS on libvirt/KVM managed with OpenTofu/Terraform
- `traefik/`: reverse proxy and TLS termination
- `cockpit/`: cockpit-machines setup and diagnostics

## Global network topology

```mermaid
flowchart LR
	Internet((Internet)) --> DNS[Cloudflare DNS]
	DNS --> TraefikHost[Traefik on host\n192.168.1.55]
	TraefikHost --> HAProxy[HA backend\n192.168.150.10:8123]
	HAProxy --> HAOS[HAOS VM]
	HAOS --> LAN[LAN IP via eth0\n192.168.1.x]
	HAOS --> NAT[NAT mgmt via ha-net\n192.168.150.10]
```

## Commands

Use `just` at repository root.

Cockpit:

- `just cockpit`
- `just cockpit::init-config`
- `just cockpit::install`
- `just cockpit::revert`
- `just cockpit::status`
- `just cockpit::check`
- `just cockpit::doctor`
- `just cockpit::logs`
- `just cockpit::url`

HAOS:

- `just haos`
- `just haos::init`
- `just haos::plan`
- `just haos::apply`
- `just haos::destroy`
- `just haos::output`
