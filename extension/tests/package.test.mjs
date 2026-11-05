import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { test } from 'node:test'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildPilot, RELEASE_MEMBERS } from '../package.mjs'

const sourceDir = fileURLToPath(new URL('../', import.meta.url))
async function temp(t) {
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'jobgrid-ext47-'))
  t.after(async () => { await fs.rm(folder, { recursive: true, force: true }) })
  return folder
}
function unzip(args) {
  const result = spawnSync('unzip', args, { encoding: 'utf8' })
  assert.equal(result.status, 0, 'unzip validation failed: ' + (result.stderr || result.stdout))
  return result.stdout
}
async function sourceCopy(folder) {
  const source = path.join(folder, 'source')
  await fs.mkdir(source, { recursive: true })
  for (const member of RELEASE_MEMBERS) {
    await fs.copyFile(path.join(sourceDir, member), path.join(source, member))
  }
  return source
}

test('EXT-47 identical sources produce a byte-for-byte versioned allowlist ZIP and SHA-256', async t => {
  const folder = await temp(t)
  const first = await buildPilot({ outputDir: path.join(folder, 'a') })
  const second = await buildPilot({ outputDir: path.join(folder, 'b') })
  assert.equal(first.name, 'jobgrid-pilot-v' + first.version + '.zip')
  assert.deepEqual(first.members, [...RELEASE_MEMBERS].sort())
  assert.equal(first.sha256, second.sha256)
  assert.deepEqual(await fs.readFile(first.file), await fs.readFile(second.file))
  const digest = createHash('sha256').update(await fs.readFile(first.file)).digest('hex')
  assert.equal(first.sha256, digest)
  assert.equal(await fs.readFile(first.file + '.sha256', 'utf8'),
    digest + '  ' + first.name + '\n')

  // Independent ZIP decoder validates the central directory and member paths.
  const members = unzip(['-Z', '-1', first.file]).trim().split('\n')
  assert.deepEqual(members, [...RELEASE_MEMBERS].sort())
  unzip(['-t', first.file])
  const unpacked = path.join(folder, 'unpacked')
  unzip(['-q', first.file, '-d', unpacked])
  const manifest = JSON.parse(await fs.readFile(path.join(unpacked, 'manifest.json'), 'utf8'))
  assert.equal(manifest.version, first.version)
  assert.equal(manifest.action.default_popup, 'popup.html')
  assert.equal(manifest.background, undefined)
  assert.equal(manifest.content_scripts, undefined)
  assert.equal(manifest.host_permissions, undefined)
  assert.match(await fs.readFile(path.join(unpacked, 'popup.html'), 'utf8'), /Not connected yet/)
})

test('EXT-47 release ZIP excludes fixture hosts, profile data and executable code', async t => {
  const folder = await temp(t)
  const archive = (await buildPilot({ outputDir: folder })).file
  const bytes = await fs.readFile(archive)
  const text = bytes.toString('utf8')
  assert.doesNotMatch(text, /localhost|127\.0\.0\.1|manifest\.dev|popup\.dev|TEST_AUTH|cookie|Bearer\s|private key/i)
  assert.doesNotMatch(text, /<script\b|eval\s*\(|new\s+Function\s*\(|<iframe\b/i)
  const names = unzip(['-Z', '-1', archive]).trim().split('\n')
  assert.deepEqual(names, ['manifest.json', 'popup.html'])
})

test('EXT-47 fails closed before creating a ZIP on permission, secret or active-code changes', async t => {
  const folder = await temp(t)
  const source = await sourceCopy(folder)
  const outputDir = path.join(folder, 'output')
  const manifestPath = path.join(source, 'manifest.json')
  const popupPath = path.join(source, 'popup.html')
  const originalManifest = await fs.readFile(manifestPath, 'utf8')
  const originalPopup = await fs.readFile(popupPath, 'utf8')

  const bad = JSON.parse(originalManifest)
  bad.host_permissions = ['<all_urls>']
  await fs.writeFile(manifestPath, JSON.stringify(bad))
  await assert.rejects(() => buildPilot({ sourceDir: source, outputDir }), /permission contract/)
  await fs.writeFile(manifestPath, originalManifest)

  const local = JSON.parse(originalManifest)
  local.optional_host_permissions.push('http://localhost:5173/*')
  await fs.writeFile(manifestPath, JSON.stringify(local))
  await assert.rejects(() => buildPilot({ sourceDir: source, outputDir }), /Forbidden|permission contract/)
  await fs.writeFile(manifestPath, originalManifest)

  await fs.writeFile(popupPath, originalPopup + '\n<script src="https://example.test/a.js"></script>')
  await assert.rejects(() => buildPilot({ sourceDir: source, outputDir }), /script-free/)
  await fs.writeFile(popupPath, originalPopup + '\n<!-- sk-123456789012345678901234 -->')
  await assert.rejects(() => buildPilot({ sourceDir: source, outputDir }), /Forbidden/)
  await assert.rejects(fs.access(outputDir), { code: 'ENOENT' })
})

test('EXT-47 rejects symlinked runtime members outside its source directory', async t => {
  const folder = await temp(t)
  const source = await sourceCopy(folder)
  const popup = path.join(source, 'popup.html')
  await fs.unlink(popup)
  await fs.symlink(path.join(sourceDir, 'popup.html'), popup)
  await assert.rejects(
    () => buildPilot({ sourceDir: source, outputDir: path.join(folder, 'out') }),
    /regular local file/,
  )
})


test('EXT-47 enforces Chrome version limits before creating output', async t => {
  const folder = await temp(t)
  const source = await sourceCopy(folder)
  const manifestPath = path.join(source, 'manifest.json')
  const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'))
  for (const version of ['0.0.0', '01.2.3', '1.02.3', '65536.0.1', '1.2.999999', '1.2.3/unsafe']) {
    await fs.writeFile(manifestPath, JSON.stringify({ ...manifest, version }))
    const outputDir = path.join(folder, 'rejected')
    await assert.rejects(() => buildPilot({ sourceDir: source, outputDir }), /permission contract/)
    await assert.rejects(fs.access(outputDir), { code: 'ENOENT' })
  }
  for (const version of ['0.0.1', '65535.65535.65535']) {
    await fs.writeFile(manifestPath, JSON.stringify({ ...manifest, version }))
    const result = await buildPilot({ sourceDir: source, outputDir: path.join(folder, 'valid') })
    assert.equal(result.version, version)
    assert.equal(result.name, 'jobgrid-pilot-v' + version + '.zip')
  }
})


test('EXT-47 rejects additional manifest activation surfaces and HTML handlers', async t => {
  const folder = await temp(t)
  const source = await sourceCopy(folder)
  const manifestPath = path.join(source, 'manifest.json')
  const popupPath = path.join(source, 'popup.html')
  const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'))
  const popup = await fs.readFile(popupPath, 'utf8')
  const outputDir = path.join(folder, 'rejected')
  for (const extra of [
    { devtools_page: 'popup.html' },
    { sandbox: { pages: ['popup.html'] } },
    { options_page: 'popup.html' },
    { action: { ...manifest.action, default_icon: 'missing.png' } },
  ]) {
    await fs.writeFile(manifestPath, JSON.stringify({ ...manifest, ...extra }))
    await assert.rejects(() => buildPilot({ sourceDir: source, outputDir }), /permission contract/)
    await assert.rejects(fs.access(outputDir), { code: 'ENOENT' })
  }
  await fs.writeFile(manifestPath, JSON.stringify(manifest))
  for (const handler of ['onfocus', 'onmouseover', 'onanimationstart', 'ONPOINTERENTER']) {
    await fs.writeFile(popupPath, popup.replace('<main>', '<main ' + handler + '="alert(1)">'))
    await assert.rejects(() => buildPilot({ sourceDir: source, outputDir }), /script-free/)
    await assert.rejects(fs.access(outputDir), { code: 'ENOENT' })
  }
})
