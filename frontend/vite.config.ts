import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In dev, /api is proxied to the FastAPI server so the app always calls same-origin /api,
// exactly as it does on Vercel. Override the target with VITE_PROXY_TARGET.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // One page, no routes: a single chunk (~200 kB gzipped, mostly Recharts) is fine.
  build: { chunkSizeWarningLimit: 800 },
  server: {
    proxy: { "/api": process.env.VITE_PROXY_TARGET ?? "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
