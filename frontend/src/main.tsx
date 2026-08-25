/*
 * main.tsx
 * Application entry point — mounts <App /> into the DOM, wrapped in a
 * TanStack Query client provider (every data-fetching hook in this app
 * depends on this provider existing above it in the tree).
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
