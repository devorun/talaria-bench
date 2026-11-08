// Dev-only entry (scripts/render_gallery.py): renders one robot with the same Stage as the 3D viewer, so
// the gallery images match the app (rounded parts, materials, shadows, light). Not part of the plugin.
import { Stage } from './stage.js'

let stage = null

window.renderRobot = async function renderRobot(data, { label = true } = {}) {
  const host = document.getElementById('stage')
  if (stage) stage.dispose()
  stage = new Stage(host, { interactive: false, dark: false, preserve: true })
  stage.follow = false
  stage.setRobot(data.parts, data.look || {})
  stage.setPose(data.parts.map((p) => p.pose))
  stage.frame(true, { distance: 1.75, azimuth: [0.82, 0.42, 0.7] })
  const info = document.getElementById('info')
  info.style.display = label ? 'block' : 'none'
  document.getElementById('name').textContent = data.title
  document.getElementById('sub').textContent = data.sub
  const badge = document.getElementById('badge')
  badge.style.display = data.look && data.look.badge ? 'inline-flex' : 'none'
  badge.textContent = (data.look && data.look.badge) || ''
  badge.style.background = (data.look && data.look.accent) || '#5b6cff'
  document.getElementById('sim').style.display = label ? 'block' : 'none'
  // Let shadows and the environment map settle for a few frames.
  for (let i = 0; i < 6; i++) await new Promise((r) => requestAnimationFrame(r))
  stage.renderNow()
  return true
}
