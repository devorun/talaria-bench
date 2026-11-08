// The 3D stage: one three.js scene per viewer (and per gallery render). Robots arrive as MuJoCo geometry
// (metres, z up, x forward) and per-frame poses [x, y, z, qw, qx, qy, qz]; the stage turns that into soft,
// rounded parts on a shadowed floor, applies the spec's look (aluminium, OLED face, accent colour), draws
// the scene's course (striped ramp with its angle, hazard-striped bar, slippery tint, push arrow, payload),
// flashes the robot red at the moment it tips, and keeps the camera on the robot. No app markup is touched.
import {
  ACESFilmicToneMapping, ArrowHelper, Box3, BufferGeometry, CanvasTexture, CapsuleGeometry, CircleGeometry, Color,
  CylinderGeometry, DirectionalLight, EdgesGeometry, Group, HemisphereLight, Line, LineBasicMaterial,
  LineDashedMaterial, LineSegments, Matrix4, Mesh, MeshBasicMaterial, MeshPhysicalMaterial, MeshStandardMaterial,
  PCFSoftShadowMap, PerspectiveCamera, PlaneGeometry, PMREMGenerator, RepeatWrapping, Scene, ShaderMaterial,
  ShadowMaterial, SphereGeometry, Sprite, SpriteMaterial, SRGBColorSpace, Vector3, WebGLRenderer,
} from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'

const TIP_RED = new Color(0xff2d20)
const HAZARD_YELLOW = '#f5c518'
const RAMP_TONE = '#d9a441'

function luminance(css) {
  const m = /rgba?\(([^)]+)\)/.exec(css || '')
  if (!m) return 0.5
  const [r, g, b] = m[1].split(',').map((v) => parseFloat(v) / 255)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function isDarkTheme(el) {
  // Text colour tells the theme: light text = dark background.
  return luminance(getComputedStyle(el).color) > 0.5
}

function canvasTexture(w, h, draw) {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  draw(c.getContext('2d'), w, h)
  const t = new CanvasTexture(c)
  t.colorSpace = SRGBColorSpace
  t.anisotropy = 8
  return t
}

function hazardTexture() {
  const t = canvasTexture(256, 64, (g, w, h) => {
    g.fillStyle = '#16181c'
    g.fillRect(0, 0, w, h)
    g.fillStyle = HAZARD_YELLOW
    for (let x = -h; x < w + h; x += 48) {
      g.beginPath()
      g.moveTo(x, h); g.lineTo(x + 24, h); g.lineTo(x + 24 + h, 0); g.lineTo(x + h, 0)
      g.closePath(); g.fill()
    }
  })
  t.wrapS = t.wrapT = RepeatWrapping
  return t
}

function rampTexture(dark) {
  // Bands across the slope (perpendicular to the climb) so the incline reads at a glance.
  const t = canvasTexture(512, 128, (g, w, h) => {
    g.fillStyle = dark ? 'rgba(217,164,65,0.20)' : 'rgba(190,135,40,0.22)'
    g.fillRect(0, 0, w, h)
    for (let i = 0; i < 16; i++) {
      g.fillStyle = i % 2 ? 'rgba(217,164,65,0.42)' : 'rgba(217,164,65,0.10)'
      g.fillRect((i * w) / 16, 0, w / 16, h)
    }
    g.strokeStyle = RAMP_TONE
    g.lineWidth = 6
    g.strokeRect(3, 3, w - 6, h - 6)
  })
  return t
}

function textSprite(text, { color = '#ffffff', bg = 'rgba(20,22,28,0.82)', height = 0.016 } = {}) {
  const pad = 18
  const font = '600 64px system-ui, -apple-system, Segoe UI, sans-serif'
  const probe = document.createElement('canvas').getContext('2d')
  probe.font = font
  const w = Math.ceil(probe.measureText(text).width) + pad * 2
  const tex = canvasTexture(w, 96, (g, cw, ch) => {
    g.fillStyle = bg
    const r = 22
    g.beginPath()
    g.moveTo(r, 0); g.arcTo(cw, 0, cw, ch, r); g.arcTo(cw, ch, 0, ch, r); g.arcTo(0, ch, 0, 0, r); g.arcTo(0, 0, cw, 0, r)
    g.fill()
    g.font = font
    g.fillStyle = color
    g.textBaseline = 'middle'
    g.fillText(text, pad, ch / 2 + 3)
  })
  const sprite = new Sprite(new SpriteMaterial({ map: tex, depthTest: false, transparent: true }))
  sprite.scale.set((height * w) / 96, height, 1)
  sprite.renderOrder = 10
  return sprite
}

function oledTexture(accent) {
  return canvasTexture(256, 128, (g, w, h) => {
    g.fillStyle = '#020406'
    g.fillRect(0, 0, w, h)
    g.fillStyle = accent
    g.font = '700 30px ui-monospace, Menlo, monospace'
    g.textBaseline = 'top'
    g.fillText('HERMES', 18, 16)
    g.font = '500 20px ui-monospace, Menlo, monospace'
    g.fillText('waving...', 18, 58)
    g.fillRect(18, 96, 150, 6)
    g.globalAlpha = 0.35
    g.fillRect(168, 96, 70, 6)
  })
}

function partGeometry(shape, size) {
  if (shape === 'box') {
    const [x, y, z] = size
    const r = Math.min(x, y, z) * 0.22
    return new RoundedBoxGeometry(x, y, z, 5, r)
  }
  if (shape === 'cylinder') {
    const g = new CylinderGeometry(size[0], size[0], size[1], 48, 1)
    g.rotateX(Math.PI / 2) // MuJoCo cylinders run along their local z
    return g
  }
  if (shape === 'capsule') {
    const g = new CapsuleGeometry(size[0], size[1] || size[0], 10, 28)
    g.rotateX(Math.PI / 2)
    return g
  }
  return new SphereGeometry(size[0], 40, 24)
}

export class Stage {
  constructor(container, { interactive = true, dark = null, preserve = false } = {}) {
    this.container = container
    this.dark = dark == null ? isDarkTheme(container) : dark
    this.renderer = new WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: preserve })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = PCFSoftShadowMap
    this.renderer.outputColorSpace = SRGBColorSpace
    this.renderer.toneMapping = ACESFilmicToneMapping
    this.renderer.toneMappingExposure = this.dark ? 1.0 : 0.92
    this.renderer.setClearColor(0x000000, 0) // the app's own background shows through
    this.renderer.domElement.className = 'tb-canvas'
    container.appendChild(this.renderer.domElement)

    this.scene = new Scene()
    // Soft studio reflections so aluminium and clear-coated plastic read as materials, not flat colour.
    const pmrem = new PMREMGenerator(this.renderer)
    this.envMap = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    pmrem.dispose()
    this.scene.environment = this.envMap
    this.scene.environmentIntensity = this.dark ? 0.55 : 0.45

    this.camera = new PerspectiveCamera(32, 1, 0.01, 50)
    this.camera.position.set(0.6, 0.35, 0.6)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.enabled = interactive
    this.controls.maxPolarAngle = Math.PI * 0.495
    this.controls.minDistance = 0.08
    this.controls.maxDistance = 6
    this.controls.addEventListener('start', () => { this.userMoved = true })

    this._lights()
    // MuJoCo world (z up) inside a y-up three.js scene; the tilt group carries ramp angles.
    this.world = new Group()
    this.world.rotation.x = -Math.PI / 2
    this.scene.add(this.world)
    this.tilt = new Group()
    this.world.add(this.tilt)
    this.floor = new Group()
    this.tilt.add(this.floor)
    this.terrain = new Group()
    this.tilt.add(this.terrain)
    this.robot = new Group()
    this.tilt.add(this.robot)
    this._floor()

    this.meshes = []
    this.meta = {}
    this.look = {}
    this.follow = true
    this.userMoved = false
    this.tipping = false
    this._resize = new ResizeObserver(() => this.resize())
    this._resize.observe(container)
    this.resize()
    this._running = true
    const loop = () => {
      if (!this._running) return
      this._raf = requestAnimationFrame(loop)
      this.controls.update()
      this.renderer.render(this.scene, this.camera)
    }
    loop()
  }

  _lights() {
    const sky = this.dark ? 0xc8d2ff : 0xffffff
    const ground = this.dark ? 0x1a1d24 : 0xb9b4ab
    this.hemi = new HemisphereLight(sky, ground, this.dark ? 0.9 : 0.75)
    this.scene.add(this.hemi)
    const key = new DirectionalLight(0xffffff, this.dark ? 2.2 : 2.3)
    key.position.set(1.2, 2.4, 1.6)
    key.castShadow = true
    key.shadow.mapSize.set(2048, 2048)
    key.shadow.radius = 6
    key.shadow.blurSamples = 16
    key.shadow.bias = -0.0004
    key.shadow.normalBias = 0.02
    const s = key.shadow.camera
    s.left = s.bottom = -0.6
    s.right = s.top = 0.6
    s.near = 0.1
    s.far = 6
    this.key = key
    this.scene.add(key)
    this.scene.add(key.target)
    // A cool rim from behind separates white and silver robots from a light floor.
    const rim = new DirectionalLight(this.dark ? 0x8fb4ff : 0x9db6e8, this.dark ? 1.0 : 1.1)
    rim.position.set(-1.6, 1.2, -1.4)
    this.scene.add(rim)
  }

  _floor() {
    const shadow = new Mesh(new PlaneGeometry(8, 8), new ShadowMaterial({ opacity: this.dark ? 0.5 : 0.34 }))
    shadow.receiveShadow = true
    this.floor.add(shadow)
    // A procedural floor: a soft disc plus 5 cm / 20 cm grid lines, all fading out radially. In the light
    // theme the disc is a mid grey, so white and silver robots keep their outline against it.
    const SPAN = 1.6 // metres
    const grid = new Mesh(new PlaneGeometry(SPAN, SPAN), new ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: {
        uColor: { value: new Color(this.dark ? 0xffffff : 0x1d2733) },
        uDisc: { value: this.dark ? 0.07 : 0.17 },
        uMinor: { value: this.dark ? 0.12 : 0.15 },
        uMajor: { value: this.dark ? 0.26 : 0.3 },
        uSpan: { value: SPAN },
      },
      vertexShader: `
        varying vec2 vPos;
        void main() {
          vPos = position.xy;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        uniform vec3 uColor;
        uniform float uDisc, uMinor, uMajor, uSpan;
        varying vec2 vPos;
        float lines(vec2 p, float cell) {
          vec2 g = abs(fract(p / cell - 0.5) - 0.5) / fwidth(p / cell);
          return 1.0 - min(min(g.x, g.y), 1.0);
        }
        void main() {
          float r = length(vPos) / (uSpan * 0.5);
          float fade = 1.0 - smoothstep(0.15, 1.0, r);
          float a = uDisc * (1.0 - smoothstep(0.0, 0.8, r));
          a += uMinor * lines(vPos, 0.05) * fade;
          a = max(a, uMajor * lines(vPos, 0.2) * fade);
          if (a < 0.002) discard;
          gl_FragColor = vec4(uColor, a);
        }`,
    }))
    grid.position.z = 0.0006
    this.grid = grid
    this.floor.add(grid)
    this.slick = new Mesh(new CircleGeometry(1.1, 64),
      new MeshPhysicalMaterial({ color: 0x5fb7ff, transparent: true, opacity: 0.18, roughness: 0.05,
        metalness: 0, clearcoat: 1, clearcoatRoughness: 0.05, depthWrite: false }))
    this.slick.position.z = 0.001
    this.slick.visible = false
    this.floor.add(this.slick)
  }

  _material(p, look, decalParts) {
    let color = new Color(p.color || '#9aa4b2')
    if (look.accent && !decalParts.has(p.name)) color = color.lerp(new Color(look.accent), 0.78)
    if (look.material === 'aluminum') {
      return new MeshPhysicalMaterial({ color, metalness: 0.82, roughness: 0.34, clearcoat: 0.25,
        clearcoatRoughness: 0.5, envMapIntensity: 1.25 })
    }
    return new MeshPhysicalMaterial({ color, roughness: 0.46, metalness: 0.04, clearcoat: 0.4,
      clearcoatRoughness: 0.35, sheen: 0.2 })
  }

  _decorate(mesh, part, kind, look) {
    if (kind !== 'oled' || part.shape !== 'box') return
    // A small dark panel on the front (+x) face with a glowing blue OLED screen, like the real robot's face.
    const [sx, sy, sz] = part.size_m
    const pw = sy * 0.46
    const ph = sz * 0.36
    const panel = new Mesh(new RoundedBoxGeometry(0.004, pw, ph, 3, 0.0015),
      new MeshStandardMaterial({ color: 0x15181d, roughness: 0.55, metalness: 0.2 }))
    panel.position.set(sx / 2 + 0.001, 0, sz * 0.08)
    panel.castShadow = true
    mesh.add(panel)
    const glow = look.oled || '#58b4ff'
    const screen = new Mesh(new PlaneGeometry(pw * 0.78, ph * 0.62), new MeshBasicMaterial({ map: oledTexture(glow),
      toneMapped: false }))
    // Face +x (the robot's front); text runs along +y, which is the viewer's right when facing the robot.
    screen.quaternion.setFromRotationMatrix(new Matrix4().makeBasis(
      new Vector3(0, 1, 0), new Vector3(0, 0, 1), new Vector3(1, 0, 0)))
    screen.position.set(0.0022, 0, 0)
    panel.add(screen)
  }

  setRobot(parts, look = {}) {
    for (const m of this.meshes) {
      this.robot.remove(m)
      m.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose() } })
    }
    this.look = look || {}
    const decals = new Map((this.look.decals || []).map((d) => [d.part, d.kind]))
    this.meshes = parts.map((p) => {
      const mesh = new Mesh(partGeometry(p.shape, p.size_m), this._material(p, this.look, decals))
      mesh.castShadow = true
      mesh.receiveShadow = true
      mesh.name = p.name
      if (decals.has(p.name)) this._decorate(mesh, p, decals.get(p.name), this.look)
      this.robot.add(mesh)
      return mesh
    })
    this.root = this.meshes[0]
    this.tipping = false
  }

  setPose(frame) {
    if (!frame) return
    for (let i = 0; i < this.meshes.length && i < frame.length; i++) {
      const [x, y, z, qw, qx, qy, qz] = frame[i]
      this.meshes[i].position.set(x, y, z)
      this.meshes[i].quaternion.set(qx, qy, qz, qw)
    }
    this._updatePayload(frame)
    if (this.follow && this.root) this._track()
  }

  // Red highlight on every part while ``on`` (the moment a run tips over).
  setTip(on) {
    if (on === this.tipping) return
    this.tipping = on
    for (const m of this.meshes) {
      m.material.emissive = on ? TIP_RED : new Color(0x000000)
      m.material.emissiveIntensity = on ? 0.55 : 0
    }
  }

  _clearTerrain() {
    while (this.terrain.children.length) {
      const c = this.terrain.children.pop()
      c.traverse((o) => {
        if (o.geometry) o.geometry.dispose()
        if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose() }
      })
    }
    if (this.levelLine) {
      this.world.remove(this.levelLine)
      this.levelLine.geometry.dispose()
      this.levelLine.material.dispose()
      this.levelLine = null
    }
    if (this.label) {
      this.scene.remove(this.label)
      this.label.material.map.dispose()
      this.label.material.dispose()
      this.label = null
    }
  }

  setMeta(meta = {}) {
    this.meta = meta
    this._clearTerrain()
    const tilt = (meta.tilt_deg || 0) * Math.PI / 180
    this.tilt.rotation.y = -tilt // the floor rises toward +x (the robot faces uphill)
    this.slick.visible = meta.floor === 'slippery'
    if (tilt) {
      // The course: a striped ramp surface, an uphill arrow, a level reference line and the angle label.
      const ramp = new Mesh(new PlaneGeometry(1.2, 0.5), new MeshStandardMaterial({
        map: rampTexture(this.dark), transparent: true, roughness: 0.85, depthWrite: false }))
      ramp.position.set(0.3, 0, 0.0004)
      this.terrain.add(ramp)
      const up = new ArrowHelper(new Vector3(1, 0, 0), new Vector3(-0.05, -0.2, 0.002), 0.4, 0xd9a441, 0.05, 0.03)
      this.terrain.add(up)
      const level = new Line(new BufferGeometry().setFromPoints([
        new Vector3(-0.3, -0.25, 0), new Vector3(0.9, -0.25, 0)]),
      new LineDashedMaterial({ color: this.dark ? 0xffffff : 0x26303c, dashSize: 0.02, gapSize: 0.015,
        transparent: true, opacity: 0.5 }))
      level.computeLineDistances()
      this.levelLine = level
      this.world.add(level)
      this.labelAt = new Vector3(0.16, -0.13, 0.025)
      this.label = textSprite(`${Math.round(meta.tilt_deg)}° ramp`, { color: '#ffd27a' })
      this.scene.add(this.label)
    }
    for (const b of meta.boxes || []) {
      const [hx, hy, hz] = b.half
      const width = Math.min(hy, 0.18) * 2
      // Hazard tape: alternating yellow and black 3 cm segments along the bar (no UV tricks needed).
      const bar = new Group()
      const seg = 0.03
      const n = Math.max(2, Math.round(width / seg))
      const yellow = new MeshStandardMaterial({ color: HAZARD_YELLOW, roughness: 0.55 })
      const black = new MeshStandardMaterial({ color: 0x16181c, roughness: 0.6 })
      for (let i = 0; i < n; i++) {
        const piece = new Mesh(new RoundedBoxGeometry(hx * 2, width / n, hz * 2, 2, Math.min(hx, hz) * 0.18),
          i % 2 ? black : yellow)
        piece.position.set(0, -width / 2 + (i + 0.5) * (width / n), 0)
        piece.castShadow = piece.receiveShadow = true
        bar.add(piece)
      }
      bar.position.set(...b.center)
      this.terrain.add(bar)
      this.labelAt = new Vector3(b.center[0] + 0.05, -0.16, hz * 2 + 0.012)
      this.label = textSprite(`${Math.round(hz * 2 * 1000) / 10} cm bar`, { color: HAZARD_YELLOW })
      this.scene.add(this.label)
    }
    this.arrow = null
    if (meta.push) {
      const v = meta.push.vector || [1, 0]
      const dir = new Vector3(v[0], v[1], 0).normalize()
      this.arrow = new ArrowHelper(dir, new Vector3(), 0.12, 0xff5a4f, 0.04, 0.025)
      this.arrow.visible = false
      this.terrain.add(this.arrow)
    }
    this.payload = null
    if (meta.payload && meta.payload.part) {
      const r = 0.008 + Math.cbrt(Math.max(meta.payload.grams, 1)) * 0.0022
      this.payload = new Mesh(new SphereGeometry(r, 24, 16),
        new MeshStandardMaterial({ color: 0x7c8796, roughness: 0.3, metalness: 0.6 }))
      this.payload.castShadow = true
      this.payloadIndex = this.meshes.findIndex((m) => m.name === meta.payload.part)
      this.terrain.add(this.payload)
    }
    this._placeLabel()
  }

  _placeLabel() {
    if (!this.label || !this.labelAt) return
    this.scene.updateMatrixWorld(true)
    this.label.position.copy(this.labelAt.clone().applyMatrix4(this.tilt.matrixWorld))
  }

  setTime(t) {
    if (!this.arrow || !this.meta.push || !this.root) return
    const p = this.meta.push
    const on = t >= p.at_s - 0.05 && t <= p.at_s + Math.max(p.duration_s, 0.5)
    this.arrow.visible = on
    if (on) {
      const dir = new Vector3(p.vector[0], p.vector[1], 0).normalize()
      this.arrow.position.copy(this.root.position.clone().addScaledVector(dir, -0.16))
    }
  }

  _updatePayload(frame) {
    if (!this.payload || this.payloadIndex < 0) return
    const [x, y, z] = frame[this.payloadIndex]
    this.payload.position.set(x, y, z - 0.025)
  }

  _robotBox() {
    const box = new Box3()
    for (const m of this.meshes) box.expandByObject(m)
    return box
  }

  // Aim the camera at the robot. ``fit`` also chooses the distance (first frame or "reset view").
  frame(fit = true, { distance = 2.35, azimuth = [0.78, 0.5, 0.72] } = {}) {
    this.scene.updateMatrixWorld(true)
    const box = this._robotBox()
    if (box.isEmpty()) return
    const center = box.getCenter(new Vector3())
    const size = box.getSize(new Vector3()).length()
    this._size = size
    center.y *= 0.85 // aim a little low so the floor and the shadow are in frame
    this.controls.target.copy(center)
    if (fit) {
      const dist = Math.max(size * distance, 0.3)
      // 3/4 view from the front right, slightly above (robot faces MuJoCo +x = three +x).
      const dir = new Vector3(...azimuth).normalize()
      this.camera.position.copy(center).addScaledVector(dir, dist)
      this.userMoved = false
    }
    this._aimLight(center, size)
    this._placeLabel()
    this.controls.update()
  }

  _track() {
    // Follow the whole robot (its bounding-box centre), not one part, so nothing leaves the frame.
    this.scene.updateMatrixWorld(true)
    const box = this._robotBox()
    if (box.isEmpty()) return
    const p = box.getCenter(new Vector3())
    p.y = this.controls.target.y + (p.y - this.controls.target.y) * 0.3
    const step = p.sub(this.controls.target).multiplyScalar(0.12)
    this.controls.target.add(step)
    this.camera.position.add(step)
    // Keep the faded grid under a walking robot, snapped to whole 20 cm cells so it never slides.
    this.grid.position.x = Math.round(this.root.position.x / 0.2) * 0.2
    this.grid.position.y = Math.round(this.root.position.y / 0.2) * 0.2
    this._aimLight(this.controls.target, this._size || 0.4)
  }

  _aimLight(center, size) {
    this.key.target.position.copy(center)
    this.key.position.copy(center).add(new Vector3(1.2, 2.4, 1.6).normalize().multiplyScalar(2.2))
    const s = Math.max(size, 0.3)
    const cam = this.key.shadow.camera
    cam.left = cam.bottom = -s
    cam.right = cam.top = s
    cam.updateProjectionMatrix()
  }

  resize() {
    const w = Math.max(this.container.clientWidth, 10)
    const h = Math.max(this.container.clientHeight, 10)
    this.renderer.setSize(w, h, false)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  renderNow() {
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }

  dispose() {
    this._running = false
    cancelAnimationFrame(this._raf)
    this._resize.disconnect()
    this.controls.dispose()
    this._clearTerrain()
    this.scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose()
      if (o.material) {
        if (o.material.map) o.material.map.dispose()
        o.material.dispose()
      }
    })
    if (this.envMap) this.envMap.dispose()
    this.renderer.dispose()
    this.renderer.forceContextLoss()
    this.renderer.domElement.remove()
  }
}
