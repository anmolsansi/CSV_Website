import test from 'node:test'
import assert from 'node:assert/strict'
import { groupKey, groupLabel, groupTableRows } from '../src/components/grouping.js'

const row = (id, data) => ({ original: { id, data } })

test('company names group without case or surrounding whitespace', () => {
  const groups = groupTableRows([
    row(1, { company_guess: ' Acme ' }),
    row(2, { company_guess: 'acme' }),
    row(3, { company_guess: 'Beta' }),
    row(4, { company_guess: null }),
    row(5, { company_guess: '' }),
  ], 'company_guess')
  assert.deepEqual(groups.map((group) => [group.key, group.rows.length]), [
    ['acme', 2], ['beta', 1], ['', 2],
  ])
  assert.equal(groups[0].label, 'Acme')
  assert.equal(groups[2].label, 'Unknown')
})

test('USA status normalizes supported truthy and false values', () => {
  assert.equal(groupKey('YES', 'is_usa_role'), 'usa')
  assert.equal(groupKey('1', 'is_usa_role'), 'usa')
  assert.equal(groupKey('no', 'is_usa_role'), 'not usa')
  assert.equal(groupKey('0', 'is_usa_role'), 'not usa')
  assert.equal(groupLabel('true', 'is_usa_role'), 'USA')
  assert.equal(groupLabel('false', 'is_usa_role'), 'Not USA')
  assert.equal(groupLabel('N/A', 'is_usa_role'), 'Unknown')
})

test('grouping retains exact rejection reason combinations and row identity', () => {
  const first = row(10, { rejection_reasons: ' Visa required; 8 years experience ' })
  const second = row(11, { rejection_reasons: 'visa required; 8 years experience' })
  const groups = groupTableRows([first, second], 'rejection_reasons')
  assert.equal(groups.length, 1)
  assert.deepEqual(groups[0].rows, [first, second])
})

test('no grouping leaves the original row order unchanged', () => {
  const rows = [row(1, {}), row(2, {})]
  const groups = groupTableRows(rows, '')
  assert.equal(groups.length, 1)
  assert.equal(groups[0].rows, rows)
})
