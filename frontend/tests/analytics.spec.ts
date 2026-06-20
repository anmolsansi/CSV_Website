import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('Analytics', () => {
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
    await page.goto('/analytics');
    await page.waitForSelector('h2:has-text("Analytics")', { timeout: 15000 });
  });

  test('loads analytics page with header', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('Analytics');
    await expect(page.locator('.page-header-row p')).toContainText('Job search metrics');
  });

  test('stats grid displays metric cards', async ({ page }) => {
    const statsGrid = page.locator('.stats-grid.app-stats-grid');
    await expect(statsGrid).toBeVisible();

    const cards = statsGrid.locator('.stat-card');
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(5);
  });

  test('shows total URLs uploaded stat', async ({ page }) => {
    const card = page.locator('.stat-card').filter({ hasText: 'Total URLs uploaded' });
    await expect(card).toBeVisible();
    const value = await card.locator('strong').textContent();
    expect(Number(value)).toBeGreaterThanOrEqual(0);
  });

  test('shows total opened stat', async ({ page }) => {
    const card = page.locator('.stat-card').filter({ hasText: 'Total opened' });
    await expect(card).toBeVisible();
  });

  test('application funnel section is visible', async ({ page }) => {
    const funnelSection = page.locator('.chart-section', { hasText: 'Application Funnel' });
    await expect(funnelSection).toBeVisible();
  });

  test('ATS performance table is shown', async ({ page }) => {
    const section = page.locator('.chart-section', { hasText: 'ATS Performance' });
    await expect(section).toBeVisible();
  });

  test('search bucket performance table is shown', async ({ page }) => {
    const section = page.locator('.chart-section', { hasText: 'Search Bucket Performance' });
    await expect(section).toBeVisible();
  });

  test('goals button toggles goals panel', async ({ page }) => {
    const goalsBtn = page.locator('.page-header-row button', { hasText: 'Goals' });
    await expect(goalsBtn).toBeVisible();
    await goalsBtn.click();
    await page.waitForTimeout(500);

    const saveGoalsBtn = page.locator('button', { hasText: 'Save goals' });
    const isVisible = await saveGoalsBtn.isVisible().catch(() => false);
    expect(isVisible).toBeTruthy();

    await goalsBtn.click();
    await page.waitForTimeout(500);
  });

  test('refresh button reloads analytics data', async ({ page }) => {
    const refreshBtn = page.locator('.page-header-row button', { hasText: 'Refresh' });
    await expect(refreshBtn).Visible();
    await refreshBtn.click();
    await page.waitForTimeout(2000);
    await expect(page.locator('.stats-grid.app-stats-grid')).toBeVisible();
  });

  test('weekly summary section loads', async ({ page }) => {
    const section = page.locator('.chart-section', { hasText: "This Week's Summary" });
    const isVisible = await section.isVisible().catch(() => false);
    if (isVisible) {
      const statCards = section.locator('.stat-card');
      const count = await statCards.count();
      expect(count).toBeGreaterThan(0);
    }
  });
});
