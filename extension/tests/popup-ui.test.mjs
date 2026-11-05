import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'

const JOB = 'https://jobs.lever.co/acme/engineer-12'
const UUID = '1b8cee75-42c0-45b1-8c46-bfcfa1d1ffcc'
const settle = async () => { await new Promise(resolve => setImmediate(resolve)); await new Promise(resolve => setImmediate(resolve)) }

class Element {
  constructor(id) {
    this.id = id
    this.textContent = ''
    this.value = ''
    this.hidden = false
    this.checked = false
    this.disabled = false
    this.listeners = new Map()
    this.children = []
  }
  addEventListener(type, callback) {
    const list = this.listeners.get(type) || []
    list.push(callback)
    this.listeners.set(type, list)
  }
  dispatch(type) {
    for (const callback of this.listeners.get(type) || []) callback({ preventDefault() {} })
  }
  replaceChildren() { this.children = [] }
  append(value) { this.children.push(value) }
}

test('EXT-38–40 real popup module confirms one application and typed visit deletion', async () => {
  const html = readFileSync(new URL('../popup.dev.html', import.meta.url), 'utf8')
  const nodes = new Map([...html.matchAll(/id="([^"]+)"/g)]
    .map(([, id]) => [id, new Element(id)]))
  const el = id => {
    assert.ok(nodes.has(id), 'missing element ' + id)
    return nodes.get(id)
  }
  const history = []
  let account = { protocol_version: 1, connected: true, paused: false,
    account_id: 101, account_label: 'Pilot A' }
  let checked = { protocol_version: 1, account_id: 101, url: JOB,
    save_state: 'manual_only', before_visit: {
      visit: { visited: false, first_visited_at: null }, matches: [],
      lookup_complete: false, company_history_count: 0, company_known: false,
    } }
  let visitedDeleted = false
  const original = { document: globalThis.document, chrome: globalThis.chrome,
    window: globalThis.window }
  globalThis.document = {
    getElementById: id => el(id),
    createElement: name => new Element(name),
  }
  globalThis.window = { confirm: () => true }
  globalThis.chrome = {
    runtime: {
      sendMessage: async packet => {
        history.push(packet)
        let data = null
        if (packet.type === 'ext35:status') data = account
        else if (packet.type === 'ext32:tab-status') {
          if (visitedDeleted) return { version: 1, request_id: packet.request_id,
            ok: false, error: { code: 'no_check' } }
          data = checked
        } else if (packet.type === 'ext34:stage-apply') {
          data = { protocol_version: 1, pending: true, account_id: 101, url: JOB,
            company: packet.company, title: packet.title, idempotency_key: UUID }
        } else if (packet.type === 'ext39:submit-pending') {
          checked = { ...checked, apply_status: 'saved' }
          data = { protocol_version: 1, account_id: 101, saved: true, url: JOB }
        } else if (packet.type === 'ext26:command' && packet.kind === 'forget_visits') {
          visitedDeleted = true
          data = { protocol_version: 1, account_id: 101, deleted: 2 }
        }
        return { version: 1, request_id: packet.request_id, ok: true, data }
      },
    },
    tabs: { query: async () => [{ id: 2, url: JOB }] },
  }
  try {
    await import('../popup.dev.js?ui-integration')
    await settle()
    assert.equal(el('apply-section').hidden, false)
    assert.match(el('result-lookup').textContent, /incomplete/i)
    el('apply-company').value = ' Acme '
    el('apply-title').value = ' Engineer '
    el('draft-form').dispatch('submit')
    await settle()
    assert.equal(el('approval').hidden, false)
    assert.equal(el('submit-apply').disabled, true)
    el('confirm-apply').checked = true
    el('confirm-apply').dispatch('change')
    assert.equal(el('submit-apply').disabled, false)
    el('submit-apply').dispatch('click')
    await settle()
    assert.equal(history.filter(x => x.type === 'ext39:submit-pending').length, 1)
    assert.match(el('result-title').textContent, /saved/i)
    assert.equal(el('apply-section').hidden, true)

    el('forget').dispatch('click')
    el('forget-phrase').value = 'FORGET VISITS'
    el('forget-phrase').dispatch('input')
    assert.equal(el('forget-final').disabled, false)
    el('forget-final').dispatch('click')
    await settle()
    assert.equal(history.filter(x => x.kind === 'forget_visits').length, 1)
    assert.equal(history.find(x => x.kind === 'forget_visits').payload.confirmed, true)
    assert.match(el('feedback').textContent, /2 external visit/)
    assert.equal(el('forget-confirmation').hidden, true)
    assert.match(el('open-jobgrid').href, /^https:\/\/csv-website-steel\.vercel\.app\/applications$/)
  } finally {
    globalThis.document = original.document
    globalThis.chrome = original.chrome
    globalThis.window = original.window
  }
})
