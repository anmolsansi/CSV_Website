import { test } from 'node:test'
import assert from 'node:assert/strict'
import { reserveTabs, openJobs, webUrl } from '../src/api/openJobs.js'
const row = (id, url = `https://example.test/${id}`) => ({ id, data: { url } })
const tab = () => ({ opener: {}, closed: false, location: { replace(url) { this.url = url } }, close() { this.closed = true } })

test('reserves tabs synchronously and severs their opener', () => {
  const tabs = reserveTabs(5, { open: () => tab() })
  assert.equal(tabs.length, 5)
  assert.ok(tabs.every(t => t.opener === null))
})
test('blocked windows do not record visits', async () => {
  const tabs = reserveTabs(5, { open: () => null })
  const visited = []
  assert.equal((await openJobs(tabs, [row(1)], id => visited.push(id))).opened, 0)
  assert.deepEqual(visited, [])
})
test('navigates five in order and awaits tracking', async () => {
  const tabs = Array.from({ length: 5 }, tab)
  const visited = []
  const result = await openJobs(tabs, [1, 2, 3, 4, 5].map(id => row(id)), async id => visited.push(id))
  assert.deepEqual(visited, [1, 2, 3, 4, 5])
  assert.deepEqual(result, { opened: 5, invalid: 0, failed: 0 })
  assert.equal(tabs[4].location.url, 'https://example.test/5')
})
test('closes unused tabs for fewer and zero candidates', async () => {
  const tabs = Array.from({ length: 5 }, tab)
  await openJobs(tabs, [row(1)], async () => {})
  assert.ok(tabs.slice(1).every(t => t.closed))
  const empty = [tab()]
  await openJobs(empty, [], async () => {})
  assert.ok(empty[0].closed)
})
test('rejects unsafe and malformed URLs without visits', async () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,hi', '/relative', 'https://', 'https://user:pass@example.test']) assert.equal(webUrl(url), null)
  const result = await openJobs([tab()], [row(1, 'javascript:alert(1)')], () => assert.fail())
  assert.equal(result.invalid, 1)
})
test('reports failed persistence while preserving opened tabs', async () => {
  const tabs = [tab()]
  const result = await openJobs(tabs, [row(1)], async () => { throw new Error('offline') })
  assert.equal(result.failed, 1)
  assert.equal(result.opened, 1)
  assert.equal(tabs[0].closed, false)
})
test('reservation exceptions close partial blank tabs', () => {
  const first = tab()
  let calls = 0
  assert.throws(() => reserveTabs(5, { open: () => {
    if (calls++) throw new Error('browser unavailable')
    return first
  } }))
  assert.ok(first.closed)
})
test('closed reserved tabs do not prevent remaining tabs opening', async () => {
  const closed = tab()
  closed.close()
  const live = tab()
  const visited = []
  const result = await openJobs([closed, live], [row(1)], id => visited.push(id))
  assert.equal(result.opened, 1)
  assert.deepEqual(visited, [1])
})
