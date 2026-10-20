# Web image (plan task P1.2): build the static app, then serve it with nginx and security headers.
# Build from the repo root:
#   docker build -f apps/web/Dockerfile -t sabha-web .
# Run: CSP_CONNECT_SRC lists the origins the browser may call (API, the identity provider for sign-in and token
# renewal, and the S3 bucket for direct uploads).

FROM node:22.23.0-alpine AS build
RUN corepack enable
WORKDIR /web
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web ./
# Sign-in settings are baked into the bundle (apps/web/.env.example); pass them with --build-arg. Not secrets.
ARG VITE_OIDC_AUTHORITY VITE_OIDC_CLIENT_ID VITE_OIDC_AUDIENCE
RUN pnpm build

FROM nginxinc/nginx-unprivileged:1.28-alpine
# Files in /etc/nginx/templates are rendered with envsubst at start-up (only the variables listed below).
ENV CSP_CONNECT_SRC="'self'" NGINX_ENVSUBST_FILTER="^CSP_"
COPY apps/web/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
