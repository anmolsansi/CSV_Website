import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('../job-candidates.js', import.meta.url), 'utf8')
const UUID = '1b8cee75-42c0-45b1-8c46-bfcfa1d1ffcc'
const packet = url => ({ type: 'ext29:extract', version: 1, request_id: UUID, url })
const lever = 'https://jobs.lever.co/acme/role-123'
const gh = 'https://boards.greenhouse.io/acme/jobs/123'

function setup(url, nodes = {}, { subframe = false } = {}) {
  let listener
  const queries = []
  const top = {}
  const context = {
    chrome: { runtime: { id: 'test', onMessage: { addListener: fn => { listener = fn } } } },
    location: { href: url },
    window: subframe ? { top: {} } : { top },
    document: {
      querySelector: selector => { queries.push(selector); return nodes[selector] ?? null },
    },
    URL,
  }
  if (!subframe) context.window.top = context.window
  vm.runInNewContext(source, context, { timeout: 1000 })
  function send(message = packet(url)) {
    if (!listener) return null
    let value
    listener(message, {}, outcome => { value = JSON.parse(JSON.stringify(outcome)) })
    return value
  }
  return { send, queries, installed: () => !!listener }
}

const node = (text, { forbidden = false } = {}) => ({
  innerText: text, textContent: text,
  closest: () => forbidden ? {} : null,
})

test('EXT-29 extracts only editable, bounded public Greenhouse and Lever heading candidates', () => {
  const a = setup(gh, {
    '[data-testid="job-title"]': node('  Staff   Engineer \n'),
    '[data-testid="company-name"]': node(' Acme '),
  })
  assert.deepEqual(a.send(), {
    version: 1, request_id: UUID, ok: true, url: gh,
    title: 'Staff Engineer', company: 'Acme',
  })
  const b = setup(lever, {
    '.posting-headline h2': node('Backend Developer'),
    '.posting-company': node('Example Inc'),
  })
  assert.equal(b.send().title, 'Backend Developer')
  assert.equal(b.send().company, 'Example Inc')
  assert.ok(a.queries.every(q => !/form|input|textarea|body|script/i.test(q)))
})

test('EXT-29 ignores form descendants, hidden headings, oversize strings and unknown metadata', () => {
  const a = setup(lever, {
    '.posting-headline h2': node('Private applicant answer', { forbidden: true }),
    'h1': node('T'.repeat(501)),
    '.posting-company': node('C'.repeat(321)),
  })
  const result = a.send()
  assert.equal(result.title, null)
  assert.equal(result.company, null)
  assert.equal(a.queries.length <= 6, true)
})

test('EXT-29 refuses listing, apply and credential URLs and never runs in iframes', () => {
  for (const url of [
    'https://jobs.lever.co/acme',
    'https://boards.greenhouse.io/acme/jobs/123/apply',
    lever + '?session_token=abc',
    'https://jobs.lever.co.attacker.test/acme/role-123',
  ]) {
    const page = setup(url)
    assert.equal(page.send().ok, false, url)
    assert.equal(page.queries.length, 0)
  }
  assert.equal(setup(gh, {}, { subframe: true }).installed(), false)
})

test('EXT-29 accepts only the internal four-field extraction envelope', () => {
  const page = setup(lever)
  for (const candidate of [
    { ...packet(lever), site: 'evil' },
    { ...packet(lever), version: 2 },
    { ...packet(lever), url: gh },
    { ...packet(lever), request_id: 'bad' },
  ]) {
    assert.equal(page.send(candidate).ok, false)
  }
  assert.equal(page.queries.length, 0)
})
