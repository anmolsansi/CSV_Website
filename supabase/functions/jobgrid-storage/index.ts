import 'jsr:@supabase/functions-js/edge-runtime.d.ts'
import { createClient } from 'npm:@supabase/supabase-js@2'

const BUCKET = 'jobgrid-documents'
const TOKEN_HEADER = 'x-jobgrid-storage-token'
const PREFIX = 'jobgrid-storage-v1:'
const CANARY_KEY = '_ops/c09-durability-canary.txt'
const CANARY_TEXT = 'jobgrid-c09-durability-canary-v1\n'
const encoder = new TextEncoder()

function hex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer)).map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function expectedToken(): Promise<string> {
  const dbUrl = Deno.env.get('SUPABASE_DB_URL')
  if (!dbUrl) throw new Error('database secret unavailable')
  const parsed = new URL(dbUrl)
  const password = decodeURIComponent(parsed.password || '')
  if (!password) throw new Error('database password unavailable')
  return hex(await crypto.subtle.digest('SHA-256', encoder.encode(PREFIX + password)))
}

function safeKey(value: string | null): string | null {
  if (!value) return null
  const normalized = value.replaceAll('\\', '/').trim()
  const parts = normalized.split('/')
  if (!normalized || normalized.startsWith('/') || parts.some((p) => !p || p === '.' || p === '..')) return null
  return normalized
}

function secureEqual(a: string, b: string): boolean {
  const aa = encoder.encode(a)
  const bb = encoder.encode(b)
  if (aa.length !== bb.length) return false
  let diff = 0
  for (let i = 0; i < aa.length; i++) diff |= aa[i] ^ bb[i]
  return diff === 0
}

async function authorized(req: Request): Promise<boolean> {
  const actual = req.headers.get(TOKEN_HEADER) || ''
  const expected = await expectedToken()
  return secureEqual(actual, expected)
}

function adminClient() {
  const url = Deno.env.get('SUPABASE_URL')!
  const secrets = JSON.parse(Deno.env.get('SUPABASE_SECRET_KEYS') || '{}')
  const key = secrets['default'] || Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')
  if (!key) throw new Error('supabase secret unavailable')
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } })
}

async function objectInfo(client: ReturnType<typeof adminClient>, key: string) {
  const slash = key.lastIndexOf('/')
  const folder = slash >= 0 ? key.slice(0, slash) : ''
  const name = slash >= 0 ? key.slice(slash + 1) : key
  const { data, error } = await client.storage.from(BUCKET).list(folder, { limit: 100, search: name })
  if (error) throw error
  const item = (data || []).find((entry: any) => entry.name === name)
  if (!item) return null
  return { size: Number(item?.metadata?.size || 0), updated_at: item.updated_at || item.created_at || null }
}

async function listRecursive(client: ReturnType<typeof adminClient>, prefix: string, limit: number) {
  const items: any[] = []
  const queue: string[] = [prefix]
  while (queue.length && items.length < limit) {
    const folder = queue.shift() || ''
    const { data, error } = await client.storage.from(BUCKET).list(folder, { limit: 1000 })
    if (error) throw error
    for (const entry of data || []) {
      const key = folder ? `${folder}/${entry.name}` : entry.name
      if (entry.id) {
        items.push({ key, size_bytes: Number(entry?.metadata?.size || 0), modified_at: entry.updated_at || entry.created_at || null })
        if (items.length >= limit) break
      } else {
        queue.push(key)
      }
    }
  }
  return items
}

async function durabilityCanary() {
  const client = adminClient()
  const expected = encoder.encode(CANARY_TEXT)
  const info = await objectInfo(client, CANARY_KEY)
  if (!info) {
    const { error } = await client.storage.from(BUCKET).upload(CANARY_KEY, expected, {
      contentType: 'text/plain', cacheControl: '0', upsert: false,
    })
    if (error) throw error
    return { status: 'ready', state: 'created', size_bytes: expected.length }
  }

  const { data, error } = await client.storage.from(BUCKET).download(CANARY_KEY)
  if (error || !data) throw error || new Error('canary missing')
  const bytes = new Uint8Array(await data.arrayBuffer())
  if (bytes.length !== expected.length) throw new Error('canary size mismatch')
  for (let i = 0; i < expected.length; i++) {
    if (bytes[i] !== expected[i]) throw new Error('canary content mismatch')
  }
  return { status: 'ready', state: 'verified', size_bytes: bytes.length }
}

Deno.serve(async (req: Request) => {
  try {
    const url = new URL(req.url)
    const action = url.searchParams.get('action')

    // Public, synthetic-only operational canary. It can touch exactly one fixed
    // object and cannot list, read, write, move, or delete any user object.
    if (action === 'c09-canary' && req.method === 'GET') {
      return Response.json(await durabilityCanary(), { headers: { 'cache-control': 'no-store' } })
    }

    if (!(await authorized(req))) return new Response('unauthorized', { status: 401 })
    const client = adminClient()

    if (action === 'ready') {
      const { error } = await client.storage.from(BUCKET).list('', { limit: 1 })
      if (error) throw error
      return Response.json({ status: 'ready' }, { headers: { 'cache-control': 'no-store' } })
    }
    if (action === 'list' && req.method === 'GET') {
      const prefixRaw = url.searchParams.get('prefix') || ''
      const prefix = prefixRaw ? safeKey(prefixRaw) : ''
      if (prefixRaw && !prefix) return new Response('invalid key', { status: 400 })
      const requested = Number(url.searchParams.get('limit') || '500')
      const limit = Math.max(1, Math.min(Number.isFinite(requested) ? requested : 500, 500))
      return Response.json({ items: await listRecursive(client, prefix || '', limit) }, { headers: { 'cache-control': 'no-store' } })
    }
    if (action === 'move' && req.method === 'POST') {
      const payload = await req.json()
      const source = safeKey(String(payload?.source || ''))
      const target = safeKey(String(payload?.target || ''))
      if (!source || !target) return new Response('invalid key', { status: 400 })
      const { error } = await client.storage.from(BUCKET).move(source, target)
      if (error) throw error
      return new Response(null, { status: 204 })
    }

    const key = safeKey(url.searchParams.get('key'))
    if (!key) return new Response('invalid key', { status: 400 })
    if (req.method === 'HEAD') {
      const info = await objectInfo(client, key)
      if (!info) return new Response(null, { status: 404 })
      const headers = new Headers({ 'x-object-size': String(info.size), 'cache-control': 'no-store' })
      if (info.updated_at) headers.set('last-modified', new Date(info.updated_at).toUTCString())
      return new Response(null, { status: 200, headers })
    }
    if (req.method === 'GET') {
      const { data, error } = await client.storage.from(BUCKET).download(key)
      if (error || !data) return new Response(null, { status: 404 })
      return new Response(await data.arrayBuffer(), { status: 200, headers: { 'content-type': 'application/octet-stream', 'cache-control': 'private, no-store' } })
    }
    if (req.method === 'PUT') {
      const body = new Uint8Array(await req.arrayBuffer())
      const { error } = await client.storage.from(BUCKET).upload(key, body, { contentType: 'application/octet-stream', cacheControl: '0', upsert: false })
      if (error) throw error
      return new Response(null, { status: 201 })
    }
    if (req.method === 'DELETE') {
      const { error } = await client.storage.from(BUCKET).remove([key])
      if (error) throw error
      return new Response(null, { status: 204 })
    }
    return new Response('method not allowed', { status: 405 })
  } catch (error) {
    console.error('jobgrid-storage error', error instanceof Error ? error.name : 'unknown')
    return new Response('storage unavailable', { status: 503 })
  }
})
