import { test, expect } from '@playwright/test';

const API_URL = 'http://localhost:8000';

async function resetAndLogin(request) {
  await request.post(`${API_URL}/test/reset`);
  await request.post(`${API_URL}/test/seed`);
  const login = await request.post(`${API_URL}/auth/dev-login`, {
    data: { email: 'test@jobgrid.dev' },
  });
  expect(login.ok()).toBeTruthy();
}

test.describe('JG-007 browser/export query parity', () => {
  test.beforeAll(async ({ request }) => {
    await resetAndLogin(request);
  });

  test('dashboard saved-view URL survives reload and filtered export uses the same query', async ({ page }) => {
    const browseRequest = page.waitForRequest((request) => {
      if (!request.url().includes('/rows?')) return false;
      return new URL(request.url()).searchParams.get('q') === 'Parity';
    });

    await page.goto('/?q=Parity&unopened_only=true&opened_only=false&sort_by=title&sort_dir=asc');
    const browse = new URL((await browseRequest).url()).searchParams;

    expect(browse.get('q')).toBe('Parity');
    expect(browse.get('unopened_only')).toBe('true');
    expect(browse.get('opened_only')).toBe('false');
    expect(browse.get('sort_by')).toBe('title');
    expect(browse.get('sort_dir')).toBe('asc');

    await page.reload();
    await expect(page.locator('#search-filter')).toHaveValue('Parity');

    await page.locator('.export-bar select').nth(1).selectOption('filtered');
    const exportRequest = page.waitForRequest((request) => request.url().includes('/crm/export/dashboard?'));
    await page.locator('.export-bar button', { hasText: 'Download' }).click();
    const exported = new URL((await exportRequest).url()).searchParams;

    expect(exported.get('scope')).toBe('filtered');
    expect(exported.get('q')).toBe('Parity');
    expect(exported.get('unopened_only')).toBe('true');
    expect(exported.get('opened_only')).toBe('false');
    expect(exported.get('sort_by')).toBe('title');
    expect(exported.get('sort_dir')).toBe('asc');
    expect(exported.has('page')).toBeFalsy();
    expect(exported.has('page_size')).toBeFalsy();
  });

  test('applications saved-view URL and filtered export share the same query contract', async ({ page }) => {
    const browseRequest = page.waitForRequest((request) => {
      if (!request.url().includes('/crm/applications')) return false;
      return new URL(request.url()).searchParams.get('q') === 'ParityApp';
    });

    await page.goto('/applications?q=ParityApp&follow_up_due=false&opened_not_applied=true&sort_by=company&sort_dir=asc');
    const browse = new URL((await browseRequest).url()).searchParams;

    expect(browse.get('q')).toBe('ParityApp');
    expect(browse.get('follow_up_due')).toBe('false');
    expect(browse.get('opened_not_applied')).toBe('true');
    expect(browse.get('sort_by')).toBe('company');
    expect(browse.get('sort_dir')).toBe('asc');

    await expect(page.getByLabel('Search')).toHaveValue('ParityApp');
    await page.locator('.export-bar select').nth(1).selectOption('filtered');

    const exportRequest = page.waitForRequest((request) => request.url().includes('/crm/export/applications?'));
    await page.locator('.export-bar button', { hasText: 'Download' }).click();
    const exported = new URL((await exportRequest).url()).searchParams;

    expect(exported.get('scope')).toBe('filtered');
    expect(exported.get('q')).toBe('ParityApp');
    expect(exported.get('follow_up_due')).toBe('false');
    expect(exported.get('opened_not_applied')).toBe('true');
    expect(exported.get('sort_by')).toBe('company');
    expect(exported.get('sort_dir')).toBe('asc');
    expect(exported.has('page')).toBeFalsy();
    expect(exported.has('page_size')).toBeFalsy();
  });

  test('selected dashboard export sends exactly the selected row ids', async ({ page }) => {
    const responsePromise = page.waitForResponse((response) => response.url().includes('/rows?') && response.status() === 200);
    await page.goto('/');
    const payload = await (await responsePromise).json();
    expect(payload.rows.length).toBeGreaterThanOrEqual(2);
    const selectedIds = payload.rows.slice(0, 2).map((row) => row.id);

    for (const id of selectedIds) {
      await page.getByLabel(`Select row ${id}`).check();
    }

    await page.locator('.export-bar select').nth(1).selectOption('selected');
    const exportRequest = page.waitForRequest((request) => request.url().includes('/crm/export/dashboard?'));
    await page.locator('.export-bar button', { hasText: 'Download' }).click();
    const exported = new URL((await exportRequest).url()).searchParams;

    expect(exported.get('scope')).toBe('selected');
    expect(exported.get('row_ids')?.split(',').map(Number)).toEqual(selectedIds);
  });

  test('sort changes are serialized into filtered export ordering parameters', async ({ page }) => {
    await page.goto('/');
    await page.locator('#sort-column').selectOption('title');
    await page.locator('#sort-direction').selectOption('asc');
    await expect(page.locator('.export-bar button', { hasText: 'Download' })).toBeEnabled();

    await page.locator('.export-bar select').nth(1).selectOption('filtered');
    const exportRequest = page.waitForRequest((request) => request.url().includes('/crm/export/dashboard?'));
    await page.locator('.export-bar button', { hasText: 'Download' }).click();
    const exported = new URL((await exportRequest).url()).searchParams;

    expect(exported.get('sort_by')).toBe('title');
    expect(exported.get('sort_dir')).toBe('asc');
  });

  test('unsupported saved-view query keys show a recoverable error', async ({ page }) => {
    await page.goto('/?unsupported_saved_key=1');
    await expect(page.locator('[role="alert"]')).toContainText('Unsupported saved-view keys');
    await page.getByRole('button', { name: 'Clear saved-view filters' }).click();
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
    expect(new URL(page.url()).search).toBe('');
  });

  test('export error response is surfaced and never reported as a downloaded file', async ({ page }) => {
    await page.goto('/');
    await page.locator('.export-bar select').nth(1).selectOption('filtered');
    await page.route('**/crm/export/dashboard?**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'synthetic failure' }),
      });
    });

    await page.locator('.export-bar button', { hasText: 'Download' }).click();
    await expect(page.getByText('Export failed. No file was downloaded. Please retry.')).toBeVisible();
    await expect(page.getByText('Export downloaded')).toHaveCount(0);
  });
});
