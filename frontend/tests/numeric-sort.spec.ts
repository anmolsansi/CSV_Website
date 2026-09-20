import { expect, test, type Page } from '@playwright/test';

const API_URL = 'http://localhost:8000';
const ASCENDING_SCORES = ['-3', '2', '10', '85%', '$99.50', '1,000', 'invalid', ''];
const DESCENDING_SCORES = ['1,000', '$99.50', '85%', '10', '2', '-3', 'invalid', ''];

function csvCell(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

async function renderedScores(page: Page) {
  const headers = await page.locator('thead th').allTextContents();
  const scoreColumnIndex = headers.findIndex((header) =>
    header.trim().startsWith('resume_match_score')
  );
  expect(scoreColumnIndex).toBeGreaterThan(0);

  const rows = page.locator('tbody tr');
  const scores: string[] = [];
  for (let index = 0; index < await rows.count(); index += 1) {
    scores.push((await rows.nth(index).locator('td').nth(scoreColumnIndex).textContent() ?? '').trim());
  }
  return scores;
}

test('Resume Score sorting uses exact numeric order and URL-backed order survives reload', async ({ page, context }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  const suffix = Date.now().toString();
  const marker = `JG020 Numeric Browser ${suffix}`;
  const values = ['2', '10', '85%', '1,000', '$99.50', '-3', '', 'invalid'];
  const csv = [
    'url,title,company_guess,resume_match_score',
    ...values.map((score, index) => [
      csvCell(`https://example.test/jg020-browser-${suffix}/${index}`),
      csvCell(`${marker} role ${index}`),
      csvCell(marker),
      csvCell(score),
    ].join(',')),
  ].join('\n');

  const preferences = await context.request.put(`${API_URL}/preferences`, {
    data: { hidden_columns: [], column_order: [] },
  });
  expect(preferences.ok(), await preferences.text()).toBeTruthy();

  const upload = await context.request.post(`${API_URL}/upload`, {
    multipart: {
      file: {
        name: 'jg020-numeric-sort.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(csv),
      },
    },
  });
  expect(upload.ok(), await upload.text()).toBeTruthy();
  const uploadPayload = await upload.json();
  expect(uploadPayload.inserted).toBe(values.length);

  const params = new URLSearchParams({
    q: marker,
    sort_by: 'resume_match_score',
    sort_dir: 'asc',
    page: '1',
    page_size: '50',
  });
  await page.goto(`/?${params.toString()}`);

  await expect(page.locator('tbody tr')).toHaveCount(values.length);
  await expect.poll(() => renderedScores(page)).toEqual(ASCENDING_SCORES);

  await page.reload();
  await expect(page.locator('tbody tr')).toHaveCount(values.length);
  await expect.poll(() => renderedScores(page)).toEqual(ASCENDING_SCORES);

  const descendingResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      url.pathname === '/rows'
      && url.searchParams.get('sort_by') === 'resume_match_score'
      && url.searchParams.get('sort_dir') === 'desc'
      && url.searchParams.get('q') === marker
    );
  });

  await page.getByTitle('Sort by resume_match_score').click();
  const response = await descendingResponse;
  expect(response.status(), await response.text()).toBe(200);
  await expect.poll(() => renderedScores(page)).toEqual(DESCENDING_SCORES);

  expect(pageErrors).toEqual([]);
});
