// A small 3D picture of a robot for the gallery card: the same Stage as the 3D viewer, drawn once in a hidden
// box and kept as a PNG. Used for robots without a pre-rendered thumbnail (the user's own).
import { api } from './platform.js'
import { Stage } from './stage.js'

const cache = new Map()       // robot key -> PNG data URL, or null when 3D is not available here
let queue = Promise.resolve() // one hidden WebGL context at a time

const keyOf = (robot) => `${robot.name}|${robot.servos}|${robot.mass_g}|${robot.family}`
const settle = () => new Promise((done) => { requestAnimationFrame(() => done()); setTimeout(done, 80) })

async function draw(robot, key) {
  if (cache.has(key)) return cache.get(key)
  let host = null
  let stage = null
  try {
    const r = await api(`/robots/${robot.name}`)
    if (!r || !r.ok) throw new Error('no robot data')
    const shown = r.showcase || r.render
    host = document.createElement('div')
    host.style.cssText = 'position:fixed;left:-10000px;top:0;width:360px;height:270px;pointer-events:none'
    document.body.appendChild(host)
    stage = new Stage(host, { interactive: false, dark: false, preserve: true })
    stage.follow = false
    stage.setRobot(shown.parts, r.look || {})
    stage.setPose(shown.parts.map((p) => p.pose))
    stage.setMeta({ mark: 'front' })
    stage.frame(true, { distance: 1.75, azimuth: [0.82, 0.42, 0.7] })
    for (let i = 0; i < 6; i++) await settle()
    stage.renderNow()
    const url = stage.renderer.domElement.toDataURL('image/png')
    cache.set(key, url)
    return url
  } catch (err) {
    cache.set(key, null)
    return null
  } finally {
    if (stage) stage.dispose()
    if (host) host.remove()
  }
}

export function robotThumb(robot) {
  const key = keyOf(robot)
  if (cache.has(key)) return Promise.resolve(cache.get(key))
  const job = queue.then(() => draw(robot, key))
  queue = job.then(() => null, () => null)
  return job
}
