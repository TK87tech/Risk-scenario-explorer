import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // GitHub Pages serves the static demo from /<repo>/; Docker and local dev serve from /.
  base: process.env.VITE_BASE ?? "/",
  server: { port: 5173, strictPort: true },
  build: {
    // MapLibre is most of the bundle; keep it in its own long-cached chunk so app updates stay small.
    rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"] } } },
    chunkSizeWarningLimit: 1100,
  },
});
