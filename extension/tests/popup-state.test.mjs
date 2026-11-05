import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { safeMatchText, summarizeWarning } from '../popup-state.js'

const warning = (changes = {}, save_state = 'manual_only') => ({
  save_state,
  before_visit: {
    visit: { visited: false, first_visited_at: null },
    matches: [], company_known: false,
    company_history_count: 0, lookup_complete: true,
    ...changes,
  },
})

test('EXT-36 ranks definite applications ahead of possible, visits and company history', () => {
  const input = warning({
    visit: { visited: true },
    matches: [{ confidence: 'possible' }, { confidence: 'exact' }],
    company_known: true,
  })
  assert.equal(summarizeWarning(input).kind, 'applied')
  assert.equal(summarizeWarning(warning({ matches: [{ confidence: 'possible' }] })).kind, 'possible')
  assert.equal(summarizeWarning(warning({ visit: { visited: true } })).kind, 'visited')
  assert.equal(summarizeWarning(warning({ company_history_count: 3 })).kind, 'company')
})

test('EXT-36 treats incomplete search as partial and manual checks as unsaved', () => {
  const partial = summarizeWarning(warning({ lookup_complete: false }))
  assert.equal(partial.kind, 'partial')
  assert.doesNotMatch(partial.detail, /never applied/i)
  const manual = summarizeWarning(warning())
  assert.equal(manual.kind, 'clear')
  assert.match(manual.save, /not saved as a visit/)
  assert.match(summarizeWarning(warning({}, 'save_unknown')).save, /unknown/)
  assert.equal(summarizeWarning(null).kind, 'empty')
})

test('EXT-36 escapes hostile employer and job labels by using text-only DOM APIs', () => {
  const input = { company: '<img src=x onerror=alert(1)>', title: '<script>steal()</script>',
    confidence: 'exact' }
  assert.match(safeMatchText(input), /<script>/,
    'the view model returns text; the renderer must never interpret it as HTML')
  const popup = readFileSync(new URL('../popup.dev.js', import.meta.url), 'utf8')
  assert.match(popup, /\.textContent\s*=/)
  assert.match(popup, /\.replaceChildren\(\)/)
  assert.doesNotMatch(popup, /innerHTML|insertAdjacentHTML|document\.write|eval\s*\(/)
  const release = JSON.parse(readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'))
  const dev = JSON.parse(readFileSync(new URL('../manifest.dev.json', import.meta.url), 'utf8'))
  assert.equal(release.action.default_popup, 'popup.html')
  assert.equal(release.background, undefined)
  assert.equal(dev.action.default_popup, 'popup.dev.html')
})
