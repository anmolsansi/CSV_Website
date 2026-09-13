import { test, expect } from '@playwright/test';

test('filtered batches and remembered applications survive reload', async ({ page, context }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const suffix = Date.now();
  const company = `Memory Browser ${suffix}`;
  const csv = 'url,title,company_guess,location_group\n' + Array.from({ length: 8 }, (_, i) =>
    `https://example.test/memory-${suffix}/${i},Memory Job ${i},${company},remote`).join('\n');
  const upload = await context.request.post('http://localhost:8000/upload', {
    multipart: { file: { name: 'memory.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) } },
  });
  expect(upload.ok()).toBeTruthy();
  await context.route('https://example.test/**', route => route.fulfill({ contentType: 'text/html', body: '<h1>Test job</h1>' }));
  await page.goto('/');
  const search = page.getByPlaceholder('Company, title, URL');
  await search.fill(company);
  await expect(page.getByRole('button', { name: 'Open top 5 unopened', exact: true })).toBeEnabled();
  const candidates = await context.request.get('http://localhost:8000/rows', {
    params: { q: company, sort_by: 'created_at', sort_dir: 'desc', unopened_only: true, page_size: 5 },
  });
  const expected = (await candidates.json()).rows.map((r: any) => r.data.url);
  const batchResponse = page.waitForResponse(r => r.url().includes('/rows?') && r.url().includes('page_size=5'));
  await page.getByRole('button', { name: 'Open top 5 unopened', exact: true }).click();
  expect((await (await batchResponse).json()).rows.map((r: any) => r.data.url)).toEqual(expected);
  await expect.poll(() => context.pages().filter(p => p !== page && p.url().includes(`memory-${suffix}`)).map(p => p.url()).sort()).toEqual([...expected].sort());
  await expect(page.getByText('Opened 5 links.', { exact: true })).toBeVisible();
  for (const popup of context.pages().filter(p => p !== page)) {
    expect(await popup.evaluate(() => window.opener)).toBeNull();
    await popup.close();
  }
  await page.getByRole('button', { name: 'Open top 5 unopened', exact: true }).click();
  await expect(page.getByText('Opened 3 links.', { exact: true })).toBeVisible();
  await expect.poll(() => context.pages().filter(p => p !== page && p.url().includes(`memory-${suffix}`)).length).toBe(3);
  for (const popup of context.pages().filter(p => p !== page)) await popup.close();
  const firstRow = page.locator('tbody tr').first();
  await firstRow.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Mark applied', exact: true }).click();
  await expect(page.getByText('Marked 1 as applied', { exact: true })).toBeVisible();
  await page.reload();
  await page.goto('/companies');
  await page.getByRole('button', { name: `${company} · 1 jobs · 1 applied`, exact: true }).click();
  await expect(page.getByText(/^Applied:/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: `${company} · 1 jobs · 1 applied`, exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test('blocked batch tabs do not mark jobs visited', async ({ page }) => {
  let visits = 0;
  page.on('request', r => { if (/\/rows\/\d+\/click$/.test(r.url())) visits++; });
  await page.goto('/');
  const button = page.getByRole('button', { name: 'Open top 5 unopened', exact: true });
  await expect(button).toBeEnabled();
  await page.evaluate(() => { window.open = () => null; });
  await button.click();
  await expect(page.getByText('Allow pop-ups for JobGrid in Chrome, then retry.', { exact: true })).toBeVisible();
  expect(visits).toBe(0);
  await expect(button).toBeEnabled();
});

test('failed batch lookup closes blank tabs', async ({ page, context }) => {
  await page.goto('/');
  const button = page.getByRole('button', { name: 'Open top 5 unopened', exact: true });
  await expect(button).toBeEnabled();
  await page.route('**/rows?**', route => {
    if (new URL(route.request().url()).searchParams.get('openable_only') === 'true') {
      return route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Test failure"}' });
    }
    return route.continue();
  });
  await button.click();
  await expect(page.getByText('Could not load or refresh jobs. Please retry.', { exact: true })).toBeVisible();
  await expect.poll(() => context.pages().length).toBe(1);
  await expect(button).toBeEnabled();
});

test('company directory errors can be retried', async ({ page }) => {
  let fail = true;
  await page.route('**/crm/companies?**', route => {
    if (fail) return route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Test failure"}' });
    return route.continue();
  });
  await page.goto('/companies');
  await expect(page.getByRole('alert')).toContainText('Could not load remembered companies');
  fail = false;
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Remembered companies' })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
