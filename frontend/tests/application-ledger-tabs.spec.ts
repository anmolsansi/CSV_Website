import { test, expect } from '@playwright/test'
import { applicationTabFromUrl, filtersForApplicationTab, applicationEmptyState } from '../src/utils/applicationLedgerViews.js'

test('AL-07: tab URL overrides saved filters and keeps ordinary facets', () => {
  expect(applicationTabFromUrl('?tab=all&applied_only=true', { appliedOnly: true })).toBe('all')
  expect(applicationTabFromUrl('?applied_only=true', { appliedOnly: true })).toBe('applied')
  expect(applicationTabFromUrl('?follow_up_due=true', { followUpDue: true })).toBe('followups')
  expect(applicationTabFromUrl('?tab=invalid', {})).toBe('all')
  const original = { status: 'interview', company: 'Example', dateAppliedFrom: '2026-11-01', followUpDue: true, appliedOnly: false }
  const applied = filtersForApplicationTab(original, 'applied')
  expect(applied).toMatchObject({
    status: 'interview', company: 'Example', dateAppliedFrom: '2026-11-01',
    appliedOnly: true, followUpDue: false,
  })
  expect(original.followUpDue).toBe(true)
  const followups = filtersForApplicationTab(applied, 'followups')
  expect(followups).toMatchObject({ appliedOnly: false, followUpDue: true })
})

test('AL-07: empty states distinguish no confirmed submissions and failed filters', () => {
  expect(applicationEmptyState('applied', false).title).toBe('No confirmed applications yet')
  expect(applicationEmptyState('followups', false).title).toBe('No follow-ups are due')
  expect(applicationEmptyState('all', false).title).toBe('No tracked jobs yet')
  expect(applicationEmptyState('applied', true).title).toBe('No matching applications')
})
