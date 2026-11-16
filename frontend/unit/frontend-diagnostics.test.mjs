import test from 'node:test'
import assert from 'node:assert/strict'
import { installBrowserDiagnostics, logApiFailure, logReactFailure, logUiFeedback } from '../src/api/diagnostics.js'

test('API logging reports safe metadata without URLs, bodies, headers or credentials', () => {
  const captured = []
  const previous = console.warn
  console.warn = (...args) => captured.push(args)
  try {
    logApiFailure({
      config: { method: 'post', url: '/crm/companies/secret@example.com?token=private' },
      response: {
        status: 429, headers: { authorization: 'private' },
        data: { detail: 'password=private' },
      },
    }, { kind: 'hosting_throttle', retryAfter: 12, level: 'warn' })
    assert.equal(captured.length, 1)
    assert.deepEqual(captured[0][1], {
      event: 'api_failure', kind: 'hosting_throttle', status: 429,
      method: 'POST', resource: 'crm', retryAfterSeconds: 12,
    })
    assert.doesNotMatch(JSON.stringify(captured), /private|example.com|password|secret/)
  } finally {
    console.warn = previous
  }
})

test('expected auth checks do not generate outage noise and canceled requests are ignored', () => {
  const captured = []
  const previous = console.warn
  console.warn = (...args) => captured.push(args)
  try {
    logApiFailure({ response: { status: 401 } }, null)
    logApiFailure({ code: 'ERR_CANCELED' }, null)
    assert.equal(captured.length, 0)
  } finally {
    console.warn = previous
  }
})

test('UI error and warning toasts log severity without free-text content', () => {
  const warnings = []
  const errors = []
  const oldWarn = console.warn
  const oldError = console.error
  console.warn = (...args) => warnings.push(args)
  console.error = (...args) => errors.push(args)
  try {
    logUiFeedback('warning')
    logUiFeedback('error')
    logUiFeedback('success')
    logReactFailure()
    assert.equal(warnings.length, 1)
    assert.equal(errors.length, 2)
    assert.equal(warnings[0][1].event, 'ui_feedback')
    assert.equal(errors[0][1].event, 'ui_feedback')
    assert.equal(errors[1][1].event, 'react_render_failure')
  } finally {
    console.warn = oldWarn
    console.error = oldError
  }
})

test('global browser handlers capture all uncaught errors with redacted metadata', () => {
  const oldWindow = globalThis.window
  const oldError = console.error
  const listeners = new Map()
  const errors = []
  globalThis.window = { addEventListener: (name, fn) => listeners.set(name, fn) }
  console.error = (...args) => errors.push(args)
  try {
    installBrowserDiagnostics()
    assert.ok(listeners.has('error'))
    assert.ok(listeners.has('unhandledrejection'))
    listeners.get('error')({ message: 'token=private' })
    listeners.get('unhandledrejection')({ reason: new Error('password=private') })
    assert.deepEqual(errors.map((entry) => entry[1].event), ['uncaught_browser_error', 'unhandled_promise_rejection'])
    assert.doesNotMatch(JSON.stringify(errors), /private|password/)
  } finally {
    if (oldWindow === undefined) delete globalThis.window
    else globalThis.window = oldWindow
    console.error = oldError
  }
})
