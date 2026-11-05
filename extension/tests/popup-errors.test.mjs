import assert from 'node:assert/strict'
import { test } from 'node:test'
import { summarizeFailure, summarizeWarning } from '../popup-state.js'

const warning = (overrides = {}) => ({
  save_state: 'manual_only',
  before_visit: {
    visit: { visited: false, first_visited_at: null },
    matches: [], company_known: false, company_history_count: 0,
    lookup_complete: false, ...overrides,
  },
})

test('EXT-37 incomplete matching remains visible even alongside stronger evidence', () => {
  for (const info of [
    warning(),
    warning({ company_history_count: 2, company_known: true }),
    warning({ matches: [{ confidence: 'exact', company: 'Acme', title: 'Role' }] }),
  ]) {
    const result = summarizeWarning(info)
    assert.match(result.lookup, /incomplete/i)
    assert.doesNotMatch(result.lookup, /never applied/i)
  }
  assert.equal(summarizeWarning(null).kind, 'empty')
})

test('EXT-37 shows distinct offline/401/403/429/timeout/unsupported/unavailable states', () => {
  assert.equal(summarizeFailure({ code: 'offline' }).kind, 'offline')
  assert.equal(summarizeFailure({ code: 'not_authenticated' }).kind, 'auth')
  assert.equal(summarizeFailure({ code: 'account_changed' }).kind, 'auth')
  assert.equal(summarizeFailure({ code: 'forbidden' }).kind, 'forbidden')
  assert.equal(summarizeFailure({ code: 'permission_denied' }).kind, 'forbidden')
  assert.equal(summarizeFailure({ code: 'rate_limited', retry_after: 7 }).kind, 'rate_limited')
  assert.match(summarizeFailure({ code: 'rate_limited', retry_after: 7 }).detail, /7 seconds/)
  assert.doesNotMatch(summarizeFailure({ code: 'rate_limited', retry_after: -1 }).detail, /-1 seconds/)
  assert.equal(summarizeFailure({ code: 'timeout' }).kind, 'timeout')
  assert.equal(summarizeFailure({ code: 'unsupported' }).kind, 'unsupported')
  assert.equal(summarizeFailure({ code: 'protocol_error' }).kind, 'unsupported')
  assert.equal(summarizeFailure({ code: 'unavailable' }).kind, 'unavailable')
  assert.doesNotMatch(summarizeFailure({ code: 'unavailable' }).detail, /never applied/i)
})

test('EXT-37 ambiguous apply failure never claims save success', () => {
  for (const code of ['timeout', 'save_unknown', 'unavailable']) {
    const result = summarizeFailure({ code }, 'apply')
    assert.match(result.detail, /may have been saved/i)
    assert.doesNotMatch(result.detail, /was saved successfully/i)
  }
  assert.equal(summarizeFailure({ code: 'forbidden' }, 'apply').kind, 'forbidden')
})
