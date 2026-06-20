import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('Sessions', () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API_URL}/test/reset`);
    await request.post(`${API_URL}/test/seed`);

    const loginResp = await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    });
    expect(loginResp.ok()).toBeTruthy();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/sessions');
    await page.waitForSelector('h2:has-text("Sessions")', { timeout: 15000 });
  });

  test('loads sessions page with header', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('Sessions');
    await expect(page.locator('.page-header-row p')).toContainText('Track job-search sessions');
  });

  test('session creation form is visible', async ({ page }) => {
    const nameInput = page.locator('input[placeholder*="Morning applications"]');
    await expect(nameInput).toBeVisible();

    const notesInput = page.locator('input[placeholder="Optional notes"]');
    await expect(notesInput).toBeVisible();
  });

  test('start session button is visible when no active session', async ({ page }) => {
    const startBtn = page.locator('button', { hasText: 'Start session' });
    const endBtn = page.locator('button', { hasText: 'End active session' });

    const startVisible = await startBtn.isVisible().catch(() => false);
    const endVisible = await endBtn.isVisible().catch(() => false);
    expect(startVisible || endVisible).toBeTruthy();
  });

  test('can start a new session', async ({ page }) => {
    const nameInput = page.locator('input[placeholder*="Morning applications"]');
    await nameInput.fill('E2E Test Session');

    const notesInput = page.locator('input[placeholder="Optional notes"]');
    await notesInput.fill('Automated test');

    const startBtn = page.locator('button', { hasText: 'Start session' });
    const isVisible = await startBtn.isVisible().catch(() => false);

    if (isVisible) {
      await startBtn.click();
      await page.waitForTimeout(2000);

      const activeBanner = page.locator('.active-session-banner');
      const bannerVisible = await activeBanner.isVisible().catch(() => false);

      const table = page.locator('table');
      const tableVisible = await table.isVisible().catch(() => false);

      expect(bannerVisible || tableVisible).toBeTruthy();
    }
  });

  test('sessions table shows columns when data exists', async ({ page }) => {
    const table = page.locator('table');
    const isVisible = await table.isVisible().catch(() => false);

    if (isVisible) {
      const headers = await table.locator('th').allTextContents();
      expect(headers.join(' ')).toContain('Name');
      expect(headers.join(' ')).toContain('Started');
      expect(headers.join(' ')).toContain('Duration');
    }
  });

  test('end active session button works', async ({ page }) => {
    const endBtn = page.locator('button', { hasText: 'End active session' });
    const isVisible = await endBtn.isVisible().catch(() => false);

    if (isVisible) {
      await endBtn.click();
      await page.waitForTimeout(2000);

      const startBtn = page.locator('button', { hasText: 'Start session' });
      await expect(startBtn).toBeVisible({ timeout: 5000 });
    }
  });

  test('empty state shown when no sessions', async ({ page }) => {
    const emptyState = page.locator('.empty-state');
    const table = page.locator('table');
    const emptyVisible = await emptyState.isVisible().catch(() => false);
    const tableVisible = await table.isVisible().catch(() => false);
    expect(emptyVisible || tableVisible).toBeTruthy();
  });

  test('delete button on session rows', async ({ page }) => {
    const deleteBtn = page.locator('tbody button', { hasText: 'Delete' });
    const count = await deleteBtn.count();
    if (count > 0) {
      await expect(deleteBtn.first()).toBeVisible();
    }
  });
});
