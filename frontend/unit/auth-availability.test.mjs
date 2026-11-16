import test from 'node:test'
import assert from 'node:assert/strict'
import { emailAuth429Message, isRenderHibernationThrottle, readRetryAfter, sessionCheckProblem } from '../src/api/authAvailability.js'

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
