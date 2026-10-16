/// <reference types="vite/client" />

// Build-time settings (apps/web/.env.example). Only VITE_* variables reach the browser bundle; none are secrets.
interface ImportMetaEnv {
  readonly VITE_OIDC_AUTHORITY?: string;
  readonly VITE_OIDC_CLIENT_ID?: string;
  readonly VITE_OIDC_AUDIENCE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
