import test from 'node:test'
import assert from 'node:assert/strict'
import {
  RECOVERY_WINDOW_SECONDS,
  secondsUntil,
  formatCountdown,
  recoveryDeadline,
} from '../src/utils/retryCountdown.js'

test('recovery countdown starts at 120 seconds and ends at 00:00', () => {
  const startedAt = 10_000
  const deadline = recoveryDeadline(startedAt)
  assert.equal(RECOVERY_WINDOW_SECONDS, 120)
  assert.equal(secondsUntil(deadline, startedAt), 120)
  assert.equal(formatCountdown(secondsUntil(deadline, startedAt)), '02:00')
  assert.equal(formatCountdown(secondsUntil(deadline, startedAt + 1_000)), '01:59')
  assert.equal(formatCountdown(secondsUntil(deadline, startedAt + 119_000)), '00:01')
  assert.equal(formatCountdown(secondsUntil(deadline, startedAt + 120_000)), '00:00')
  assert.equal(formatCountdown(secondsUntil(deadline, startedAt + 140_000)), '00:00')
})

test('slow responses keep original start time, not another 120 seconds after failure', () => {
  const startedAt = 15_000
  const responseAt = startedAt + 90_000
  const deadline = recoveryDeadline(startedAt, responseAt)
  assert.equal(secondsUntil(deadline, responseAt), 30)
})

test('longer provider Retry-After is honored, shorter one never shortens countdown', () => {
  const startedAt = 100_000
  const responseAt = startedAt + 25_000
  assert.equal(recoveryDeadline(startedAt, responseAt, 5), startedAt + 120_000)
  assert.equal(recoveryDeadline(startedAt, responseAt, 180), responseAt + 180_000)
  assert.equal(formatCountdown(180), '03:00')
})
