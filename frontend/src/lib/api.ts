// Tiny API client. All requests go through the /api prefix, which the Vite dev
// server proxies to the FastAPI backend (see vite.config.ts). On the home server
// the same /api path is routed to the backend by the LAN-only Caddy proxy.

export interface Health {
  status: string
  mode: string
  demo: boolean
}

export async function getHealth(): Promise<Health> {
  const res = await fetch('/api/health')
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.status}`)
  }
  return res.json()
}
