import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes into `tan/api/static/` so FastAPI's StaticFiles mount serves it.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../tan/api/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
