import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import istanbul from "vite-plugin-istanbul";
import { VitePWA } from "vite-plugin-pwa";

const BACKEND_URL = process.env.COVOIT_BACKEND_URL || "http://127.0.0.1:8000";

// Chemins de l'API backend à proxifier tels quels en développement (même
// origine pour le navigateur, pas de configuration CORS nécessaire).
const API_PATHS = [
  "/auth",
  "/users",
  "/admin",
  "/groups",
  "/vehicles",
  "/trips",
  "/recurring-models",
  "/reimbursements",
  "/health",
];

export default defineConfig({
  plugins: [
    vue(),
    istanbul({
      include: "src/*",
      exclude: ["node_modules", "e2e"],
      extension: [".ts", ".vue"],
      requireEnv: true,
      forceBuildInstrument: process.env.VITE_COVERAGE === "true",
    }),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/icon.svg"],
      manifest: {
        name: "Covoit",
        short_name: "Covoit",
        description: "Groupes de covoiturage, trajets et frais partagés",
        start_url: ".",
        scope: ".",
        display: "standalone",
        background_color: "#0f172a",
        theme_color: "#0f172a",
        lang: "fr",
        icons: [{ src: "icons/icon.svg", sizes: "any", type: "image/svg+xml" }],
      },
      workbox: {
        runtimeCaching: [
          {
            // Consultation hors ligne uniquement: réseau prioritaire, secours
            // par le cache pour les lectures déjà vues (les écritures échouent
            // hors connexion, conformément à la spécification).
            urlPattern: ({ url, request }) =>
              request.method === "GET" && API_PATHS.some((p) => url.pathname.startsWith(p)),
            handler: "NetworkFirst",
            options: { cacheName: "covoit-api" },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: Object.fromEntries(API_PATHS.map((p) => [p, { target: BACKEND_URL, changeOrigin: true }])),
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
