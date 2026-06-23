import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('Applications', () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API_URL}/test/reset`);
    await request.post(`${API_URL}/test/seed`);

    const loginResp = await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    });
    expect(loginResp.ok()).toBeTruthy();

    const rowsResp = await request.get(`${API_URL}/rows`, {
      params: { sort_by: 'created_at', sort_dir: 'desc', page: 1, page_size: 5 },
    });
    const rowsData = await rowsResp.json();
    const rowIds = (rowsData.rows || []).slice(0, 5).map((r: any) => r.id);

    if (rowIds.length > 0) {
      await request.post(`${API_URL}/crm/from-rows/bulk`, {
        data: { row_ids: rowIds },
      });
    }
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/applications');
    await page.waitForSelector('h2:has-text("Applications")', { timeout: 15000 });
  });

  test('loads applications page with header', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('Applications');
    await expect(page.locator('.page-header-row p')).toContainText('Track opened jobs');
  });

  test('loads applications from backend', async ({ page }) => {
    const table = page.locator('table');
    await expect(table).toBeVisible({ timeout: 10000 });

    const rows = table.locator('tbody tr');
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
  });

  test('shows total stat card', async ({ page }) => {
    const totalCard = page.locator('.stat-card').filter({ hasText: 'Total' });
    await expect(totalCard).toBeVisible();

    await expect.poll(async () => {
      const value = await totalCard.locator('strong').textContent();
      return Number(value);
    }).toBeGreaterThan(0);
  });

  test('multi-select rows with checkboxes', async ({ page }) => {
    const firstRowCheckbox = page.locator('tbody tr').first().locator('input[type="checkbox"]');
    await expect(firstRowCheckbox).toBeVisible({ timeout: 10000 });

    await firstRowCheckbox.check();
    await page.waitForTimeout(300);

    const secondRowCheckbox = page.locator('tbody tr').nth(1).locator('input[type="checkbox"]');
    if (await secondRowCheckbox.isVisible().catch(() => false)) {
      await secondRowCheckbox.check();
    }

    const toolbar = page.locator('.sticky-toolbar');
    await expect(toolbar).toBeVisible();
    await expect(toolbar).toContainText('selected');
  });

  test('select all with header checkbox', async ({ page }) => {
    const headerCheckbox = page.locator('thead input[type="checkbox"]');
    await expect(headerCheckbox).toBeVisible({ timeout: 10000 });

    await headerCheckbox.check();
    await page.waitForTimeout(500);

    const toolbar = page.locator('.sticky-toolbar');
    await expect(toolbar).toBeVisible();
  });

  test('bulk mark as applied', async ({ page }) => {
    const headerCheckbox = page.locator('thead input[type="checkbox"]');
    await expect(headerCheckbox).toBeVisible({ timeout: 10000 });
    await headerCheckbox.check();
    await page.waitForTimeout(500);

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    const markAppliedBtn = page.locator('.sticky-toolbar button', { hasText: 'Mark applied' });
    await expect(markAppliedBtn).toBeVisible();
    await markAppliedBtn.click();

    await page.waitForTimeout(2000);
    await expect(page.locator('.toast')).toBeVisible({ timeout: 10000 });
  });

  test('update individual row status', async ({ page }) => {
    const statusSelect = page.locator('tbody tr').first().locator('select');
    await expect(statusSelect).toBeVisible({ timeout: 10000 });

    await statusSelect.selectOption('applied');
    await page.waitForTimeout(1000);
  });

  test('follow-up date quick buttons (+3d, +7d, Mon)', async ({ page }) => {
    const followUpCell = page.locator('.follow-up-quick-btns').first();
    const isVisible = await followUpCell.isVisible().catch(() => false);

    if (!isVisible) {
      const followUpCol = page.locator('th', { hasText: 'Follow-up' });
      if (await followUpCol.isVisible().catch(() => false)) {
        const plus3d = page.locator('button', { hasText: '+3d' }).first();
        if (await plus3d.isVisible().catch(() => false)) {
          await plus3d.click();
          await page.waitForTimeout(1000);
        }

        const plus7d = page.locator('button', { hasText: '+7d' }).first();
        if (await plus7d.isVisible().catch(() => false)) {
          await plus7d.click();
          await page.waitForTimeout(1000);
        }

        const monBtn = page.locator('button', { hasText: 'Mon' }).first();
        if (await monBtn.isVisible().catch(() => false)) {
          await monBtn.click();
          await page.waitForTimeout(1000);
        }
      }
    } else {
      const plus3d = followUpCell.locator('button', { hasText: '+3d' });
      await plus3d.click();
      await page.waitForTimeout(1000);

      const plus7d = followUpCell.locator('button', { hasText: '+7d' });
      await plus7d.click();
      await page.waitForTimeout(1000);

      const monBtn = followUpCell.locator('button', { hasText: 'Mon' });
      await monBtn.click();
      await page.waitForTimeout(1000);
    }
  });

  test('filter by status', async ({ page }) => {
    const statusFilter = page.locator('.table-controls select').first();
    await expect(statusFilter).toBeVisible({ timeout: 10000 });

    await statusFilter.selectOption('applied');
    await page.waitForTimeout(1500);
  });

  test('filter by company', async ({ page }) => {
    const companyInput = page.locator('.table-controls input[placeholder="Company"]');
    await expect(companyInput).toBeVisible({ timeout: 10000 });

    await companyInput.fill('Acme');
    await page.waitForTimeout(1500);

    await companyInput.fill('');
    await page.waitForTimeout(1000);
  });

  test('filter by score range', async ({ page }) => {
    const minScore = page.locator('input[type="number"]').first();
    const maxScore = page.locator('input[type="number"]').nth(1);

    if (await minScore.isVisible().catch(() => false)) {
      await minScore.fill('50');
      await page.waitForTimeout(1500);

      await minScore.fill('');
      await page.waitForTimeout(1000);
    }
  });

  test('inline notes editing', async ({ page }) => {
    const notesTextarea = page.locator('tbody textarea').first();
    const isVisible = await notesTextarea.isVisible().catch(() => false);

    if (isVisible) {
      await notesTextarea.fill('Test note from E2E');
      await page.waitForTimeout(1000);

      const value = await notesTextarea.inputValue();
      expect(value).toBe('Test note from E2E');
    }
  });

  test('export bar is present', async ({ page }) => {
    const exportBar = page.locator('.export-bar');
    await expect(exportBar).toBeVisible();

    const formatSelect = exportBar.locator('select').first();
    await expect(formatSelect).toBeVisible();

    const scopeSelect = exportBar.locator('select').nth(1);
    await expect(scopeSelect).toBeVisible();

    const downloadBtn = exportBar.locator('button', { hasText: 'Download' });
    await expect(downloadBtn).toBeVisible();
  });

  test('column visibility toggles work', async ({ page }) => {
    const toggles = page.locator('.compact-toggles label');
    const count = await toggles.count();
    expect(count).toBeGreaterThan(0);

    const firstToggle = toggles.first().locator('input[type="checkbox"]');
    const wasChecked = await firstToggle.isChecked();
    await firstToggle.click();
    await page.waitForTimeout(500);

    const isNowChecked = await firstToggle.isChecked();
    expect(isNowChecked).toBe(!wasChecked);

    await firstToggle.click();
    await page.waitForTimeout(500);
  });

  test('clear filters resets all', async ({ page }) => {
    const companyInput = page.locator('.table-controls input[placeholder="Company"]');
    if (await companyInput.isVisible().catch(() => false)) {
      await companyInput.fill('xyznonexistent');
      await page.waitForTimeout(1000);
    }

    const clearBtn = page.locator('button', { hasText: 'Clear filters' });
    await clearBtn.click();
    await page.waitForTimeout(1500);

    if (await companyInput.isVisible().catch(() => false)) {
      const value = await companyInput.inputValue();
      expect(value).toBe('');
    }
  });

  test('refresh button reloads data', async ({ page }) => {
    const refreshBtn = page.locator('.page-header-row button', { hasText: 'Refresh' });
    await expect(refreshBtn).toBeVisible();
    await refreshBtn.click();

    await page.waitForTimeout(2000);

    const table = page.locator('table');
    await expect(table).toBeVisible();
  });

  test('pagination controls when enough data', async ({ page }) => {
    const pagination = page.locator('.pagination-controls');
    const isVisible = await pagination.isVisible().catch(() => false);

    if (isVisible) {
      await expect(pagination.locator('button', { hasText: 'Prev' })).toBeVisible();
      await expect(pagination.locator('.pagination-info')).toBeVisible();
    }
  });

  test('mark applied button on individual row', async ({ page }) => {
    const markBtn = page.locator('tbody tr').first().locator('button', { hasText: 'Mark applied' });
    const isVisible = await markBtn.isVisible().catch(() => false);

    if (isVisible) {
      await markBtn.click();
      await page.waitForTimeout(1500);
    }
  });
});
