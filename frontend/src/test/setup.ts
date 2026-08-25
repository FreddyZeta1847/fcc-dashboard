/*
 * setup.ts
 * Vitest setup file — extends `expect` with jest-dom's DOM matchers
 * (toBeInTheDocument, etc.) for every test file, and cleans up mounted
 * components between tests.
 */
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})
