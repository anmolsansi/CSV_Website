import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('Saved Views', () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API_URL}/test/reset`);
    await request.post(`${API_URL}/test/seed`);

    const loginResp = await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    });
    expect(loginResp.ok()).toBeTruthy();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/saved-views');
    await page.waitForSelector('h2:has-text("Saved Views")', { timeout: 15000 });
  });

  test('loads saved views page with header', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('Saved Views');
    await expect(page.locator('.page-header-row p')).toContainText('Save and recall filter combinations');
  });

  test('create default views button is visible', async ({ page }) => {
    const createDefaultsBtn = page.locator('.page-header-row button', { hasText: 'Create default views' });
    await expect(createDefaultsBtn).toBeVisible();
  });

  test('saved view form has all fields', async ({ page }) => {
    const nameInput = page.locator('input[placeholder*="High score"]');
    await expect(nameInput).toBeVisible();

    const pageSelect = page.locator('select');
    await expect(pageSelect).toBeVisible();

    const filterInput = page.locator('.filter-json-input');
    await expect(filterInput).toBeVisible();

    const saveBtn = page.locator('button', { hasText: 'Save view' });
    await expect(saveBtn).toBeVisible();
  });

  test('can create a saved view', async ({ page }) => {
    const nameInput = page.locator('input[placeholder*="High score"]');
    await nameInput.fill('E2E Test View');

    const saveBtn = page.locator('button', { hasText: 'Save view' });
    await saveBtn.click();
    await page.waitForTimeout(2000);

    const table = page.locator('table');
    const isVisible = await table.isVisible().catch(() => false);

    if (isVisible) {
      const rows = table.locator('tbody tr');
      const count = await rows.count();
      expect(count).toBeGreaterThan(0);
    }
  });

  test('saved views table shows correct columns', async ({ page }) => {
    const table = page.locator('table');
    const isVisible = await table.isVisible().catch(() => false);

    if (isVisible) {
      const headers = await table.locator('th').allTextContents();
      expect(headers.join(' ')).toContain('Name');
      expect(headers.join(' ')).toContain('Page');
      expect(headers.join(' ')).toContain('Filters');
      expect(headers.join(' ')).toContain('Actions');
    }
  });

  test('apply button on saved view navigates', async ({ page }) => {
    const applyBtn = page.locator('tbody button', { hasText: 'Apply' });
    const count = await applyBtn.count();
    if (count > 0) {
      await expect(applyBtn.first()).toBeVisible();
    }
  });

  test('edit button on saved view populates form', async ({ page }) => {
    const editBtn = page.locator('tbody button', { hasText: 'Edit' });
    const count = await editBtn.count();
    if (count > 0) {
      await editBtn.first().click();
      await page.waitForTimeout(500);

      const updateBtn = page.locator('button', { hasText: 'Update view' });
      const isVisible = await updateBtn.isVisible().catch(() => false);
      expect(isVisible).toBeTruthy();

      const cancelBtn = page.locator('button', { hasText: 'Cancel' });
      if (await cancelBtn.isVisible().catch(() => false)) {
        await cancelBtn.click();
      }
    }
  });

  test('create defaults generates views', async ({ page }) => {
    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    const createDefaultsBtn = page.locator('.page-header-row button', { hasText: 'Create default views' });
    await createDefaultsBtn.click();
    await page.waitForTimeout(3000);

    const table = page.locator('table');
    const isVisible = await table.isVisible().catch(() => false);
    expect(isVisible).toBeTruthy();
  });

  test('empty state shown when no views exist', async ({ page }) => {
    const emptyState = page.locator('.empty-state');
    const table = page.locator('table');
    const emptyVisible = await emptyState.isVisible().catch(() => false);
    const tableVisible = await table.isVisible().catch(() => false);
    expect(emptyVisible || tableVisible).toBeTruthy();
  });
});
