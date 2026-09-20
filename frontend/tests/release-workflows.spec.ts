import { test, expect } from '@playwright/test';

test('top5_complete_filters_sort_safe_url_popup_blocking_and_click_recording', async ({ page, context }) => {
  const suffix = Date.now();
  const company = `JG023 Browser ${suffix}`;
  const remoteRows = Array.from({ length: 8 }, (_, index) => (
    `https://example.test/jg023-${suffix}/remote-${index},Release Job ${String(index).padStart(2, '0')},${company},remote`
  ));
  const controlRows = [
    `https://example.test/jg023-${suffix}/onsite,Release Job 00,${company},onsite`,
    `https://example.test/jg023-${suffix}/other,Release Job 99,Other Company,remote`,
  ];
  const csv = [
    'url,title,company_guess,location_group',
    ...remoteRows,
    ...controlRows,
  ].join('\n');

  const upload = await context.request.post('http://localhost:8000/upload', {
    multipart: {
      file: {
        name: 'jg023-release.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(csv),
      },
    },
  });
  expect(upload.ok()).toBeTruthy();

  await context.route('https://example.test/**', route => route.fulfill({
    contentType: 'text/html',
    body: '<h1>JG-023 synthetic job</h1>',
  }));

  const query = new URLSearchParams({
    q: company,
    location_group: 'remote',
    sort_by: 'title',
    sort_dir: 'asc',
  });
  await page.goto(`/?${query.toString()}`);

  const expectedResponse = await context.request.get('http://localhost:8000/rows', {
    params: {
      q: company,
      location_group: 'remote',
      sort_by: 'title',
      sort_dir: 'asc',
      unopened_only: true,
      openable_only: true,
      page: 1,
      page_size: 5,
    },
  });
  expect(expectedResponse.ok()).toBeTruthy();
  const expectedRows = (await expectedResponse.json()).rows;
  expect(expectedRows).toHaveLength(5);
  const expectedUrls = expectedRows.map((row: any) => row.data.url);
  expect(expectedUrls.every((url: string) => new URL(url).protocol === 'https:')).toBeTruthy();
  expect(expectedUrls.every((url: string) => url.includes('/remote-'))).toBeTruthy();

  const openButton = page.getByRole('button', { name: 'Open top 5 unopened', exact: true });
  await expect(openButton).toBeEnabled();

  const batchResponse = page.waitForResponse(response => {
    const url = new URL(response.url());
    return (
      url.pathname === '/rows'
      && url.searchParams.get('openable_only') === 'true'
      && url.searchParams.get('page_size') === '5'
    );
  });
  await openButton.click();

  const batchPayload = await (await batchResponse).json();
  expect(batchPayload.rows.map((row: any) => row.data.url)).toEqual(expectedUrls);

  await expect.poll(() => (
    context.pages()
      .filter(candidate => candidate !== page && candidate.url().includes(`jg023-${suffix}`))
      .map(candidate => candidate.url())
      .sort()
  )).toEqual([...expectedUrls].sort());

  await expect(page.getByText('Opened 5 links.', { exact: true })).toBeVisible();
  for (const popup of context.pages().filter(candidate => candidate !== page)) {
    expect(await popup.evaluate(() => window.opener)).toBeNull();
    await popup.close();
  }

  const openedAfterSuccess = await context.request.get('http://localhost:8000/rows', {
    params: {
      q: company,
      location_group: 'remote',
      opened_only: true,
      sort_by: 'title',
      sort_dir: 'asc',
      page: 1,
      page_size: 20,
    },
  });
  expect(openedAfterSuccess.ok()).toBeTruthy();
  const openedRows = (await openedAfterSuccess.json()).rows;
  expect(openedRows).toHaveLength(5);
  expect(openedRows.map((row: any) => row.data.url).sort()).toEqual([...expectedUrls].sort());

  let blockedVisitWrites = 0;
  page.on('request', request => {
    if (/\/rows\/\d+\/click$/.test(request.url()) && request.method() === 'POST') {
      blockedVisitWrites += 1;
    }
  });
  await page.evaluate(() => {
    window.open = () => null;
  });

  await openButton.click();
  await expect(
    page.getByText('Allow pop-ups for JobGrid in Chrome, then retry.', { exact: true }),
  ).toBeVisible();
  expect(blockedVisitWrites).toBe(0);

  const openedAfterBlocked = await context.request.get('http://localhost:8000/rows', {
    params: {
      q: company,
      location_group: 'remote',
      opened_only: true,
      page: 1,
      page_size: 20,
    },
  });
  expect(openedAfterBlocked.ok()).toBeTruthy();
  expect((await openedAfterBlocked.json()).rows).toHaveLength(5);
});
