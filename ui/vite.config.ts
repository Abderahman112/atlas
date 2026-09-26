import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8787 (python -m atlas); Vite proxies to it.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/ws": { target: "ws://127.0.0.1:8787", ws: true },
      "/api": "http://127.0.0.1:8787",
    },
  },
});
