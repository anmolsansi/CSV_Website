import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('../background.js', import.meta.url), 'utf8')
const UUID = '1b8cee75-42c0-45b1-8c46-bfcfa1d1ffcc'
const APP = 'https://csv-website-steel.vercel.app'
const JOB = 'https://jobs.lever.co/acme/role-123'
const POPUP = { id: 'ext-test', url: 'chrome-extension://ext-test/popup.html',
  origin: 'chrome-extension://ext-test', frameId: 0 }
const packet = (type, extra = {}) => ({ type, version: 1, request_id: UUID, ...extra })
const res = (id, extras = {}) => ({ version: 1, request_id: UUID, ok: true,
  data: { protocol_version: 1, account_id: id, ...extras } })

export function createWorker() {
  const permissions = new Set([APP + '/*'])
  const scripts = new Map()
  const requested = []
  const storageLocal = {}
  const storageSession = {}
  const tabs = new Map([
    [1, { id: 1, url: APP + '/dashboard', status: 'complete' }],
    [2, { id: 2, url: JOB, status: 'complete' }],
  ])
  let listener, updated, removed, permissionRemoved
  const calls = []
  const scriptOperations = []
  const chrome = {
    runtime: {
      id: 'ext-test', getURL: path => 'chrome-extension://ext-test/' + path,
      onMessage: { addListener: fn => { listener = fn } },
    },
    permissions: {
      contains: async ({ origins }) => origins.every(origin => permissions.has(origin)),
      request: async ({ origins }) => {
        requested.push(...origins)
        for (const origin of origins) permissions.add(origin)
        return true
      },
      onRemoved: { addListener: fn => { permissionRemoved = fn } },
    },
    scripting: {
      executeScript: async () => [{ documentId: 'doc-app' }],
      getRegisteredContentScripts: async ({ ids }) => ids.filter(id => scripts.has(id))
        .map(id => scripts.get(id)),
      registerContentScripts: async items => {
        for (const item of items) {
          scripts.set(item.id, item)
          scriptOperations.push(['register', item])
        }
      },
      unregisterContentScripts: async ({ ids }) => {
        for (const id of ids) {
          scripts.delete(id)
          scriptOperations.push(['unregister', id])
        }
      },
    },
    tabs: {
      get: async id => {
        if (!tabs.has(id)) throw Error('missing tab')
        return tabs.get(id)
      },
      query: async () => [tabs.get(1)],
      sendMessage: async (tabId, message) => {
        calls.push([tabId, message])
        if (message.type === 'ext29:extract') {
          return { version: 1, request_id: message.request_id, ok: true, url: JOB,
            company: 'Acme', title: 'Engineer' }
        }
        return { version: 1, request_id: message.request_id, ok: true,
          data: message.kind === 'session'
            ? { protocol_version: 1, account_id: 101, account_label: 'Test account' }
            : message.kind === 'check'
              ? { protocol_version: 1, account_id: 101, checked_at: '2026-11-04T00:00:00Z',
                visit: { visited: false, first_visited_at: null }, matches: [],
                company_history_count: 0, company_known: false, lookup_complete: true }
              : { protocol_version: 1, account_id: 101, created: true,
                first_visited_at: '2026-11-04T00:00:01Z' },
        }
      },
      onUpdated: { addListener: fn => { updated = fn } },
      onRemoved: { addListener: fn => { removed = fn } },
    },
    storage: {
      local: {
        get: async key => ({ [key]: storageLocal[key] }),
        set: async obj => Object.assign(storageLocal, obj),
      },
      session: {
        get: async key => ({ [key]: storageSession[key] }),
        set: async obj => Object.assign(storageSession, obj),
        remove: async key => { for (const k of Array.isArray(key) ? key : [key]) delete storageSession[k] },
      },
    },
  }
  vm.runInNewContext(source, {
    chrome, URL, TextEncoder, crypto: globalThis.crypto,
    setTimeout, clearTimeout,
  }, { filename: 'background.js', timeout: 1000 })
  async function send(message, sender = POPUP) {
    return await new Promise(resolve => {
      const accepted = listener(message, sender, resolve)
      assert.equal(accepted, true)
    })
  }
  return {
    send, calls, scripts, requested, scriptOperations, storageSession, storageLocal,
    permissions, tabs, packet, connect: () => send(packet('ext26:connect', { tab_id: 1 })),
    emitUpdated: (id, change) => { const tab = tabs.get(id); Object.assign(tab, change);
      updated?.(id, change, tab) },
    revoke: origin => { permissions.delete(origin); permissionRemoved?.({ origins: [origin] }) },
    remove: id => { tabs.delete(id); removed?.(id) },
  }
}

test('EXT-30 never asks for access or registers a content script on startup', async () => {
  const worker = createWorker()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(worker.requested, [])
  assert.equal(worker.scripts.size, 0)
  const status = await worker.send(packet('ext30:site-status', { host: 'jobs.lever.co' }))
  assert.equal(status.data.opted_in, false)
  assert.equal(status.data.permission_granted, false)
})

test('EXT-30 requires a selected account and popup gesture, then registers one exact host', async () => {
  const w = createWorker()
  const request = packet('ext30:site-opt-in', { host: 'jobs.lever.co', enabled: true })
  assert.equal((await w.send(request)).error.code, 'not_connected')
  assert.equal(w.requested.length, 0)
  assert.equal((await w.connect()).ok, true)
  const enabled = await w.send(request)
  assert.equal(enabled.ok, true)
  assert.equal(enabled.data.opted_in, true)
  assert.deepEqual(w.requested, ['https://jobs.lever.co/*'])
  const entries = [...w.scripts.values()]
  assert.equal(entries.length, 1)
  assert.equal(entries[0].id, 'jobgrid-public-jobs-lever-co')
  assert.deepEqual(Array.from(entries[0].matches), ['https://jobs.lever.co/*'])
  assert.deepEqual(Array.from(entries[0].js), ['job-candidates.js'])
  assert.equal(entries[0].allFrames, false)
  assert.equal(entries[0].persistAcrossSessions, false)
  await w.send(request)
  assert.equal(w.scripts.size, 1, 'registering twice is idempotent')
  const disabled = await w.send(packet('ext30:site-opt-in', {
    host: 'jobs.lever.co', enabled: false,
  }))
  assert.equal(disabled.ok, true)
  assert.equal(w.scripts.size, 0)
  assert.equal(w.storageLocal.jobgridSiteOptIns['jobs.lever.co'], undefined)
})

test('EXT-30 denies forged senders, unknown hosts and revocation cannot remain opted in', async () => {
  const w = createWorker()
  await w.connect()
  for (const message of [
    packet('ext30:site-opt-in', { host: 'jobs.lever.co.evil.test', enabled: true }),
    packet('ext30:site-opt-in', { host: 'jobs.lever.co', enabled: 'true' }),
    packet('ext30:site-status', { host: 'boards.greenhouse.io', extra: 'spoof' }),
  ]) assert.equal((await w.send(message)).ok, false)
  assert.equal((await w.send(packet('ext30:site-opt-in', {
    host: 'jobs.lever.co', enabled: true,
  }), { ...POPUP, url: 'https://jobs.lever.co/acme/role' })).ok, false)
  await w.send(packet('ext30:site-opt-in', { host: 'jobs.lever.co', enabled: true }))
  w.revoke('https://jobs.lever.co/*')
  await new Promise(resolve => setImmediate(resolve))
  const status = await w.send(packet('ext30:site-status', { host: 'jobs.lever.co' }))
  assert.equal(status.data.opted_in, false)
  assert.equal(w.scripts.size, 0)
})
