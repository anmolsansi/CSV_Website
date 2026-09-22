import { test, expect, type APIRequestContext } from '@playwright/test'

const API_URL = 'http://localhost:8000'

async function resetAndLogin(request: APIRequestContext) {
  await request.post(`${API_URL}/test/reset`)
  await request.post(`${API_URL}/test/seed`)
  const login = await request.post(`${API_URL}/auth/dev-login`, {
    data: { email: 'test@jobgrid.dev' },
  })
  expect(login.ok()).toBeTruthy()
}

function captureUrl(payload: Record<string, unknown>) {
  return `/capture#payload=${encodeURIComponent(JSON.stringify(payload))}`
}

test.describe('JG-047/JG-048 quick capture', () => {
  test.beforeEach(async ({ request }) => {
    await resetAndLogin(request)
  })

  test('bookmarklet_payload_edit_save', async ({ page }) => {
    const unique = Date.now()
    const jobUrl = `https://capture-ui.example/jobs/${unique}`
    await page.goto(captureUrl({
      job_url: jobUrl,
      title: 'Draft Engineer',
      company: '',
      source: 'bookmarklet',
      notes: 'Saved from a source page.',
    }))

    await expect(page).toHaveURL(/\/capture$/)
    await expect(page.locator('#capture-url')).toHaveValue(jobUrl)
    await page.locator('#capture-title').fill('Platform Engineer')
    await page.locator('#capture-company').fill('Capture UI Co')
    await page.getByRole('button', { name: 'Save job' }).click()

    await expect(page.getByTestId('capture-result')).toContainText('Row #')
    const rows = await page.request.get(`${API_URL}/rows`, {
      params: { q: String(unique), page: 1, page_size: 10 },
    })
    expect(rows.ok()).toBeTruthy()
    const payload = await rows.json()
    expect(payload.total_count).toBe(1)
    expect(payload.rows[0].data.title).toBe('Platform Engineer')
  })

  test('expired_or_malformed_draft_discarded', async ({ page }) => {
    await page.goto('/capture')
    await page.evaluate(() => {
      sessionStorage.setItem('jobgrid:capture-draft:v1', '{not-json')
    })
    await page.reload()
    await expect(page.locator('#capture-url')).toHaveValue('')

    await page.evaluate(() => {
      sessionStorage.setItem('jobgrid:capture-draft:v1', JSON.stringify({
        saved_at: Date.now() - (2 * 60 * 60 * 1000),
        draft: {
          job_url: 'https://expired.example/jobs/1',
          title: 'Expired',
          company: 'Expired Co',
          source: 'bookmarklet',
          notes: '',
        },
      }))
    })
    await page.reload()
    await expect(page.locator('#capture-url')).toHaveValue('')
    await expect(page.locator('#capture-title')).toHaveValue('')
  })

  test('login_preserves_valid_draft', async ({ page }) => {
    const jobUrl = `https://login-draft.example/jobs/${Date.now()}`
    await page.context().clearCookies()
    await page.goto(captureUrl({
      job_url: jobUrl,
      title: 'Login Draft Engineer',
      company: 'Login Draft Co',
      source: 'bookmarklet',
      notes: '',
    }))
    await expect(page.getByRole('heading', { name: 'Log in or sign up' })).toBeVisible()
    await expect(page).toHaveURL(/\/login\?return_to=%2Fcapture$/)

    const login = await page.request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    })
    expect(login.ok()).toBeTruthy()
    await page.goto('/capture')
    await expect(page.locator('#capture-url')).toHaveValue(jobUrl)
    await expect(page.locator('#capture-title')).toHaveValue('Login Draft Engineer')
  })

  test('external_return_url_rejected', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/login?return_to=https%3A%2F%2Fevil.example.test')
    const googleHref = await page.getByRole('link', { name: 'Continue with Google' }).getAttribute('href')
    expect(googleHref).toBeTruthy()
    expect(googleHref).not.toContain('return_to=')
    expect(googleHref).not.toContain('evil.example.test')
  })

  test('repeat_submit_one_row', async ({ page }) => {
    const unique = Date.now()
    const jobUrl = `https://repeat-capture.example/jobs/${unique}`
    await page.goto('/capture')
    await page.locator('#capture-url').fill(jobUrl)
    await page.locator('#capture-title').fill('Repeat Engineer')
    await page.locator('#capture-company').fill('Repeat Co')

    await page.getByRole('button', { name: 'Save job' }).click()
    await expect(page.getByTestId('capture-result')).toBeVisible()
    await page.getByRole('button', { name: 'Save job' }).click()
    await expect(page.getByTestId('capture-result')).toBeVisible()

    const rows = await page.request.get(`${API_URL}/rows`, {
      params: { q: String(unique), page: 1, page_size: 10 },
    })
    expect((await rows.json()).total_count).toBe(1)
  })

  test('title_markup_rendered_as_text', async ({ page }) => {
    const hostile = '<img src=x onerror="window.__captureXss=1">Staff Engineer'
    await page.goto(captureUrl({
      job_url: `https://hostile-title.example/jobs/${Date.now()}`,
      title: hostile,
      company: 'Markup Co',
      source: 'bookmarklet',
      notes: '',
    }))
    await expect(page.locator('#capture-title')).toHaveValue(hostile)
    await expect(page.locator('.capture-page img')).toHaveCount(0)
    expect(await page.evaluate(() => (window as any).__captureXss || 0)).toBe(0)
  })

  test('popup_blocked_copy_fallback', async ({ page }) => {
    await page.goto('/capture')
    const bookmarklet = await page.getByTestId('capture-bookmarklet').getAttribute('href')
    expect(bookmarklet).toBeTruthy()

    const prompted = await page.evaluate((code) => {
      ;(window as any).__capturePrompt = null
      window.open = () => null
      window.prompt = (message?: string, value?: string) => {
        ;(window as any).__capturePrompt = { message, value }
        return value || ''
      }
      document.title = '<b>Hostile title</b>'
      history.replaceState({}, '', '/synthetic-source')
      ;(0, eval)(String(code).replace(/^javascript:/, ''))
      return (window as any).__capturePrompt
    }, bookmarklet)

    expect(prompted.message).toContain('Popup blocked')
    expect(prompted.value).toContain('/capture#payload=')
    const payloadText = new URL(prompted.value).hash.replace(/^#payload=/, '')
    const decoded = JSON.parse(decodeURIComponent(payloadText))
    expect(decoded.title).toBe('<b>Hostile title</b>')
    expect(decoded.job_url).toContain('/synthetic-source')
  })

  test('duplicate_warning_survives_capture_flow', async ({ page, request }) => {
    const rowsResponse = await request.get(`${API_URL}/rows`, {
      params: { sort_by: 'created_at', sort_dir: 'asc', page: 1, page_size: 1 },
    })
    const seedRow = (await rowsResponse.json()).rows[0]
    const prior = await request.post(`${API_URL}/crm/from-row/${seedRow.id}`)
    expect(prior.ok()).toBeTruthy()
    const priorTrack = await prior.json()
    expect((await request.patch(`${API_URL}/crm/applications/${priorTrack.id}`, {
      data: { mark_applied: true },
    })).ok()).toBeTruthy()

    const variantUrl = `${seedRow.data.url}?utm_source=capture-flow`
    await page.goto(captureUrl({
      job_url: variantUrl,
      title: seedRow.data.title,
      company: seedRow.data.company_guess,
      source: 'bookmarklet',
      notes: '',
    }))

    await expect(page.getByTestId('capture-match-list')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('capture-match-canonical')).toBeVisible()
    await expect(page.getByTestId('capture-match-list')).toContainText('View application history')
  })

  test('five_job_capture_synthetic_timing', async ({ page }, testInfo) => {
    const timings: number[] = []
    await page.goto('/capture')

    for (let index = 0; index < 5; index += 1) {
      const started = Date.now()
      const unique = `${Date.now()}-${index}`
      await page.locator('#capture-url').fill(`https://timing.example/jobs/${unique}`)
      await page.locator('#capture-title').fill(`Timing Engineer ${index}`)
      await page.locator('#capture-company').fill('Timing Co')
      await page.getByRole('button', { name: 'Save job' }).click()
      await expect(page.getByTestId('capture-result')).toBeVisible()
      timings.push(Date.now() - started)
    }

    expect(timings).toHaveLength(5)
    expect(Math.max(...timings)).toBeLessThan(60_000)
    console.log(`JG-048 five-job automated browser capture timings (ms): ${timings.join(',')}`)
    testInfo.annotations.push({
      type: 'automated-browser-capture-timing-ms',
      description: timings.join(','),
    })
  })
})
