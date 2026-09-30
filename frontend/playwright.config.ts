import { defineConfig, devices } from "@playwright/test";

const PORT = 8321;
const python = process.platform === "win32" ? "..\\.venv\\Scripts\\python" : "../.venv/bin/python";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
  // The real backend, serving the built UI, reading the committed snapshot: no network needed.
  webServer: {
    command: `${python} -m uvicorn datadoctor.api.main:app --app-dir ../backend --host 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    // DD_LLM_PROVIDER pinned: a developer's .env must not change what the tests see.
    env: { DD_SOURCE: "snapshot", DD_STARTUP_LIVE: "0", DD_DATA_DIR: "../data", DD_LLM_PROVIDER: "none" },
  },
});
