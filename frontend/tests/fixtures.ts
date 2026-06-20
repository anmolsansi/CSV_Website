import { test as base } from '@playwright/test';

interface TestFixtures {
  authPage: AuthPage;
  dashboardPage: DashboardPage;
  applicationsPage: ApplicationsPage;
  apiHelper: ApiHelper;
}

class AuthPage {
  constructor(private page: any) {}

  async loginWithTestUser() {
    await this.page.goto('/');
    await this.page.waitForSelector('text=JobGrid', { timeout: 10000 });
  }
}

class DashboardPage {
  constructor(private page: any) {}

  async uploadCSV(csvContent: string) {
    const fileInput = this.page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'test-jobs.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(csvContent),
    });
    await this.page.waitForSelector('text=Upload complete', { timeout: 10000 });
  }

  async selectRows(count: number) {
    const checkboxes = this.page.locator('tbody input[type="checkbox"]');
    for (let i = 0; i < Math.min(count, await checkboxes.count()); i++) {
      await checkboxes.nth(i).check();
    }
  }

  async clickSendToApplications() {
    await this.page.click('button:has-text("Send to Applications")');
    await this.page.waitForSelector('text=Created:', { timeout: 10000 });
  }

  async clickOpenSelected() {
    const [popup] = await Promise.all([
      this.page.waitForEvent('popup'),
      this.page.click('button:has-text("Open selected")'),
    ]);
    return popup;
  }
}

class ApplicationsPage {
  constructor(private page: any) {}

  async goto() {
    await this.page.click('nav a:has-text("Applications")');
    await this.page.waitForSelector('h2:has-text("Applications")');
  }

  async selectAllVisible() {
    await this.page.check('thead input[type="checkbox"]');
  }

  async bulkMarkApplied() {
    await this.page.click('button:has-text("Mark applied")');
    await this.page.waitForSelector('text=Marked', { timeout: 10000 });
  }

  async verifyRowStatus(rowIndex: number, expectedStatus: string) {
    const row = this.page.locator('tbody tr').nth(rowIndex);
    await expect(row.locator('select')).toHaveValue(expectedStatus);
  }
}

class ApiHelper {
  constructor(private page: any) {}

  async seedTestData() {
    await this.page.request.post('http://localhost:8000/test/seed', {
      data: { user: 'test@example.com' },
    });
  }
}

export const test = base.extend<TestFixtures>({
  authPage: async ({ page }, use) => {
    await use(new AuthPage(page));
  },
  dashboardPage: async ({ page }, use) => {
    await use(new DashboardPage(page));
  },
  applicationsPage: async ({ page }, use) => {
    await use(new ApplicationsPage(page));
  },
  apiHelper: async ({ page }, use) => {
    await use(new ApiHelper(page));
  },
});

export { expect } from '@playwright/test';