import assert from 'node:assert/strict'
import { test } from 'node:test'
import { existsSync, readFileSync } from 'node:fs'
import { APP_ORIGIN, ATS_HOSTS } from '../config.js'

const read = (name) => JSON.parse(readFileSync(new URL(`../${name}`, import.meta.url), 'utf8'))
const release = read('manifest.json')
const development = read('manifest.dev.json')
const popup = readFileSync(new URL('../popup.html', import.meta.url), 'utf8')

// ext_02_case_01 (structural checks; unpacked Chrome load is separate manual acceptance)
test('MV3 metadata points to the real, script-free, named popup', () => {
  assert.equal(release.manifest_version, 3)
  assert.match(release.name, /JobGrid/)
  assert.match(release.action.default_title, /JobGrid/)
  assert.equal(release.action.default_popup, 'popup.html')
  assert.ok(existsSync(new URL('../popup.html', import.meta.url)))
  assert.match(popup, /<main>/)
  assert.match(popup, /role="status"/)
  assert.match(popup, /Not connected yet/)
  assert.doesNotMatch(popup, /<script\b|onload=|onclick=|<iframe\b/i)
  assert.equal(release.background, undefined)
  assert.equal(release.content_scripts, undefined)
})

// ext_02_case_02
test('release permissions and exact optional hosts are strictly limited', () => {
  assert.deepEqual(release.permissions, ['storage', 'activeTab', 'scripting'])
  assert.equal(release.host_permissions, undefined)
  assert.equal(release.externally_connectable, undefined)
  const hosts = [...ATS_HOSTS.map((host) => `https://${host}/*`), `${APP_ORIGIN}/*`]
  assert.deepEqual(release.optional_host_permissions, hosts)
  assert.equal(release.optional_host_permissions.length, 4)
  assert.doesNotMatch(JSON.stringify(release), /localhost|127\.0\.0\.1|<all_urls>|"tabs"|"history"|"cookies"|\*\.vercel/i)
  assert.deepEqual(development.permissions, release.permissions)
  assert.deepEqual(development.optional_host_permissions, [
    ...ATS_HOSTS.map((host) => `https://${host}/*`), 'http://localhost:5173/*',
  ])
  assert.equal(development.host_permissions, undefined)
  assert.equal(development.content_scripts, undefined)
})

// ext_02_case_03
test('install and popup load cannot trigger a network call or a visit write', () => {
  assert.equal(release.background, undefined)
  assert.equal(release.content_scripts, undefined)
  assert.equal(release.chrome_url_overrides, undefined)
  assert.equal(release.web_accessible_resources, undefined)
  assert.doesNotMatch(popup, /\b(fetch|XMLHttpRequest|sendBeacon|chrome\.runtime|serviceWorker)\b/)
  assert.doesNotMatch(popup, /<script\b|<link\b[^>]*href="https?:/i)
  assert.equal(read('package.json').private, true)
  assert.equal(read('package.json').type, 'module')
  assert.deepEqual(read('package.json').dependencies ?? {}, {})
})
