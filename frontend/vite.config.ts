import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Served from the root. Every asset URL and every API call is built relative to
// `base` (see src/lib/api.ts), so this is the only line that would need to change
// if the app ever moved to a sub-path.
const BASE = "/";

// The dev server proxies /api to the Python process, which puts both on one origin.
// That is why there is no CORS configuration anywhere in this project.
const API_TARGET = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  base: BASE,
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // Charts are the heaviest dependency and are not needed for first paint.
        manualChunks: {
          charts: ["recharts"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Straight pass-through: the API already serves everything the browser needs
      // under /api, including its own docs at /api/docs. No path rewriting, which
      // is one fewer thing that can silently break.
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // The default 5s is a measure of machine speed, not of correctness. Rendering
    // React plus Recharts under jsdom is several times slower on Windows than on
    // Linux, and a suite that fails on a slower laptop teaches you to distrust it.
    // 20s is still far below anything that indicates a genuine hang.
    testTimeout: 20_000,
    hookTimeout: 20_000,
  },
});
