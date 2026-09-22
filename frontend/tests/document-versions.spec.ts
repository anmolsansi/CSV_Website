import { randomUUID } from 'node:crypto'
import { request as playwrightRequest, test, expect, type APIRequestContext } from '@playwright/test'

const API_URL = 'http://localhost:8000'
const PDF_V1 = Buffer.from('%PDF-1.4\nresume-version-one\n%%EOF\n')
const PDF_V2 = Buffer.from('%PDF-1.4\nresume-version-two\n%%EOF\n')

async function resetAndLogin(request: APIRequestContext) {
  await request.post(`${API_URL}/test/reset`)
  await request.post(`${API_URL}/test/seed`)
  const login = await request.post(`${API_URL}/auth/dev-login`, {
    data: { email: 'test@jobgrid.dev' },
  })
  expect(login.ok()).toBeTruthy()
}

async function createTrack(request: APIRequestContext) {
  const rowsResponse = await request.get(`${API_URL}/rows`, {
    params: { page: 1, page_size: 5, sort_by: 'created_at', sort_dir: 'asc' },
  })
  expect(rowsResponse.ok()).toBeTruthy()
  const rows = (await rowsResponse.json()).rows || []
  expect(rows.length).toBeGreaterThan(0)

  const created = await request.post(`${API_URL}/crm/from-row/${rows[0].id}`)
  expect(created.ok()).toBeTruthy()
  return await created.json()
}

async function documentByLabel(request: APIRequestContext, label: string) {
  const response = await request.get(`${API_URL}/crm/documents`)
  expect(response.ok()).toBeTruthy()
  const data = await response.json()
  return (data.items || []).find((item: any) => item.label === label)
}

async function uploadFromLibrary(page: any, label: string, contents: Buffer, filename: string) {
  await page.getByLabel('Document label').fill(label)
  await page.getByLabel('Document file').setInputFiles({
    name: filename,
    mimeType: 'application/pdf',
    buffer: contents,
  })
  await page.getByRole('button', { name: 'Upload document', exact: true }).click()
  await expect(page.getByTestId('document-library').getByText(label, { exact: true }))
    .toBeVisible({ timeout: 15000 })
}

test.describe('JG-043 document versions', () => {
  test('application_A_keeps_v1_after_v2', async ({ page, request }) => {
    await resetAndLogin(request)
    const track = await createTrack(request)
    const label = `Resume ${randomUUID().slice(0, 8)}`

    await page.goto('/documents')
    await uploadFromLibrary(page, label, PDF_V1, 'resume-v1.pdf')
    const v1 = await documentByLabel(request, label)
    expect(v1).toBeTruthy()
    expect(v1.version_number).toBe(1)

    await page.goto(`/applications?track_id=${track.id}`)
    const panel = page.getByTestId('application-documents')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await panel.getByLabel('Document version').selectOption(v1.id)
    await panel.getByLabel('Document usage').selectOption('used')
    await panel.getByRole('button', { name: 'Attach document' }).click()
    await expect(panel.getByTestId(`application-document-${v1.id}`)).toContainText('Used')

    await page.goto(`/documents?track_id=${track.id}`)
    const v1Card = page.getByTestId(`document-${v1.id}`)
    await v1Card.getByRole('button', { name: 'New version' }).click()
    await page.getByLabel('Document file').setInputFiles({
      name: 'resume-v2.pdf',
      mimeType: 'application/pdf',
      buffer: PDF_V2,
    })
    await page.getByRole('button', { name: 'Upload new version' }).click()
    await expect(page.getByText('v2', { exact: true }).last()).toBeVisible({ timeout: 15000 })

    await page.getByRole('link', { name: 'Back to application' }).click()
    await expect(page.getByTestId('application-documents')).toBeVisible({ timeout: 15000 })
    const attached = page.getByTestId(`application-document-${v1.id}`)
    await expect(attached).toBeVisible()
    await expect(attached).toContainText('v1')
    await expect(attached).toContainText('Used')
  })

  test('failed_upload_never_appears_ready', async ({ page, request }) => {
    await resetAndLogin(request)
    const label = `Bad ${randomUUID().slice(0, 8)}`

    await page.goto('/documents')
    await page.getByLabel('Document label').fill(label)
    await page.getByLabel('Document file').setInputFiles({
      name: 'looks-like.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('this is text, not a PDF signature'),
    })
    await page.getByRole('button', { name: 'Upload document', exact: true }).click()

    await expect(page.getByRole('alert')).toBeVisible({ timeout: 10000 })
    const response = await request.get(`${API_URL}/crm/documents`)
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    expect((data.items || []).some(
      (item: any) => item.label === label && item.state === 'ready'
    )).toBeFalsy()
    await expect(page.getByTestId('document-library').getByText(label, { exact: true }))
      .toHaveCount(0)
  })

  test('referenced_delete_conflict_explained', async ({ page, request }) => {
    await resetAndLogin(request)
    const track = await createTrack(request)
    const label = `Referenced ${randomUUID().slice(0, 8)}`

    await page.goto('/documents')
    await uploadFromLibrary(page, label, PDF_V1, 'referenced.pdf')
    const document = await documentByLabel(request, label)

    const attached = await request.post(`${API_URL}/crm/tracks/${track.id}/documents`, {
      data: { document_version_id: document.id, usage: 'reference' },
    })
    expect(attached.ok()).toBeTruthy()

    await page.reload()
    page.once('dialog', (dialog) => dialog.accept())
    await page.getByTestId(`document-${document.id}`)
      .getByRole('button', { name: 'Delete' }).click()

    const conflict = page.getByTestId('document-delete-conflict')
    await expect(conflict).toBeVisible({ timeout: 10000 })
    await expect(conflict).toContainText('Detach before deleting')
    await expect(conflict).toContainText('Reference')
    await expect(conflict.getByRole('link')).toHaveAttribute(
      'href',
      `/applications?track_id=${track.id}`
    )
  })

  test('download_requires_current_session', async ({ page, request }) => {
    await resetAndLogin(request)
    const label = `Private ${randomUUID().slice(0, 8)}`

    await page.goto('/documents')
    await uploadFromLibrary(page, label, PDF_V1, 'private.pdf')
    const document = await documentByLabel(request, label)

    const authenticated = await request.get(
      `${API_URL}/crm/documents/${document.id}/download`
    )
    expect(authenticated.ok()).toBeTruthy()
    expect(await authenticated.body()).toEqual(PDF_V1)

    const anonymous = await playwrightRequest.newContext()
    try {
      const unauthenticated = await anonymous.get(
        `${API_URL}/crm/documents/${document.id}/download`
      )
      expect([401, 403]).toContain(unauthenticated.status())
    } finally {
      await anonymous.dispose()
    }
  })
})
