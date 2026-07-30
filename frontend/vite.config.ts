import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
