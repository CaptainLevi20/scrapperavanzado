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
  build: {
    // La oficina tiene equipos con Chrome congelado en la 109 (Windows 8 no
    // permite actualizar Chrome más allá de esa versión). Se fija el objetivo de
    // compilación a ese piso para que esbuild rebaje cualquier sintaxis moderna
    // —de la app o de dependencias como pdf.js— a algo que la 109 sí entienda.
    // Las funciones nuevas en tiempo de ejecución (Promise.withResolvers,
    // URL.parse, …) no se pueden rebajar así: esas se cubren con los polyfills
    // en src/lib/polyfills.ts.
    target: ["chrome109", "edge109", "firefox115", "safari15"],
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
