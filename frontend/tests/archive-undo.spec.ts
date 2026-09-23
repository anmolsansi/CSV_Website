import { expect, test, type Page } from '@playwright/test';

const API_URL = 'http://localhost:8000';

async function archiveSelected(page: Page, count = 1) {
  const checkboxes = page.locator('tbody input[type="checkbox"]');
  await expect(checkboxes.first()).toBeVisible({ timeout: 15000 });
  for (let index = 0; index < count; index += 1) {
    await checkboxes.nth(index).check();
  }

  const dialogs: string[] = [];
  page.on('dialog', async (dialog) => {
    dialogs.push(dialog.type());
    if (dialog.type() === 'prompt') await dialog.accept('1');
    else await dialog.accept();
  });
  await page.getByRole('button', { name: 'Remove selected' }).first().click();
  await expect.poll(() => dialogs.length).toBeGreaterThanOrEqual(2);
  await expect(page.getByRole('region', { name: 'Last bulk action' })).toBeVisible();
}

async function archivedRows(page: Page) {
  await page.goto('/archive');
  await expect(page.getByTestId('archive-page')).toBeVisible({ timeout: 15000 });
  return page.locator('tbody tr');
}

test.describe('Archive and conflict-aware Undo', () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post(`${API_URL}/test/reset`);
    await request.post(`${API_URL}/test/seed`);
    await page.goto('/');
    await page.waitForSelector('tbody tr', { timeout: 15000 });
  });

  test('archive_reload_restore', async ({ page }) => {
    await archiveSelected(page, 1);
    const rows = await archivedRows(page);
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText(/Acme Corp|Senior Engineer/);

    await rows.first().locator('input[type="checkbox"]').check();
    await page.getByRole('button', { name: 'Restore selected' }).click();
    await expect(page.getByText('No archived rows match these filters.')).toBeVisible();

    await page.reload();
    await expect(page.getByText('No archived rows match these filters.')).toBeVisible();
  });

  test('two_tab_conflict_no_silent_overwrite', async ({ page, context }) => {
    await archiveSelected(page, 1);
    const rows = await archivedRows(page);
    const row = rows.first();
    const testId = await row.getAttribute('data-testid');
    const rowId = Number(testId?.replace('archive-row-', ''));
    expect(rowId).toBeGreaterThan(0);

    const second = await context.newPage();
    await second.goto('/archive');
    await second.evaluate(async (id) => {
      await fetch(`http://localhost:8000/rows/${id}/click`, {
        method: 'POST',
        credentials: 'include',
      });
    }, rowId);
    await second.close();

    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(page.getByText(/Nothing was overwritten/)).toBeVisible();
    await expect(page.getByText(/Default Undo restored 0 records/)).toBeVisible();
    await expect(row).toBeVisible();
  });

  test('partial_undo_counts_visible', async ({ page, context }) => {
    await page.goto('/');
    await archiveSelected(page, 2);
    const rows = await archivedRows(page);
    await expect(rows).toHaveCount(2);
    const firstId = Number((await rows.first().getAttribute('data-testid'))?.replace('archive-row-', ''));

    const second = await context.newPage();
    await second.goto('/archive');
    await second.evaluate(async (id) => {
      await fetch(`http://localhost:8000/rows/${id}/click`, {
        method: 'POST',
        credentials: 'include',
      });
    }, firstId);
    await second.close();

    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(page.getByText(/Changed: 1/)).toBeVisible();
    await page.getByRole('button', { name: 'Restore unchanged records' }).click();
    await expect(page.getByText(/Recovered 1 record/)).toBeVisible();
    await expect.poll(async () => page.locator('tbody tr').count()).toBe(1);
  });

  test('expired_undo_archive_still_recoverable', async ({ page }) => {
    await archiveSelected(page, 1);
    await page.route('**/crm/bulk-actions/*/undo', async (route) => {
      await route.fulfill({
        status: 410,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: {
            code: 'undo_expired',
            fields: [{ field: '__root__', message: 'Immediate Undo expired.' }],
          },
        }),
      });
    });
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(page.getByText(/Immediate Undo expired.*still recoverable from Archive/)).toBeVisible();
    await page.goto('/archive');
    await expect(page.locator('tbody tr')).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Restore selected' })).toBeVisible();
  });

  test('filters_work_over_all_archived_pages', async ({ page }) => {
    await archiveSelected(page, 3);
    await page.goto('/archive');
    const search = page.getByLabel('Search archived jobs');
    await search.fill('Senior Engineer');
    await expect.poll(async () => page.locator('tbody tr').count()).toBe(3);
    await search.fill('does-not-exist');
    await expect(page.getByText('No archived rows match these filters.')).toBeVisible();
    await search.fill('Acme');
    await expect.poll(async () => page.locator('tbody tr').count()).toBe(3);
  });
});
