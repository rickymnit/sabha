import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the browser calls the API on this same origin: Vite forwards these paths to it, so no CORS is
// needed for the API (uploads go straight to storage, whose CORS rules scripts/dev_storage.py sets).
const api = "http://localhost:8000"; // `make api`

export default defineConfig({
  plugins: [react()],
  server: {
    // 5180, not Vite's default 5173, so Sabha never collides with other projects' dev servers.
    port: 5180,
    strictPort: true,
    proxy: {
      "/v1": api,
      "/dev-idp": api,
      "/health": api,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
