import assert from 'node:assert/strict'
import { test } from 'node:test'
import { normalizeApplicationFields, checkedJobForAccount, sameStagedIntent } from '../popup-apply.js'

const state = { connected: true, paused: false, account_id: 101 }
const record = { account_id: 101, url: 'https://jobs.lever.co/acme/1',
  before_visit: { visit: { visited: false }, matches: [] } }
const fields = { company: 'Acme', title: 'Engineer' }

test('EXT-38 draft requires two trimmed bounded fields and never guesses the employer', () => {
  assert.deepEqual(normalizeApplicationFields(' Acme ', ' Engineer '), { ok: true, ...fields })
  for (const input of [
    ['', 'Engineer'], ['Acme', ''], ['   ', ' Engineer '],
    ['a'.repeat(321), 'Engineer'], ['Acme', 'b'.repeat(501)],
    [null, 'Engineer'], ['Acme', undefined],
  ]) assert.equal(normalizeApplicationFields(...input).ok, false)
  assert.equal(normalizeApplicationFields('🔧', 'A'.repeat(500)).ok, true)
})

test('EXT-38 checked account and URL must bind the prepared intent exactly', () => {
  const pending = { pending: true, account_id: 101, url: record.url,
    ...fields, idempotency_key: '1b8cee75-42c0-45b1-8c46-bfcfa1d1ffcc' }
  assert.equal(checkedJobForAccount(record, state), true)
  assert.equal(sameStagedIntent(record, state, pending, fields), true)
  assert.equal(sameStagedIntent(record, state, { ...pending, url: 'https://other.test' }, fields), false)
  assert.equal(sameStagedIntent(record, state, pending, { ...fields, company: 'Other' }), false)
  assert.equal(sameStagedIntent(record, { ...state, account_id: 202 }, pending, fields), false)
  assert.equal(sameStagedIntent(record, { ...state, paused: true }, pending, fields), false)
  assert.equal(checkedJobForAccount({ ...record, before_visit: null }, state), false)
})

test('EXT-38 popup has explicit labels and confirmation; does not read page form contents', async () => {
  const { readFileSync } = await import('node:fs')
  const html = readFileSync(new URL('../popup.dev.html', import.meta.url), 'utf8')
  const js = readFileSync(new URL('../popup.dev.js', import.meta.url), 'utf8')
  for (const id of ['apply-company', 'apply-title', 'confirm-apply']) {
    assert.match(html, new RegExp('for="' + id + '"'))
  }
  assert.match(html, /Reviewed|Review application details/)
  assert.match(js, /ext34:stage-apply/)
  assert.doesNotMatch(js, /innerHTML|insertAdjacentHTML|eval\s*\(/)
})
