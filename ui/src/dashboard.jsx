// Web dashboard (`hermes dashboard`): one tab, same App, talking to plugin_api.py through SDK.fetchJSON.
import { App } from './app.jsx'
import { setPlatform } from './platform.js'

const SDK = window.__HERMES_PLUGIN_SDK__
const BASE = '/api/plugins/talaria-bench'

setPlatform({
  kind: 'dashboard',
  request: (path, method, body) => SDK.fetchJSON(BASE + path, method === 'GET' ? undefined : {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  }),
  notify: () => {},
})

window.__HERMES_PLUGINS__.register('talaria-bench', App)
