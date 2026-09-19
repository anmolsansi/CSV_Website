import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('JG-011 metric consistency', () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API_URL}/test/reset`);

    const loginResp = await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    });
    expect(loginResp.ok()).toBeTruthy();

    const seedResp = await request.post(`${API_URL}/test/seed`);
    expect(seedResp.ok()).toBeTruthy();

    const timezoneResp = await request.patch(`${API_URL}/crm/profile/timezone`, {
      data: { timezone: 'Asia/Kolkata' },
    });
    expect(timezoneResp.ok()).toBeTruthy();

    const rowsResp = await request.get(`${API_URL}/rows`, {
      params: { sort_by: 'created_at', sort_dir: 'desc', page: 1, page_size: 5 },
    });
    expect(rowsResp.ok()).toBeTruthy();
    const rowsData = await rowsResp.json();
    const rows = rowsData.rows || [];
    expect(rows.length).toBeGreaterThanOrEqual(2);

    const visitResp = await request.post(`${API_URL}/rows/${rows[0].id}/click`);
    expect(visitResp.ok()).toBeTruthy();

    const savedResp = await request.post(`${API_URL}/crm/from-row/${rows[1].id}`);
    expect(savedResp.ok()).toBeTruthy();
    const saved = await savedResp.json();

    const applyResp = await request.patch(`${API_URL}/crm/applications/${saved.id}`, {
      data: { mark_applied: true },
    });
    expect(applyResp.ok()).toBeTruthy();

    // Retry both mutations. First-event totals must remain stable.
    expect((await request.post(`${API_URL}/rows/${rows[0].id}/click`)).ok()).toBeTruthy();
    expect((await request.patch(`${API_URL}/crm/applications/${saved.id}`, {
      data: { mark_applied: true },
    })).ok()).toBeTruthy();

    const analytics = await (await request.get(`${API_URL}/crm/analytics`)).json();
    const goals = await (await request.get(`${API_URL}/crm/analytics/goals`)).json();
    const weekly = await (await request.get(`${API_URL}/crm/analytics/weekly`)).json();

    expect(analytics.total_opened).toBe(1);
    expect(analytics.total_saved).toBe(1);
    expect(analytics.total_applied).toBe(1);
    expect(analytics.applied_today).toBe(1);
    expect(goals.today.opened).toBe(1);
    expect(goals.today.applied).toBe(1);
    expect(weekly.opened).toBe(1);
    expect(weekly.saved).toBe(1);
    expect(weekly.applied).toBe(1);
  });

  test('shows the same visited saved and applied definitions in Analytics', async ({ page }) => {
    await page.goto('/analytics');
    await page.waitForSelector('h2:has-text("Analytics")', { timeout: 15000 });

    const lifetime = page.locator('.stats-grid.app-stats-grid');
    await expect(lifetime.locator('.stat-card').filter({ hasText: 'Visited jobs' }).locator('strong')).toHaveText('1');
    await expect(lifetime.locator('.stat-card').filter({ hasText: 'Saved jobs' }).locator('strong')).toHaveText('1');
    await expect(lifetime.locator('.stat-card').filter({ hasText: 'Applied jobs' }).locator('strong')).toHaveText('1');

    const goals = page.locator('.chart-section', { hasText: "Today's Progress" });
    await expect(goals).toContainText('Visited jobs');
    await expect(goals).toContainText('Applied jobs');

    const weekly = page.locator('.chart-section', { hasText: "This Week's Summary" });
    await expect(weekly.locator('.stat-card').filter({ hasText: 'Visited' }).locator('strong')).toHaveText('1');
    await expect(weekly.locator('.stat-card').filter({ hasText: 'Saved' }).locator('strong')).toHaveText('1');
    await expect(weekly.locator('.stat-card').filter({ hasText: 'Applied' }).locator('strong')).toHaveText('1');

    await expect(page.getByLabel('Metrics timezone')).toHaveValue('Asia/Kolkata');
    await expect(page.getByText(/Historical records with unknown occurrence dates are excluded/)).toBeVisible();
  });
});
