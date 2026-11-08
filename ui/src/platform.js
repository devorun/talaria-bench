// The only surface-specific piece: how to reach the backend and how to notify.
// Desktop sets ctx.rest; the dashboard sets SDK.fetchJSON. Every call resolves to a JSON object;
// transport failures become { ok: false, error } so views have one error path.
let platform = null

export function setPlatform(p) {
  platform = p
}

export function surface() {
  return platform ? platform.kind : 'unknown'
}

export async function api(path, { method = 'GET', body } = {}) {
  if (!platform) return { ok: false, error: 'not connected' }
  try {
    const data = await platform.request(path, method, body)
    return data && typeof data === 'object' ? data : { ok: false, error: 'empty answer' }
  } catch (err) {
    const msg = (err && (err.message || err.detail)) || String(err)
    return { ok: false, error: msg }
  }
}

export function notify(message, kind = 'info') {
  if (platform && platform.notify) platform.notify(message, kind)
}
