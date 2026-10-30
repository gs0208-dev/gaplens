import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter } from 'react-router'

import { App } from '@/app/App'
import { AppProviders } from '@/app/providers'
import { routes } from '@/app/routes'

import './styles/index.css'

const container = document.getElementById('root')
if (container === null) {
  throw new Error('The page has no #root element to render into.')
}

createRoot(container).render(
  <StrictMode>
    <AppProviders>
      <App router={createBrowserRouter(routes)} />
    </AppProviders>
  </StrictMode>,
)
