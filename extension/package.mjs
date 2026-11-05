/**
 * Reproducible, deliberately inert EXT-47 release-shell ZIP.
 *
 * Runtime allowlist reflects the current manifest, NOT manifest.dev.json.
 * This does not activate the development background worker or permit pilot
 * distribution before Chrome/OAuth/permission acceptance.
 *
 * Requires only Node 22. Stored ZIP members have sorted names, fixed 1980
 * timestamps, no file mode/extra metadata, and deterministic SHA-256.
 */
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { APP_ORIGIN, ATS_HOSTS } from './config.js'

const ROOT = fileURLToPath(new URL('.', import.meta.url))
export const RELEASE_MEMBERS = Object.freeze(['manifest.json', 'popup.html'])
const RELEASE_PERMISSIONS = ['storage', 'activeTab', 'scripting']
const RELEASE_HOSTS = [...ATS_HOSTS.map(host => 'https://' + host + '/*'), APP_ORIGIN + '/*']
const FORBIDDEN = /localhost|127\.0\.0\.1|manifest\.dev\.json|popup\.dev\.html|(?:-----BEGIN [^-]*PRIVATE KEY-----)|(?:gh[pousr]_[A-Za-z0-9]{20,})|(?:sk-[A-Za-z0-9]{20,})|(?:Bearer\s+[A-Za-z0-9._-]{12,})/i

function assertReleaseManifest(manifest) {
  if (!manifest || manifest.manifest_version !== 3 ||
      !/^[0-9]+\.[0-9]+\.[0-9]+$/.test(manifest.version || '') ||
      manifest.action?.default_popup !== 'popup.html' ||
      !Array.isArray(manifest.permissions) ||
      JSON.stringify(manifest.permissions) !== JSON.stringify(RELEASE_PERMISSIONS) ||
      JSON.stringify(manifest.optional_host_permissions) !== JSON.stringify(RELEASE_HOSTS) ||
      manifest.host_permissions !== undefined ||
      manifest.background !== undefined ||
      manifest.content_scripts !== undefined ||
      manifest.externally_connectable !== undefined ||
      manifest.web_accessible_resources !== undefined ||
      manifest.chrome_url_overrides !== undefined) {
    throw new Error('Release manifest violates the inert-shell or exact-permission contract')
  }
}

function assertSafeMember(name, data) {
  const value = data.toString('utf8')
  if (FORBIDDEN.test(value)) throw new Error('Forbidden development host, filename or secret in ' + name)
  if (name === 'popup.html' && (
    !/<main>/.test(value) ||
    !/Not connected yet/.test(value) ||
    /<script\b|<iframe\b|<object\b|<embed\b|on(?:load|click|error)\s*=|javascript:|<link\b[^>]+https?:/i.test(value)
  )) {
    throw new Error('Release popup must remain script-free and visibly disconnected')
  }
}

function crc32(bytes) {
  let crc = 0xffffffff
  for (const byte of bytes) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0)
    }
  }
  return (crc ^ 0xffffffff) >>> 0
}

/** ZIP method 0 (STORE) avoids platform-specific compressor metadata. */
function storedZip(entries) {
  const local = []
  const central = []
  let offset = 0
  for (const { name, data } of entries) {
    if (!RELEASE_MEMBERS.includes(name) || name.includes('/') || name.includes('\\')) {
      throw new Error('ZIP path is outside the runtime allowlist')
    }
    const filename = Buffer.from(name, 'utf8')
    const checksum = crc32(data)
    const localHeader = Buffer.alloc(30)
    localHeader.writeUInt32LE(0x04034b50, 0)
    localHeader.writeUInt16LE(20, 4) // version needed
    localHeader.writeUInt16LE(0, 8) // no compression
    localHeader.writeUInt16LE(0x21, 12) // 1980-01-01, 00:00:00
    localHeader.writeUInt32LE(checksum, 14)
    localHeader.writeUInt32LE(data.length, 18)
    localHeader.writeUInt32LE(data.length, 22)
    localHeader.writeUInt16LE(filename.length, 26)
    local.push(localHeader, filename, data)

    const centralHeader = Buffer.alloc(46)
    centralHeader.writeUInt32LE(0x02014b50, 0)
    centralHeader.writeUInt16LE(20, 4)
    centralHeader.writeUInt16LE(20, 6)
    centralHeader.writeUInt16LE(0x21, 14) // 1980-01-01
    centralHeader.writeUInt32LE(checksum, 16)
    centralHeader.writeUInt32LE(data.length, 20)
    centralHeader.writeUInt32LE(data.length, 24)
    centralHeader.writeUInt16LE(filename.length, 28)
    centralHeader.writeUInt32LE(offset, 42)
    central.push(centralHeader, filename)
    offset += localHeader.length + filename.length + data.length
  }
  const centralSize = central.reduce((size, part) => size + part.length, 0)
  const end = Buffer.alloc(22)
  end.writeUInt32LE(0x06054b50, 0)
  end.writeUInt16LE(entries.length, 8)
  end.writeUInt16LE(entries.length, 10)
  end.writeUInt32LE(centralSize, 12)
  end.writeUInt32LE(offset, 16)
  return Buffer.concat([...local, ...central, end])
}

export async function buildPilot({ sourceDir = ROOT, outputDir = path.join(ROOT, 'dist') } = {}) {
  // Check all source members before creating any output, including symlink safety.
  const entries = []
  for (const name of [...RELEASE_MEMBERS].sort()) {
    const filename = path.join(sourceDir, name)
    const stat = await fs.lstat(filename)
    if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error('Release ZIP member must be a regular local file: ' + name)
    }
    const data = await fs.readFile(filename)
    assertSafeMember(name, data)
    entries.push({ name, data })
  }
  const manifest = JSON.parse(entries.find(entry => entry.name === 'manifest.json').data.toString('utf8'))
  assertReleaseManifest(manifest)

  const archive = storedZip(entries)
  const sha256 = createHash('sha256').update(archive).digest('hex')
  const name = 'jobgrid-pilot-v' + manifest.version + '.zip'
  await fs.mkdir(outputDir, { recursive: true })
  const file = path.join(outputDir, name)
  await fs.writeFile(file, archive)
  await fs.writeFile(file + '.sha256', sha256 + '  ' + name + '\n')
  return { file, name, version: manifest.version, sha256, members: entries.map(entry => entry.name) }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const outputDir = process.argv[2] ? path.resolve(process.argv[2]) : undefined
    const result = await buildPilot(outputDir ? { outputDir } : {})
    console.log('EXT-47 inactive pilot ZIP: ' + result.name)
    console.log('SHA-256: ' + result.sha256)
    console.log('Members: ' + result.members.join(', '))
    console.log('Not for store upload or real account use before acceptance')
  } catch (error) {
    console.error('EXT-47 packaging rejected: ' + error.message)
    process.exitCode = 1
  }
}
