# Setting up sign-in (Auth0)

Sabha signs people in with Auth0 (docs/adr/0002-auth.md). Auth0 only checks who someone is. Their tenant, role and
units come from Sabha's own records, and people can use Sabha only after an owner or admin invites them (P1.5b).
These steps are done once per environment (dev, staging, production), in a separate Auth0 tenant for each.

## 1. Create the Auth0 tenant

1. Sign up at auth0.com and create a tenant per environment, for example `sabha-dev`.
2. Pick the region when you create the tenant: it cannot be changed later. The owner approved storing staff
   names and emails outside India on 2026-10-16 (ADR 0002). Note the region you picked in the ADR.
3. The issuer is `https://<tenant>.<region>.auth0.com/` (shown as "Domain" on any application, add `https://`).

## 2. Register the API

Applications → APIs → Create API:

| Field | Value |
| --- | --- |
| Name | Sabha API |
| Identifier | e.g. `https://api.sabha.dev`. This is the audience. It is a name, not a URL Auth0 calls, and it cannot be changed later |
| Signing algorithm | RS256 (the API refuses anything else) |

In the API's settings, turn on **Allow Offline Access**. Without it Auth0 issues no refresh tokens, and people are
signed out when their access token expires.

## 3. Register the web app

Applications → Applications → Create Application → **Single Page Web Applications**. In its settings:

| Field | Dev value | Staging/production |
| --- | --- | --- |
| Allowed Callback URLs | `http://localhost:5173/` | `https://<web host>/` |
| Allowed Logout URLs | `http://localhost:5173/` | `https://<web host>/` |
| Allowed Web Origins | `http://localhost:5173` | `https://<web host>` |
| Refresh Token Rotation | On | On |

Note its **Client ID**. A single-page app has no client secret.

## 4. Google login

Authentication → Social → Google, and enable it for the web app (the application's Connections tab).

- In dev you can use Auth0's development keys for Google.
- For staging and production, create an OAuth client in Google Cloud (OAuth consent screen, then Credentials →
  OAuth client ID, type "Web application"). Add `https://<tenant domain>/login/callback` as an authorised redirect
  URI and paste its client ID and secret into the Auth0 Google connection.

Under Authentication → Database, either turn off the "Username-Password-Authentication" connection for the web app
or disable sign-ups on it. Uninvited people are refused by the API anyway (403 `not_invited`), but there is no
reason to let them create provider accounts.

## 5. Sign-out

The web app signs out with the standard OIDC end-session endpoint. Check that
`https://<tenant domain>/.well-known/openid-configuration` lists `end_session_endpoint`. If it does not, turn on
RP-Initiated Logout in the tenant's advanced settings.

## 6. Configure Sabha

Root `.env` (API):

```
OIDC_ISSUER=https://<tenant domain>/
OIDC_AUDIENCE=<API identifier from step 2>
OIDC_CLIENT_ID=<Client ID from step 3>
```

`apps/web/.env.local` for `pnpm dev`, or `--build-arg` for the web image (see `apps/web/.env.example`):

```
VITE_OIDC_AUTHORITY=https://<tenant domain>/
VITE_OIDC_CLIENT_ID=<Client ID from step 3>
VITE_OIDC_AUDIENCE=<API identifier from step 2>
```

In staging and production, add `https://<tenant domain>` to the web container's `CSP_CONNECT_SRC`, or the browser
blocks sign-in and token renewal.

## Checking it works

1. Create a tenant and invite yourself as its owner, with the email of the Google account you will sign in with:
   `uv run python scripts/admin/create_tenant.py --name "Test School" --owner-email you@example.com --owner-name "You"`.
2. `make api` and `pnpm -C apps/web dev`, then open http://localhost:5173/. You should be sent to Auth0, sign in
   with Google, and come back to Sabha.
3. `GET /v1/me` with your access token returns your role (owner) and your tenant's labels. Your first sign-in
   links the invite to your login and marks you active.

Owners and admins invite everyone else with `POST /v1/users/invites` (owners any role; admins manager, reviewer
and staff). People sign in with the invited email; an unverified email, or invites from two organisations, are
refused with a clear error.
