import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Self-hosted fonts (bundled, no runtime CDN — stays offline/private):
// SN Pro (a clean humanist sans) for the display/hero type, Hanken Grotesk for
// the UI. Only the two display weights we actually use are pulled in.
import '@fontsource/sn-pro/400.css'
import '@fontsource/sn-pro/600.css'
import '@fontsource-variable/hanken-grotesk'
import '@fontsource-variable/newsreader'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './auth/AuthContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)
