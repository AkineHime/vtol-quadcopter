import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the UI with hot reload and forwards API/WebSocket calls
// to the backend (python run.py) on https://localhost:8443.
const backend = { target: "https://localhost:8443", secure: false, changeOrigin: true };

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": backend,
      "/media": backend,
      "/ws": { ...backend, ws: true },
    },
  },
});
