import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end configuration.
 *
 * Both servers are started by Playwright so a contributor needs one command,
 * and so CI does not need a bespoke orchestration script.
 *
 * The API runs against a **file-backed SQLite database** rather than
 * PostgreSQL. The migrations are deliberately dialect-neutral and are verified
 * against a real PostgreSQL service in a separate CI job, so the E2E run does
 * not need a database service to prove the user journey works.
 */
const API_PORT = 8001;
const WEB_PORT = 4173;
const API_URL = `http://127.0.0.1:${API_PORT}`;
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;

const apiEnvironment = {
  OBSEIL_ENV: 'test',
  OBSEIL_DEBUG: 'true',
  OBSEIL_LOG_LEVEL: 'WARNING',
  OBSEIL_SECRET_KEY: 'end-to-end-secret-not-used-outside-tests-0123456789',
  OBSEIL_DATABASE_URL: 'sqlite+pysqlite:///./var/e2e.db',
  OBSEIL_STORAGE_PATH: './var/e2e-datasets',
  OBSEIL_CORS_ORIGINS: `${WEB_URL},http://localhost:${WEB_PORT}`,
};

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  timeout: 90_000,
  expect: { timeout: 15_000 },

  use: {
    baseURL: WEB_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // The product promises the tables stay usable on a phone, so the journey
    // is exercised at a phone width too rather than only asserted in review.
    { name: 'mobile', use: { ...devices['Pixel 7'] }, testMatch: /journey\.spec\.ts/ },
  ],

  webServer: [
    {
      // Requires the backend environment on PATH (an activated virtualenv, or
      // CI's installed dependencies) - the same requirement as running pytest.
      command: `alembic upgrade head && uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: '../backend',
      url: `${API_URL}/api/v1/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: apiEnvironment,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      // The production build, not the dev server: the E2E suite should exercise
      // what users actually receive, including the chunking and minification.
      command: 'npm run build && npm run preview',
      cwd: '../frontend',
      url: WEB_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: { VITE_API_BASE_URL: `${API_URL}/api/v1` },
      stdout: 'ignore',
      stderr: 'pipe',
    },
  ],
});
