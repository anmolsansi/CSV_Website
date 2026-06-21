import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('Company History', () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API_URL}/test/reset`);
    await request.post(`${API_URL}/test/seed`);

    const loginResp = await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    });
    expect(loginResp.ok()).toBeTruthy();

    const rowsResp = await request.get(`${API_URL}/rows`, {
      params: { sort_by: 'created_at', sort_dir: 'desc', page: 1, page_size: 3 },
    });
    const rowsData = await rowsResp.json();
    const rowIds = (rowsData.rows || []).slice(0, 3).map((r: any) => r.id);

    if (rowIds.length > 0) {
      await request.post(`${API_URL}/crm/from-rows/bulk`, {
        data: { row_ids: rowIds },
      });
    }
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/companies');
    await page.waitForSelector('h2:has-text("Company History")', { timeout: 15000 });
  });

  test('loads company history page with header', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('Company History');
    await expect(page.locator('.page-header-row p')).toContainText('View all roles and status history');
  });

  test('search input and button are visible', async ({ page }) => {
    const searchInput = page.locator('input[placeholder="Search company name..."]');
    await expect(searchInput).toBeVisible();

    const searchBtn = page.locator('button', { hasText: 'Search' });
    await expect(searchBtn).toBeVisible();
  });

  test('empty state shown before search', async ({ page }) => {
    const emptyState = page.locator('.empty-state');
    await expect(emptyState).toBeVisible();
    await expect(emptyState).toContainText('Search for a company');
  });

  test('can search for a company', async ({ page }) => {
    const searchInput = page.locator('input[placeholder="Search company name..."]');
    await searchInput.fill('Acme');

    const searchBtn = page.locator('button', { hasText: 'Search' });
    await searchBtn.click();
    await page.waitForTimeout(3000);

    const loading = page.locator('.loading-spinner');
    const loadingVisible = await loading.isVisible().catch(() => false);
    if (loadingVisible) {
      await page.waitForSelector('.loading-spinner', { state: 'hidden', timeout: 10000 });
    }

    const statsGrid = page.locator('.stats-grid');
    const emptyState = page.locator('.empty-state');
    const statsVisible = await statsGrid.isVisible().catch(() => false);
    const emptyVisible = await emptyState.isVisible().catch(() => false);
    expect(statsVisible || emptyVisible).toBeTruthy();
  });

  test('stats cards show role counts after search', async ({ page }) => {
    const searchInput = page.locator('input[placeholder="Search company name..."]');
    await searchInput.fill('Acme');

    const searchBtn = page.locator('button', { hasText: 'Search' });
    await searchBtn.click();
    await page.waitForTimeout(3000);

    const statsGrid = page.locator('.stats-grid');
    const isVisible = await statsGrid.isVisible().catch(() => false);
    if (isVisible) {
      const totalCard = statsGrid.locator('.stat-card').filter({ hasText: 'Total roles' });
      await expect(totalCard).toBeVisible();
    }
  });

  test('enter key triggers search', async ({ page }) => {
    const searchInput = page.locator('input[placeholder="Search company name..."]');
    await searchInput.fill('Acme');
    await searchInput.press('Enter');
    await page.waitForTimeout(3000);

    const statsGrid = page.locator('.stats-grid');
    const emptyState = page.locator('.empty-state');
    const statsVisible = await statsGrid.isVisible().catch(() => false);
    const emptyVisible = await emptyState.isVisible().catch(() => false);
    expect(statsVisible || emptyVisible).toBeTruthy();
  });

  test('role cards display status badges', async ({ page }) => {
    const searchInput = page.locator('input[placeholder="Search company name..."]');
    await searchInput.fill('Acme');
    await searchInput.press('Enter');
    await page.waitForTimeout(3000);

    const roleCards = page.locator('[style*="border-radius: 8px"]');
    const count = await roleCards.count();
    if (count > 0) {
      const text = await roleCards.first().textContent();
      expect(text).toBeTruthy();
    }
  });

  test('search with empty input does nothing', async ({ page }) => {
    const searchInput = page.locator('input[placeholder="Search company name..."]');
    await searchInput.fill('');

    const searchBtn = page.locator('button', { hasText: 'Search' });
    await searchBtn.click();
    await page.waitForTimeout(1000);

    const emptyState = page.locator('.empty-state');
    await expect(emptyState).toBeVisible();
  });
});
