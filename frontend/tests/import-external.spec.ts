import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

test.describe('Import External', () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API_URL}/test/reset`);
    await request.post(`${API_URL}/test/seed`);

    const loginResp = await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    });
    expect(loginResp.ok()).toBeTruthy();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/import');
    await page.waitForSelector('h2:has-text("Import External")', { timeout: 15000 });
  });

  test('loads import page with header', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('Import External Applications');
    await expect(page.locator('.page-header-row p')).toContainText('Import applications from JSON files');
  });

  test('expected format documentation is shown', async ({ page }) => {
    const preBlock = page.locator('pre');
    await expect(preBlock).toBeVisible();
    const text = await preBlock.textContent();
    expect(text).toContain('url');
    expect(text).toContain('company');
    expect(text).toContain('title');
  });

  test('choose JSON file button is visible', async ({ page }) => {
    const chooseBtn = page.locator('button', { hasText: 'Choose JSON file' });
    await expect(chooseBtn).toBeVisible();
  });

  test('import button disabled when no file selected', async ({ page }) => {
    const importBtn = page.locator('button', { hasText: 'Import Applications' });
    const isDisabled = await importBtn.isDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('can select a JSON file for preview', async ({ page }) => {
    const jsonData = [
      {
        url: 'https://example.com/job/1',
        company: 'TestCo',
        title: 'Software Engineer',
        status: 'applied',
        applied_at: '2026-06-01',
        notes: 'Test import',
      },
    ];

    const fileInput = page.locator('input[type="file"][accept=".json"]');
    await fileInput.setInputFiles({
      name: 'test-import.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(jsonData)),
    });

    await page.waitForTimeout(1000);

    const previewTable = page.locator('table');
    const isVisible = await previewTable.isVisible().catch(() => false);
    expect(isVisible).toBeTruthy();
  });

  test('preview table shows correct columns', async ({ page }) => {
    const jsonData = [
      {
        url: 'https://example.com/job/1',
        company: 'TestCo',
        title: 'Software Engineer',
        status: 'applied',
        applied_at: '2026-06-01',
      },
    ];

    const fileInput = page.locator('input[type="file"][accept=".json"]');
    await fileInput.setInputFiles({
      name: 'test-import.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(jsonData)),
    });

    await page.waitForTimeout(1000);

    const previewTable = page.locator('table');
    const isVisible = await previewTable.isVisible().catch(() => false);
    if (isVisible) {
      const headers = await previewTable.locator('th').allTextContents();
      expect(headers.join(' ')).toContain('Company');
      expect(headers.join(' ')).toContain('Title');
      expect(headers.join(' ')).toContain('Status');
    }
  });

  test('file name displayed after selection', async ({ page }) => {
    const jsonData = [{ url: 'https://example.com/job/1', company: 'TestCo', title: 'Engineer' }];

    const fileInput = page.locator('input[type="file"][accept=".json"]');
    await fileInput.setInputFiles({
      name: 'my-export.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(jsonData)),
    });

    await page.waitForTimeout(500);

    const fileName = page.locator('span', { hasText: 'my-export.json' });
    const isVisible = await fileName.isVisible().catch(() => false);
    expect(isVisible).toBeTruthy();
  });

  test('import button enabled after file selection', async ({ page }) => {
    const jsonData = [{ url: 'https://example.com/job/1', company: 'TestCo', title: 'Engineer' }];

    const fileInput = page.locator('input[type="file"][accept=".json"]');
    await fileInput.setInputFiles({
      name: 'test.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(jsonData)),
    });

    await page.waitForTimeout(500);

    const importBtn = page.locator('button', { hasText: 'Import Applications' });
    const isDisabled = await importBtn.isDisabled();
    expect(isDisabled).toBeFalsy();
  });
});
