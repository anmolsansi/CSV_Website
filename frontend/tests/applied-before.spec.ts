import { test, expect, type APIRequestContext } from '@playwright/test';

const API_URL = 'http://localhost:8000';

async function resetAndLogin(request: APIRequestContext) {
  await request.post(`${API_URL}/test/reset`);
  await request.post(`${API_URL}/test/seed`);
  const login = await request.post(`${API_URL}/auth/dev-login`, {
    data: { email: 'test@jobgrid.dev' },
  });
  expect(login.ok()).toBeTruthy();
}

async function uploadCsv(request: APIRequestContext, csv: string) {
  const response = await request.post(`${API_URL}/upload`, {
    multipart: {
      file: {
        name: 'jg031.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(csv),
      },
    },
  });
  expect(response.ok()).toBeTruthy();
}

test.describe('JG-031 applied-before context', () => {
  test('canonical warning does not block reapply', async ({ page, request }) => {
    await resetAndLogin(request);

    const rowsResponse = await request.get(`${API_URL}/rows`, {
      params: { sort_by: 'created_at', sort_dir: 'asc', page: 1, page_size: 1 },
    });
    const seedRow = (await rowsResponse.json()).rows[0];
    expect(seedRow).toBeTruthy();

    const prior = await request.post(`${API_URL}/crm/from-row/${seedRow.id}`);
    expect(prior.ok()).toBeTruthy();
    const priorTrack = await prior.json();
    const applied = await request.patch(`${API_URL}/crm/applications/${priorTrack.id}`, {
      data: { mark_applied: true },
    });
    expect(applied.ok()).toBeTruthy();

    const variantUrl = `${seedRow.data.url}?utm_source=jg031`;
    await uploadCsv(
      request,
      [
        'url,company_guess,title,ats_group',
        `${variantUrl},Acme Corp,Senior Engineer,greenhouse`,
      ].join('\n')
    );

    await page.goto('/');
    await page.waitForSelector('table', { timeout: 15000 });
    const search = page.locator('#search-filter');
    await search.fill('utm_source=jg031');
    await page.waitForTimeout(1200);

    const candidate = page.locator('tbody tr').filter({ hasText: 'utm_source=jg031' }).first();
    await expect(candidate).toBeVisible();
    await candidate.click();

    const warning = page.getByTestId('applied-before-warning');
    await expect(warning).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('prior-match-canonical')).toBeVisible();
    await expect(warning).toContainText('This warning does not block a legitimate reapplication');

    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toContain('prior applied history');
      await dialog.accept();
    });
    await page.locator('.drawer-panel button', { hasText: 'Mark applied' }).click();
    await expect(page.locator('.drawer-panel')).toContainText(
      'Marked applied. Your prior application history was kept unchanged.',
      { timeout: 10000 }
    );

    const apps = await request.get(`${API_URL}/crm/applications`, {
      params: { q: 'utm_source=jg031', page: 1, page_size: 20 },
    });
    expect(apps.ok()).toBeTruthy();
    const payload = await apps.json();
    const reapplied = payload.rows.find((item: any) => item.url === variantUrl);
    expect(reapplied).toBeTruthy();
    expect(reapplied.applied_at).toBeTruthy();
  });

  test('slash company navigation works and focuses the linked prior role', async ({ page, request }) => {
    await resetAndLogin(request);
    await uploadCsv(
      request,
      [
        'url,company_guess,title,ats_group',
        'https://jobs.example.test/slash-ui,Research/AI Labs,Platform Engineer,greenhouse',
      ].join('\n')
    );

    const rows = await request.get(`${API_URL}/rows`, {
      params: { q: 'slash-ui', page: 1, page_size: 10 },
    });
    const row = (await rows.json()).rows.find((item: any) => item.data.url.includes('slash-ui'));
    expect(row).toBeTruthy();

    const created = await request.post(`${API_URL}/crm/from-row/${row.id}`);
    expect(created.ok()).toBeTruthy();
    const track = await created.json();

    const company = encodeURIComponent('Research/AI Labs');
    await page.goto(`/companies?company=${company}&track_id=${track.id}#application-${track.id}`);
    await page.waitForSelector('h2:has-text("Company History")', { timeout: 15000 });

    await expect(page.locator(`#application-${track.id}`)).toBeVisible({ timeout: 10000 });
    await expect(page.locator(`#application-${track.id}`)).toContainText('Platform Engineer');
  });

  test('explicit company alias groups history and can be removed safely', async ({ page, request }) => {
    await resetAndLogin(request);
    await uploadCsv(
      request,
      [
        'url,company_guess,title,ats_group',
        'https://jobs.example.test/alias-a,Acme Corp,Backend Engineer,greenhouse',
        'https://jobs.example.test/alias-b,Acme Incorporated,Platform Engineer,greenhouse',
      ].join('\n')
    );

    const rows = await request.get(`${API_URL}/rows`, {
      params: { q: 'alias-', page: 1, page_size: 20 },
    });
    const payload = await rows.json();
    const rowIds = payload.rows
      .filter((item: any) => item.data.url.includes('alias-'))
      .map((item: any) => item.id);
    expect(rowIds).toHaveLength(2);

    const created = await request.post(`${API_URL}/crm/from-rows/bulk`, {
      data: { row_ids: rowIds },
    });
    expect(created.ok()).toBeTruthy();

    await page.goto('/companies?company=Acme%20Corp');
    await page.waitForSelector('h2:has-text("Company History")', { timeout: 15000 });
    await expect(page.locator('#company-alias-input')).toBeVisible();

    await page.locator('#company-alias-input').fill('Acme Incorporated');
    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toContain('This affects company-history grouping');
      await dialog.accept();
    });
    await page.getByRole('button', { name: 'Add alias' }).click();

    const aliasRow = page.getByTestId('company-alias-row').filter({ hasText: 'Acme Incorporated' });
    await expect(aliasRow).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.stats-grid').filter({ hasText: 'Total roles' })).toContainText('2');

    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toContain('Applications and their history will remain unchanged');
      await dialog.accept();
    });
    await aliasRow.getByRole('button', { name: 'Remove alias' }).click();
    await expect(page.getByText('Application history was not deleted.')).toBeVisible({ timeout: 10000 });

    const apps = await request.get(`${API_URL}/crm/applications`, {
      params: { page: 1, page_size: 20 },
    });
    expect(apps.ok()).toBeTruthy();
    expect((await apps.json()).total_count).toBe(2);
  });
});
