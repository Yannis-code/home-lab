# Home Lab SSO

This stack provides Keycloak OIDC and oauth2-proxy for the Traefik
`sso-chain` middleware. Routes that previously used the Traefik `auth`
Basic auth middleware now redirect to Keycloak.

Copy `sso/.env.example` to the repository root as `.env` and set real values
before starting the root Compose stack. `OAUTH2_PROXY_CLIENT_SECRET` must match the client secret in
`realm/home-lab-realm.json`; change both values together before the first
Keycloak start.