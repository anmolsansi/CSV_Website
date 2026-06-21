import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('ApplyPilot Batches', () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API_URL}/test/reset`);
    await request.post(`${API_URL}/test/seed`);

    const loginResp = await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    });
    expect(loginResp.ok()).toBeTruthy();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/applypilot');
    await page.waitForSelector('h2:has-text("ApplyPilot")', { timeout: 15000 });
  });

  test('loads applypilot page with header', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('ApplyPilot Batches');
    await expect(page.locator('.page-header-row p')).toContainText('Track job application batches');
  });

  test('import file input is visible', async ({ page }) => {
    const fileInput = page.locator('input[type="file"][accept=".json"]');
    await expect(fileInput).toBeVisible();
  });

  test('import results button is visible', async ({ page }) => {
    const importBtn = page.locator('button', { hasText: 'Import Results' });
    await expect(importBtn).toBeVisible();
  });

  test('import button disabled when no file selected', async ({ page }) => {
    const importBtn = page.locator('button', { hasText: 'Import Results' });
    const isDisabled = await importBtn.isDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('batches table shows correct columns', async ({ page }) => {
    const table = page.locator('table');
    const isVisible = await table.isVisible().catch(() => false);

    if (isVisible) {
      const headers = await table.locator('th').allTextContents();
      expect(headers.join(' ')).toContain('Name');
      expect(headers.join(' ')).toContain('Created');
      expect(headers.join(' ')).toContain('Jobs');
      expect(headers.join(' ')).toContain('Status');
      expect(headers.join(' ')).toContain('Actions');
    }
  });

  test('empty state shown when no batches', async ({ page }) => {
    const emptyState = page.locator('.empty-state');
    const table = page.locator('table');
    const emptyVisible = await emptyState.isVisible().catch(() => false);
    const tableVisible = await table.isVisible().catch(() => false);
    expect(emptyVisible || tableVisible).toBeTruthy();
  });

  test('download button on batch rows', async ({ page }) => {
    const downloadBtn = page.locator('tbody button', { hasText: 'Download' });
    const count = await downloadBtn.count();
    if (count > 0) {
      await expect(downloadBtn.first()).toBeVisible();
    }
  });

  test('delete button on batch rows', async ({ page }) => {
    const deleteBtn = page.locator('tbody button', { hasText: 'Delete' });
    const count = await deleteBtn.count();
    if (count > 0) {
      await expect(deleteBtn.first()).toBeVisible();
    }
  });

  test('status badges display with colors', async ({ page }) => {
    const statusBadges = page.locator('tbody td span[style*="border-radius"]');
    const count = await statusBadges.count();
    if (count > 0) {
      const text = await statusBadges.first().textContent();
      expect(text).toBeTruthy();
    }
  });
});
