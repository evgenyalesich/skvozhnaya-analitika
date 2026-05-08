import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    sourcemap: true,
  },
  server: {
    port: 4173,
    proxy: {
      "/api": {
        target: "https://roistat.pokerhub.pro",
        changeOrigin: true,
        secure: true,
      },
    },
  },
  preview: {
    port: 4173,
    allowedHosts: ["roistat.pokerhub.pro"],
  },
});
