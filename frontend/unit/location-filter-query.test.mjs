import test from 'node:test'
import assert from 'node:assert/strict'
import { dashboardNavigationState, serializeDashboardQuery, savedViewSearch } from '../src/api/queryParams.js'
import { defaultImportMapping } from '../src/api/imports.js'

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

test('Serper aliases map automatically and never override explicit canonical headers', () => {
  const aliases = defaultImportMapping(['url', 'country', 'city', 'job_location'])
  assert.deepEqual(aliases, {
    '0': 'url', '1': 'location_country', '2': 'location_city', '3': 'location_raw_extracted',
  })
  const canonical = defaultImportMapping(['url', 'country', 'location_country', 'city'])
  assert.deepEqual(canonical, { '0': 'url', '2': 'location_country', '3': 'location_city' })
})
