import { defineConfig, devices } from '@playwright/test';

const authenticatedChromium = {
  ...devices['Desktop Chrome'],
  storageState: 'tests/.auth/user.json',
};

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'html',
  timeout: 30000,
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    actionTimeout: 10000,
    navigationTimeout: 15000,
  },
  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      // The full browser suite runs in an explicit zone so host TZ never becomes
      // an undeclared part of the test contract.
      name: 'chromium-utc',
      use: {
        ...authenticatedChromium,
        timezoneId: 'UTC',
      },
      dependencies: ['setup'],
    },
    {
      // C-06 time-contract scenarios are repeated in a non-DST offset zone.
      name: 'chromium-kolkata',
      grep: /@time-zone/,
      use: {
        ...authenticatedChromium,
        timezoneId: 'Asia/Kolkata',
      },
      dependencies: ['setup'],
    },
    {
      // Repeat the same scenarios in a DST-observing zone.
      name: 'chromium-new-york',
      grep: /@time-zone/,
      use: {
        ...authenticatedChromium,
        timezoneId: 'America/New_York',
      },
      dependencies: ['setup'],
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});
