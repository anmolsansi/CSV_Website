import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { APP_ORIGIN, ATS_HOSTS, PROTOCOL_VERSION, isAllowedAppOrigin, parseTrustedOrigin } from '../config.js'

// ext_01_case_01
test('synthetic HTTPS origin is exact and suffix spoofing fails', () => {
  const trusted = parseTrustedOrigin('https://jobgrid.example.test')
  assert.equal(trusted, 'https://jobgrid.example.test')
  assert.equal(isAllowedAppOrigin(trusted, trusted), true)
  assert.equal(isAllowedAppOrigin('https://jobgrid.example.test.attacker.test', trusted), false)
  assert.equal(isAllowedAppOrigin('https://csv-website-steel.vercel.app.attacker.test'), false)
})

// ext_01_case_02
test('rejects userinfo, path, wildcard, query, credentials and unsafe schemes', () => {
  const rejected = [
    'https://user:pass@jobgrid.example.test',
    'https://jobgrid.example.test/login',
    'https://*.example.test',
    'https://jobgrid.example.test?next=/',
    'https://jobgrid.example.test/#a',
    'http://jobgrid.example.test',
    'http://localhost:5173',
    'https://jobgrid.example.test/',
    'https://jobgrid.example.test.evil.test',
    'javascript:alert(1)',
    'https://jobgrid.example.test:443',
    'https://jobgrid.example.test.',
  ]
  for (const input of rejected) {
    if (input.endsWith('.evil.test') || input.endsWith('.attacker.test')) {
      assert.equal(isAllowedAppOrigin(input, 'https://jobgrid.example.test'), false)
    } else {
      assert.throws(() => parseTrustedOrigin(input), { name: 'TypeError' }, input)
    }
  }
  assert.equal(parseTrustedOrigin('http://localhost:5173', { allowLocal: true }), 'http://localhost:5173')
  assert.throws(() => parseTrustedOrigin('http://attacker.test', { allowLocal: true }))
  assert.equal(APP_ORIGIN, 'https://csv-website-steel.vercel.app')
  assert.equal(PROTOCOL_VERSION, 1)
  assert.deepEqual([...ATS_HOSTS], ['boards.greenhouse.io', 'job-boards.greenhouse.io', 'jobs.lever.co'])
  const source = readFileSync(new URL('../config.js', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /https?:\/\/[^\s"']*(?:@|secret|token|password)/i)
  assert.doesNotMatch(APP_ORIGIN, /localhost|127\.0\.0\.1/i)
})

// ext_01_case_03
test('deployment is identified but no deployed user or extension session is asserted verified', () => {
  const readme = readFileSync(new URL('../README.md', import.meta.url), 'utf8')
  assert.match(readme, /Live Chrome\/OAuth acceptance:\s*NOT VERIFIED/i)
  assert.match(readme, /Selected release frontend origin:[^\n]*https:\/\/csv-website-steel\.vercel\.app/i)
  assert.match(readme, /Keep a JobGrid tab open/i)
})
