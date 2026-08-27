/*
 * proxy-coverage.test.ts
 * Guards a gap that no other test can see: every backend route the client
 * fetches must also appear in vite.config.ts's dev-server proxy map.
 *
 * The production build serves the frontend and the API from one origin, so a
 * missing proxy entry is invisible there — the request just resolves. It only
 * breaks under `npm run dev`, where Vite serves the page and the backend is a
 * separate process: an unproxied path hits Vite instead of the API and the
 * feature silently degrades. That is exactly how `/fcc` was missed when
 * `GET /fcc/catalog` was added, and no component or backend test could catch
 * it, because both halves were individually correct.
 *
 * Deliberately a text-level check of the two real files rather than importing
 * the Vite config: importing it pulls in the plugin chain, and the thing worth
 * asserting is what a human will actually read in the file.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Resolved from the Vitest root (frontend/), not from import.meta.url: under
// the jsdom environment import.meta.url is an http:// URL, so fileURLToPath
// rejects it with "The URL must be of scheme file".
const clientSource = readFileSync(resolve(process.cwd(), 'src/api/client.ts'), 'utf-8')
const viteConfigSource = readFileSync(resolve(process.cwd(), 'vite.config.ts'), 'utf-8')

/** Every absolute path passed to fetch(), quoted or in a template literal. */
function fetchedPaths(source: string): string[] {
  const matches = source.matchAll(/fetch\(\s*['"`](\/[^'"`?]*)/g)
  return [...new Set([...matches].map((m) => m[1]))]
}

/** The route prefixes declared in the dev proxy map. */
function proxiedPrefixes(source: string): string[] {
  const proxyBlock = source.match(/proxy:\s*\{([\s\S]*?)\n\s*\},/)
  if (!proxyBlock) {
    throw new Error('could not locate the proxy block in vite.config.ts')
  }
  const matches = proxyBlock[1].matchAll(/['"`](\/[^'"`]*)['"`]\s*:/g)
  return [...new Set([...matches].map((m) => m[1]))]
}

/** First path segment: '/fcc/catalog' -> '/fcc'. */
function rootSegment(path: string): string {
  return `/${path.split('/').filter(Boolean)[0] ?? ''}`
}

describe('dev proxy covers every fetched route', () => {
  it('finds the routes the client fetches', () => {
    const paths = fetchedPaths(clientSource)
    // Sanity-check the extraction itself, so a regex that silently stops
    // matching cannot make this suite pass vacuously.
    expect(paths.length).toBeGreaterThan(3)
    expect(paths).toContain('/fcc/catalog')
  })

  it('finds the prefixes the dev proxy declares', () => {
    expect(proxiedPrefixes(viteConfigSource).length).toBeGreaterThan(3)
  })

  it('proxies every route the client fetches', () => {
    const proxied = new Set(proxiedPrefixes(viteConfigSource).map(rootSegment))
    const missing = fetchedPaths(clientSource)
      .map(rootSegment)
      .filter((segment) => !proxied.has(segment))

    expect(missing).toEqual([])
  })
})
