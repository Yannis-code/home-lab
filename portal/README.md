# Home Lab Portal

Standalone Angular portal for the services routed by Traefik.

## Run

The external Docker network must already exist:

```bash
docker compose up -d
```

Run this command from `portal/`. The application is published through
`https://doudou.house` by the Traefik labels in this Compose file.

The Angular frontend is built in a Node stage. The production image serves the
compiled assets and exposes `/api/routes`, which reads active Traefik labels
through the filtered `docker-socket-proxy` service.