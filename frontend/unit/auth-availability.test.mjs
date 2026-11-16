import test from 'node:test'
import assert from 'node:assert/strict'
import { classifyRequestFailure, emailAuth429Message, isRenderHibernationThrottle, readRetryAfter, sessionCheckProblem } from '../src/api/authAvailability.js'

const failure = (status, headers = {}, data = null) => ({ response: { status, headers, data } })

test('401 / 403 represent unauthenticated or forbidden, not infrastructure outage', () => {
  assert.equal(sessionCheckProblem(failure(401)), null)
  assert.equal(sessionCheckProblem(failure(403)), null)
})

test('session 429 does not become login state and has safe retry guidance', () => {
  const problem = sessionCheckProblem(failure(429, { 'retry-after': '75' }))
  assert.equal(problem.kind, 'rate_limited')
  assert.equal(problem.retryAfter, 75)
  assert.match(problem.message, /could not check your existing session/)
})

test('failed upstream session check stays unknown, never marked logged out', () => {
  assert.equal(sessionCheckProblem(failure(503)).kind, 'unavailable')
  assert.equal(sessionCheckProblem({}).kind, 'unavailable')
})

test('Render signature is required to claim hosting hibernation', () => {
  assert.equal(isRenderHibernationThrottle(failure(429, { 'x-render-routing': 'hibernate-rate-limited' })), true)
  assert.equal(isRenderHibernationThrottle(failure(429)), false)
  assert.equal(isRenderHibernationThrottle(failure(401, { 'x-render-routing': 'hibernate-rate-limited' })), false)
})

test('provider 429 is not a wrong-password error', () => {
  assert.match(emailAuth429Message(failure(429, { 'x-render-routing': 'hibernate-rate-limited' })), /password was not checked/)
  assert.match(emailAuth429Message(failure(429)), /might not have been checked/)
})

test('application rate guard remains distinguishable from unknown 429', () => {
  const msg = emailAuth429Message(failure(429, {}, { detail: 'Too many attempts. Try again later.' }))
  assert.match(msg, /Too many sign-in attempts/)
})

test('retry-after only accepts bounded positive seconds and never arbitrary text', () => {
  assert.equal(readRetryAfter({ 'retry-after': '120' }), 120)
  assert.equal(readRetryAfter({ 'retry-after': '0' }), null)
  assert.equal(readRetryAfter({ 'retry-after': '-10' }), null)
  assert.equal(readRetryAfter({ 'retry-after': '5000' }), null)
  assert.equal(readRetryAfter({ 'retry-after': 'tomorrow' }), null)
  assert.equal(readRetryAfter({}), null)
  assert.equal(readRetryAfter({ 'retry-after': '5\nX-Secret: token' }), null)
})

test('global classification distinguishes Render, application, and unknown 429s', () => {
  const render = classifyRequestFailure(failure(429, { 'x-render-routing': 'hibernate-rate-limited', 'retry-after': '8' }))
  assert.equal(render.kind, 'hosting_throttle')
  assert.equal(render.globalNotice, true)
  assert.equal(render.retryAfter, 8)

  const auth = classifyRequestFailure(failure(429, {}, { detail: 'Too many attempts. Try again later.' }))
  assert.equal(auth.kind, 'auth_attempt_limit')
  assert.equal(auth.globalNotice, false)
  assert.equal(classifyRequestFailure(failure(429)).kind, 'unknown_throttle')
})

test('global classification handles connectivity, 5xx and expected validation separately', () => {
  assert.equal(classifyRequestFailure(failure(503)).kind, 'service_unavailable')
  assert.equal(classifyRequestFailure(failure(500)).kind, 'server_failure')
  assert.equal(classifyRequestFailure({}).kind, 'network_failure')
  assert.equal(classifyRequestFailure({ code: 'ERR_CANCELED' }), null)
  assert.equal(classifyRequestFailure(failure(422)), null)
  assert.equal(classifyRequestFailure(failure(401)), null)
})

test('Retry-After also accepts bounded HTTP dates without arbitrary text', () => {
  const date = new Date(Date.now() + 90_000).toUTCString()
  const seconds = readRetryAfter({ 'retry-after': date })
  assert.ok(seconds >= 88 && seconds <= 90, String(seconds))
  assert.equal(readRetryAfter({ 'retry-after': new Date(Date.now() - 60_000).toUTCString() }), null)
  assert.equal(readRetryAfter({ 'retry-after': new Date(Date.now() + 3_700_000).toUTCString() }), null)
})
