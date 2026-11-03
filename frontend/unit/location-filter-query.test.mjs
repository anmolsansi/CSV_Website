import test from 'node:test'
import assert from 'node:assert/strict'
import { dashboardNavigationState, serializeDashboardQuery, savedViewSearch } from '../src/api/queryParams.js'

test('country and city survive URL, saved-view and export query serialization', () => {
  const initial = dashboardNavigationState(
    '?location_country=United%20States&location_city=New%20York%20City&group_by=location_country',
    { sortBy: 'created_at', sortDir: 'desc', page: 1, pageSize: 50 }
  )
  assert.equal(initial.filters.locationCountry, 'United States')
  assert.equal(initial.filters.locationCity, 'New York City')
  assert.equal(initial.filters.groupBy, 'location_country')
  const serialized = serializeDashboardQuery({ ...initial.sort, ...initial.filters })
  assert.equal(serialized.location_country, 'United States')
  assert.equal(serialized.location_city, 'New York City')
  assert.equal(serialized.group_by, 'location_country')
  const saved = savedViewSearch('job_links', { ...initial.sort, ...initial.filters })
  assert.equal(saved.get('location_country'), 'United States')
  assert.equal(saved.get('location_city'), 'New York City')
})

