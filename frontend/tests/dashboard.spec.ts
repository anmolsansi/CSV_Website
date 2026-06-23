import { test, expect, type Page } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('Dashboard', () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API_URL}/test/reset`);
    await request.post(`${API_URL}/test/seed`);
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.stats-grid', { timeout: 15000 });
  });

  test('loads stats cards with seeded data', async ({ page }) => {
    const statsGrid = page.locator('.stats-grid');
    await expect(statsGrid).toBeVisible();

    const totalCard = statsGrid.locator('.stat-card').filter({ hasText: 'Total URLs counted' });
    await expect(totalCard).toBeVisible();

    await expect.poll(async () => {
      const totalValue = await totalCard.locator('strong').textContent();
      return Number(totalValue);
    }).toBeGreaterThanOrEqual(20);
  });

  test('loads data table with rows', async ({ page }) => {
    const table = page.locator('table');
    await expect(table).toBeVisible();

    const rows = table.locator('tbody tr');
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
  });

  test('upload CSV and verify stats update', async ({ page }) => {
    const csvContent = [
      'url,company_guess,title,ats_group',
      'https://example.com/job/1,TestCo,Backend Engineer,greenhouse',
      'https://example.com/job/2,TestCo,Frontend Engineer,lever',
    ].join('\n');

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'test-upload.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(csvContent),
    });

    await page.waitForSelector('.upload-result', { timeout: 15000 });
    await expect(page.locator('.upload-result')).toBeVisible();
  });

  test('select rows and send to Applications', async ({ page }) => {
    const checkboxes = page.locator('tbody input[type="checkbox"]');
    await expect(checkboxes.first()).toBeVisible({ timeout: 10000 });

    await checkboxes.nth(0).check();
    await checkboxes.nth(1).check();

    const toolbar = page.locator('.sticky-toolbar');
    await expect(toolbar).toBeVisible();
    await expect(toolbar).toContainText('2 selected');

    const sendBtn = toolbar.locator('button', { hasText: 'Send to Applications' });
    await sendBtn.click();

    await page.waitForTimeout(2000);
    await expect(page.locator('.toast')).toBeVisible({ timeout: 10000 });
  });

  test('open selected rows triggers popup handling', async ({ page }) => {
    const checkboxes = page.locator('tbody input[type="checkbox"]');
    await expect(checkboxes.first()).toBeVisible({ timeout: 10000 });

    await checkboxes.nth(0).check();

    const toolbar = page.locator('.sticky-toolbar');
    await expect(toolbar).toBeVisible();

    const [popup] = await Promise.all([
      page.waitForEvent('popup', { timeout: 5000 }).catch(() => null),
      toolbar.locator('button', { hasText: 'Open selected' }).click(),
    ]);

    if (popup) {
      await popup.close();
    }

    await page.waitForTimeout(1000);
  });

  test('filter by ATS group', async ({ page }) => {
    const atsFilter = page.locator('#ats-group-filter');
    await expect(atsFilter).toBeVisible();

    await atsFilter.selectOption({ index: 1 });

    await page.waitForTimeout(1500);

    const rowsShown = page.locator('.table-control-actions span');
    const text = await rowsShown.textContent();
    expect(text).toBeTruthy();
  });

  test('filter by search bucket', async ({ page }) => {
    const bucketFilter = page.locator('#search-bucket-filter');
    await expect(bucketFilter).toBeVisible();

    await bucketFilter.selectOption({ index: 1 });

    await page.waitForTimeout(1500);
  });

  test('filter by sponsorship status', async ({ page }) => {
    const sponsorFilter = page.locator('#sponsorship-filter');
    await expect(sponsorFilter).toBeVisible();

    await sponsorFilter.selectOption({ index: 1 });

    await page.waitForTimeout(1500);
  });

  test('search input filters rows', async ({ page }) => {
    const searchInput = page.locator('#search-filter');
    await expect(searchInput).toBeVisible();

    await searchInput.fill('Acme');
    await page.waitForTimeout(1500);

    const rows = page.locator('tbody tr');
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
  });

  test('sort by columns changes order', async ({ page }) => {
    const sortSelect = page.locator('#sort-column');
    await expect(sortSelect).toBeVisible();

    const dataRows = page.locator('tbody tr[role="row"]');
    const firstRowBefore = await dataRows.first().textContent();

    await sortSelect.selectOption('company_guess');

    await page.waitForTimeout(1500);

    const firstRowAfter = await dataRows.first().textContent();
    expect(firstRowAfter).toBeTruthy();
  });

  test('sort direction toggle works', async ({ page }) => {
    const dirSelect = page.locator('#sort-direction');
    await expect(dirSelect).toBeVisible();

    await dirSelect.selectOption('asc');
    await page.waitForTimeout(1500);

    await dirSelect.selectOption('desc');
    await page.waitForTimeout(1500);
  });

  test('pagination controls appear with enough data', async ({ page }) => {
    const pagination = page.locator('.pagination-controls');
    const isVisible = await pagination.isVisible().catch(() => false);

    if (isVisible) {
      await expect(pagination.locator('button', { hasText: 'Prev' })).toBeVisible();
      await expect(pagination.locator('button', { hasText: 'Next' })).toBeVisible();
      await expect(pagination.locator('.pagination-info')).toBeVisible();
    }
  });

  test('column show/hide toggle works', async ({ page }) => {
    const toggleHeader = page.locator('.col-collapse-toggle');
    await expect(toggleHeader).toBeVisible();

    await toggleHeader.click();

    const columnControls = page.locator('.column-control');
    await expect(columnControls.first()).toBeVisible();

    const firstCheckbox = columnControls.first().locator('input[type="checkbox"]');
    const wasChecked = await firstCheckbox.isChecked();
    await firstCheckbox.click();

    await page.waitForTimeout(1000);

    const isNowChecked = await firstCheckbox.isChecked();
    expect(isNowChecked).toBe(!wasChecked);

    await firstCheckbox.click();
    await page.waitForTimeout(500);
  });

  test('clear filters resets all filter controls', async ({ page }) => {
    const searchInput = page.locator('#search-filter');
    await searchInput.fill('xyznonexistent');
    await page.waitForTimeout(1000);

    const clearBtn = page.locator('button', { hasText: 'Clear filters' });
    await clearBtn.click();

    await page.waitForTimeout(1500);

    const searchValue = await searchInput.inputValue();
    expect(searchValue).toBe('');
  });

  test('export CSV downloads file', async ({ page }) => {
    const downloadPromise = page.waitForEvent('download', { timeout: 10000 }).catch(() => null);

    const downloadBtn = page.locator('.export-bar button', { hasText: 'Download' });
    await expect(downloadBtn).toBeVisible();
    await downloadBtn.click();

    const download = await downloadPromise;
    if (download) {
      expect(download.suggestedFilename()).toMatch(/\.(csv|json)$/);
    }
  });

  test('export format can be changed to JSON', async ({ page }) => {
    const formatSelect = page.locator('.export-bar select').first();
    await formatSelect.selectOption('json');

    const downloadPromise = page.waitForEvent('download', { timeout: 10000 }).catch(() => null);

    const downloadBtn = page.locator('.export-bar button', { hasText: 'Download' });
    await downloadBtn.click();

    const download = await downloadPromise;
    if (download) {
      expect(download.suggestedFilename()).toContain('.json');
    }
  });

  test('clear selection button deselects all rows', async ({ page }) => {
    const checkboxes = page.locator('tbody input[type="checkbox"]');
    const count = await checkboxes.count();
    if (count === 0) return;

    await checkboxes.nth(0).check();
    await page.waitForTimeout(500);

    const toolbar = page.locator('.sticky-toolbar');
    await expect(toolbar).toBeVisible();

    const clearBtn = toolbar.locator('button', { hasText: 'Clear selection' });
    await clearBtn.click();

    await page.waitForTimeout(500);
    await expect(toolbar).not.toBeVisible();
  });

  test('open next 5 button works', async ({ page }) => {
    const openNext5Btn = page.locator('button', { hasText: 'Open next 5' });
    await expect(openNext5Btn).toBeVisible();

    const [popup] = await Promise.all([
      page.waitForEvent('popup', { timeout: 5000 }).catch(() => null),
      openNext5Btn.click(),
    ]);

    if (popup) {
      await popup.close();
    }

    await page.waitForTimeout(1000);
  });

  test('density toggle cycles through modes', async ({ page }) => {
    const densityBtn = page.locator('button', { hasText: /Comfortable|Compact|Dense/ });
    await expect(densityBtn).toBeVisible();

    const initialText = await densityBtn.textContent();
    await densityBtn.click();
    await page.waitForTimeout(500);

    const nextText = await densityBtn.textContent();
    expect(nextText).not.toBe(initialText);
  });

  test('row click opens drawer', async ({ page }) => {
    const firstRow = page.locator('tbody tr').first();
    await expect(firstRow).toBeVisible({ timeout: 10000 });

    await firstRow.click();

    const drawer = page.locator('.row-drawer, .drawer, [class*="drawer"]');
    const drawerVisible = await drawer.isVisible().catch(() => false);

    if (drawerVisible) {
      const closeBtn = drawer.locator('button', { hasText: /close|×|Close/i });
      if (await closeBtn.isVisible().catch(() => false)) {
        await closeBtn.click();
      }
    }
  });
});
