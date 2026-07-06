import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Self-hosted variable fonts (bundled, no runtime CDN — stays offline/private):
// Fraunces (a warm editorial serif) for hero moments, Hanken Grotesk for the UI.
import '@fontsource-variable/fraunces'
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
