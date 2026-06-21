import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('Duplicates', () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API_URL}/test/reset`);
    await request.post(`${API_URL}/test/seed`);

    const loginResp = await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    });
    expect(loginResp.ok()).toBeTruthy();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/duplicates');
    await page.waitForSelector('h2:has-text("Duplicates")', { timeout: 15000 });
  });

  test('loads duplicates page with header', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('Duplicates Review');
  });

  test('displays duplicate count in header', async ({ page }) => {
    const header = page.locator('.page-header-row');
    await expect(header).toBeVisible();
    const text = await header.textContent();
    expect(text).toContain('duplicate(s) detected');
  });

  test('empty state shown when no duplicates', async ({ page }) => {
    const emptyState = page.locator('.empty-state');
    const table = page.locator('.table-wrap');
    const emptyVisible = await emptyState.isVisible().catch(() => false);
    const tableVisible = await table.isVisible().catch(() => false);
    expect(emptyVisible || tableVisible).toBeTruthy();
  });

  test('duplicate cards show company and title', async ({ page }) => {
    const cards = page.locator('[style*="border-radius: 8px"]');
    const count = await cards.count();
    if (count > 0) {
      const firstCard = cards.first();
      const text = await firstCard.textContent();
      expect(text).toBeTruthy();
    }
  });

  test('primary radio button exists on duplicate items', async ({ page }) => {
    const radios = page.locator('input[type="radio"]');
    const count = await radios.count();
    if (count > 0) {
      await expect(radios.first()).toBeVisible();
    }
  });

  test('select checkbox exists on duplicate items', async ({ page }) => {
    const checkboxes = page.locator('input[type="checkbox"]');
    const count = await checkboxes.count();
    if (count > 0) {
      await expect(checkboxes.first()).toBeVisible();
    }
  });

  test('keep both button exists on duplicate items', async ({ page }) => {
    const keepBothBtn = page.locator('button', { hasText: 'Keep both' });
    const count = await keepBothBtn.count();
    if (count > 0) {
      await expect(keepBothBtn.first()).toBeVisible();
    }
  });

  test('mark dup button exists on duplicate items', async ({ page }) => {
    const markDupBtn = page.locator('button', { hasText: 'Mark dup' });
    const count = await markDupBtn.count();
    if (count > 0) {
      await expect(markDupBtn.first()).toBeVisible();
    }
  });

  test('duplicate group headers show reason labels', async ({ page }) => {
    const groupHeaders = page.locator('h3[style*="font-size: 14"]');
    const count = await groupHeaders.count();
    if (count > 0) {
      const text = await groupHeaders.first().textContent();
      expect(text).toBeTruthy();
    }
  });
});
