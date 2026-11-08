// Hermes Desktop: a full page plus a sidebar entry, talking to plugin_api.py through ctx.rest.
import { ROUTES_AREA, SIDEBAR_NAV_AREA, host } from '@hermes/plugin-sdk'
import { App } from './app.jsx'
import { setPlatform } from './platform.js'

export default {
  id: 'talaria-bench',
  name: 'Talaria Bench',
  register(ctx) {
    setPlatform({
      kind: 'desktop',
      request: (path, method, body) => ctx.rest(path, method === 'GET' ? undefined : { method, body, timeoutMs: 180000 }),
      notify: (message, kind) => host.notify({ kind: kind === 'error' ? 'error' : 'info', message }),
    })
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/talaria' }, render: () => <App /> },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/talaria', label: 'Talaria Bench', codicon: 'beaker' } },
    ])
  },
}
