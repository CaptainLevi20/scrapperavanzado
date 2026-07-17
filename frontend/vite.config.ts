import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Lets an ngrok tunnel (whose Host header is a random *.ngrok-free.app
    // subdomain each run) reach the dev server for ad-hoc demos.
    allowedHosts: [".ngrok-free.app"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Tests hardcode BASE_URL = "http://localhost:8000" for MSW mocking — force the
    // same value here regardless of a local .env.local override (e.g. a developer
    // pointing their own dev server at a different port), so the two never diverge.
    env: {
      VITE_API_BASE_URL: "http://localhost:8000",
    },
  },
});
