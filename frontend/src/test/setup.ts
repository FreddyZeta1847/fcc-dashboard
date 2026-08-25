/*
 * setup.ts
 * Vitest setup file — extends `expect` with jest-dom's DOM matchers
 * (toBeInTheDocument, etc.) for every test file, and cleans up mounted
 * components between tests.
 *
 * Also polyfills `ResizeObserver`, which jsdom does not implement.
 * Recharts' <ResponsiveContainer> (first used in Task 3's VolumeChart)
 * needs it to size a percentage-width chart: without a real layout
 * engine, jsdom's getBoundingClientRect() always reports 0x0, so
 * ResponsiveContainer would wait forever for a resize event that never
 * comes and never render its children. This polyfill fires `observe()`
 * synchronously with a fixed, plausible content size, standing in for
 * "the browser laid this out at some nonzero size" so every current and
 * future Recharts-based component gets a working environment rather than
 * each test file inventing its own workaround.
 */
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

class ResizeObserverPolyfill implements ResizeObserver {
  private readonly callback: ResizeObserverCallback

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
  }

  observe(target: Element) {
    const entry = { target, contentRect: { width: 600, height: 300 } }
    this.callback([entry] as unknown as ResizeObserverEntry[], this)
  }

  unobserve() {}

  disconnect() {}
}

if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = ResizeObserverPolyfill
}

afterEach(() => {
  cleanup()
})
