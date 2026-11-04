import assert from 'node:assert/strict'
import { test } from 'node:test'
import { classifyJobDetailUrl } from '../site-rules.js'

const supported = (url, site, detail) => {
  const output = classifyJobDetailUrl(url)
  assert.deepEqual(output, {
    supported: true, eligibility: 'automatic', site,
    detail_id: detail, url,
  })
  assert.equal(Object.hasOwn(output, 'company'), false)
}

// ext_28_case_01
test('accepts only the frozen exact-host ATS detail patterns, preserving original URL', () => {
  supported('https://boards.greenhouse.io/alpha/jobs/12345?utm_source=news', 'greenhouse', '12345')
  supported('https://job-boards.greenhouse.io/beta/jobs/67890#job', 'greenhouse', '67890')
  supported('https://jobs.lever.co/alpha/234c8b09-87a1-4d2c-9874-a1f0bd420cde',
    'lever', '234c8b09-87a1-4d2c-9874-a1f0bd420cde')
})

// ext_28_case_02
test('rejects spoofed domains, lists, forms, private schemes, secrets and encoded paths', () => {
  for (const url of [
    'https://jobs.lever.co.evil.test/acme/123',
    'https://evil-jobs.lever.co/acme/123',
    'http://jobs.lever.co/acme/123',
    'javascript:alert(1)',
    'file:///etc/passwd',
    'https://boards.greenhouse.io/acme',
    'https://boards.greenhouse.io/acme/jobs',
    'https://boards.greenhouse.io/acme/jobs/123/apply',
    'https://jobs.lever.co/acme/123/apply',
    'https://jobs.lever.co/acme/123/application',
    'https://jobs.lever.co/acme/123?session_token=secret',
    'https://jobs.lever.co/acme/123?%74oken=secret',
    'https://jobs.lever.co/acme/123?ACCESS_TOKEN=abc',
    'https://user:secret@jobs.lever.co/acme/123',
    'https://jobs.lever.co:8443/acme/123',
    'https://jobs.lever.co/acme/%2Fsecret',
    'https://boards.greenhouse.io/acme/jobs/%2e%2e',
    'https://jobs.lever.co/acme/123/extra',
    'https://jobs.lever.co/acme/123\n',
    '',
    'https://jobs.lever.co/acme/123' + 'x'.repeat(2049),
  ]) {
    const result = classifyJobDetailUrl(url)
    assert.equal(result.supported, false, url)
    assert.equal(result.eligibility, 'manual')
    assert.equal(result.url, null)
  }
})

// ext_28_case_03
test('does not infer employer from ATS host or tenant slug', () => {
  const a = classifyJobDetailUrl('https://jobs.lever.co/company-a/role-42')
  const b = classifyJobDetailUrl('https://jobs.lever.co/company-b/role-42')
  assert.equal(a.supported, true)
  assert.equal(b.supported, true)
  assert.equal(a.site, b.site)
  assert.equal(a.detail_id, b.detail_id)
  assert.equal(Object.hasOwn(a, 'company'), false)
  assert.equal(Object.hasOwn(b, 'company'), false)
  assert.notEqual(a.url, b.url)
  assert.deepEqual(classifyJobDetailUrl('https://jobs.lever.co/company-a/role-42'), a)
})
