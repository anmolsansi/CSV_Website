import { test as setup, expect } from '@playwright/test';
import fs from 'node:fs/promises';

const API_URL = 'http://localhost:8000';
const DEV_LOGIN_URL = `${API_URL}/auth/dev-login`;
const TEST_SEED_URL = `${API_URL}/test/seed`;
const TEST_RESET_URL = `${API_URL}/test/reset`;
const STORAGE_STATE_PATH = 'tests/.auth/user.json';

setup('authenticate and seed test data', async ({ request }) => {
  // Reset test data first
  await request.post(TEST_RESET_URL);

  // Login via dev-login endpoint
  const loginResponse = await request.post(DEV_LOGIN_URL, {
    data: { email: 'test@jobgrid.dev' },
  });
  expect(loginResponse.ok()).toBeTruthy();

  // Seed test data
  const seedResponse = await request.post(TEST_SEED_URL);
  expect(seedResponse.ok()).toBeTruthy();
  const seedData = await seedResponse.json();
  expect(seedData.rows_created).toBeGreaterThan(0);

  await fs.mkdir('tests/.auth', { recursive: true });
  await request.storageState({ path: STORAGE_STATE_PATH });
});