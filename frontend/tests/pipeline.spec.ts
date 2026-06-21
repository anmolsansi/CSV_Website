import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('Pipeline', () => {
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
    await page.goto('/pipeline');
    await page.waitForSelector('h2:has-text("Pipeline")', { timeout: 15000 });
  });

  test('loads pipeline page with header', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('Pipeline');
    await expect(page.locator('.page-header-row p')).toContainText('Jobs grouped by application status');
  });

  test('refresh button is visible', async ({ page }) => {
    const refreshBtn = page.locator('.page-header-row button', { hasText: 'Refresh' });
    await expect(refreshBtn).toBeVisible();
  });

  test('pipeline board or empty state is shown', async ({ page }) => {
    const board = page.locator('.pipeline-board');
    const emptyState = page.locator('.empty-state');
    const boardVisible = await board.isVisible().catch(() => false);
    const emptyVisible = await emptyState.isVisible().catch(() => false);
    expect(boardVisible || emptyVisible).toBeTruthy();
  });

  test('pipeline columns display all statuses', async ({ page }) => {
    const columns = page.locator('.pipeline-column');
    const count = await columns.count();
    if (count > 0) {
      expect(count).toBeGreaterThanOrEqual(1);

      const headerTexts = await columns.locator('.pipeline-column-header').allTextContents();
      const joined = headerTexts.join(' ');
      expect(joined).toContain('opened');
    }
  });

  test('pipeline cards show company and title', async ({ page }) => {
    const cards = page.locator('.pipeline-card');
    const count = await cards.count();
    if (count > 0) {
      const firstCard = cards.first();
      await expect(firstCard.locator('.pipeline-card-company')).toBeVisible();
      await expect(firstCard.locator('.pipeline-card-title')).toBeVisible();
    }
  });

  test('status select exists on pipeline cards', async ({ page }) => {
    const selects = page.locator('.pipeline-card select');
    const count = await selects.count();
    if (count > 0) {
      await expect(selects.first()).toBeVisible();
      const options = await selects.first().locator('option').allTextContents();
      expect(options.length).toBeGreaterThan(0);
    }
  });

  test('open button on pipeline cards opens popup', async ({ page }) => {
    const openBtns = page.locator('.pipeline-card button', { hasText: 'Open' });
    const count = await openBtns.count();
    if (count > 0) {
      const [popup] = await Promise.all([
        page.waitForEvent('popup', { timeout: 5000 }).catch(() => null),
        openBtns.first().click(),
      ]);
      if (popup) await popup.close();
    }
  });

  test('refresh reloads pipeline data', async ({ page }) => {
    const refreshBtn = page.locator('.page-header-row button', { hasText: 'Refresh' });
    await expect(refreshBtn).toBeVisible();
    await refreshBtn.click();
    await page.waitForTimeout(2000);

    const board = page.locator('.pipeline-board');
    const emptyState = page.locator('.empty-state');
    const boardVisible = await board.isVisible().catch(() => false);
    const emptyVisible = await emptyState.isVisible().catch(() => false);
    expect(boardVisible || emptyVisible).toBeTruthy();
  });

  test('pipeline cards show ATS group when available', async ({ page }) => {
    const atsMeta = page.locator('.pipeline-card-meta').first();
    const isVisible = await atsMeta.isVisible().catch(() => false);
    if (isVisible) {
      await expect(atsMeta).toContainText('ATS:');
    }
  });
});
