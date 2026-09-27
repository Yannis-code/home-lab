import { defineConfig } from "@playwright/test";

const FRONTEND_PORT = 5173;
const BACKEND_PORT = 8000;
const REPO_ROOT = new URL("..", import.meta.url).pathname;
const DB_PATH = `${REPO_ROOT}e2e.db`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `rm -f ${DB_PATH} && ${REPO_ROOT}.venv/bin/uvicorn covoit.main:app --app-dir ${REPO_ROOT}src --host 127.0.0.1 --port ${BACKEND_PORT}`,
      port: BACKEND_PORT,
      env: {
        COVOIT_DATABASE_URL: `sqlite:///${DB_PATH}`,
        COVOIT_ADMIN_EMAIL: "admin@covoit.home",
        COVOIT_ADMIN_PASSWORD: "AdminPass123!",
        COVOIT_SESSION_TTL_HOURS: "168",
      },
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "npm run dev:coverage -- --port 5173 --host 127.0.0.1 --strictPort",
      port: FRONTEND_PORT,
      env: { VITE_COVERAGE: "true" },
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
