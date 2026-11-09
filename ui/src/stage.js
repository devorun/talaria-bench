// The 3D stage: one three.js scene per viewer (and per gallery render). Robots arrive as MuJoCo geometry
// (metres, z up, x forward) and per-frame poses [x, y, z, qw, qx, qy, qz]. The stage draws them as built
// parts (bevelled boards, satin prints, foil, servo horns at the joints) on a shadowed floor with a 10 cm
// scale mark, dresses the scene's course (a ramp wedge with its angle, a hazard-striped bar with its height,
// a slippery sheet, a push arrow with its force, a payload block with its mass), marks the part that
// touches the floor when a run tips, and keeps the camera on the robot.
//
// Everything here is appearance only: servo horns, screws, bevels and decals never enter the physics model,
// which is built from the robot spec alone. No app markup is touched.
import {
  BufferGeometry, CanvasTexture, CapsuleGeometry, CircleGeometry, Color, ConeGeometry, CylinderGeometry,
  DirectionalLight, DoubleSide, Float32BufferAttribute, Group, HemisphereLight, Matrix4, Mesh, MeshBasicMaterial,
  MeshPhysicalMaterial, MeshStandardMaterial, NeutralToneMapping, PCFSoftShadowMap, PerspectiveCamera,
  PlaneGeometry, PMREMGenerator, Quaternion, RingGeometry, Scene, ShaderMaterial, ShadowMaterial,
  SphereGeometry, Sprite, SpriteMaterial, SRGBColorSpace, Vector3, WebGLRenderer,
} from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'

const TIP_RED = new Color(0xff2d20)
const BLACK = new Color(0x000000)
const HAZARD_YELLOW = '#f5c518'
const RAMP_TOP = '#c9b88f'
const RAMP_EDGE = '#e3a52c'
const RAMP_SIDE = 0xa5946c
const AXES = [new Vector3(1, 0, 0), new Vector3(0, 1, 0), new Vector3(0, 0, 1)]
const Y_AXIS = new Vector3(0, 1, 0)
const VIEW_FRONT = [0.78, 0.5, 0.72] // 3/4 from the front right, slightly above
const VIEW_SIDE = [0.24, 0.4, 1.0] // from the side: an incline reads as an incline

// How each spec material is drawn. The contact model of a material lives in materials.py; this is its look.
const FINISH = {
  foam: { roughness: 0.9, metalness: 0, clearcoat: 0, sheen: 0.5, sheenRoughness: 0.9, bevel: [0.1, 0.0016] },
  pla: { roughness: 0.5, metalness: 0.02, clearcoat: 0.3, clearcoatRoughness: 0.45, bevel: [0.2, 0.0036] },
  wood: { roughness: 0.82, metalness: 0, clearcoat: 0, bevel: [0.1, 0.002] },
  metal: { roughness: 0.34, metalness: 0.88, clearcoat: 0.15, clearcoatRoughness: 0.5, bevel: [0.12, 0.002] },
  rubber: { roughness: 0.96, metalness: 0, clearcoat: 0, bevel: [0.25, 0.004] },
}
// look.material: aluminum = foil-wrapped board (Caduceus): bright satin metal with crisp edges.
const FOIL = { roughness: 0.37, metalness: 0.9, clearcoat: 0.1, clearcoatRoughness: 0.6, envMapIntensity: 1.3,
  bevel: [0.08, 0.0018] }

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

// Ramp surface: a pale board with a line every 5 cm (stronger every 20 cm) and amber edge bands.
function rampTexture(length, width) {
  const w = 1024
  const h = Math.max(128, Math.round((w * width) / length))
  return canvasTexture(w, h, (g) => {
    g.fillStyle = RAMP_TOP
    g.fillRect(0, 0, w, h)
    const px = w / length
    for (let i = 0; i * 0.05 <= length + 1e-6; i++) {
      const strong = i % 4 === 0
      g.fillStyle = strong ? 'rgba(60,45,15,0.42)' : 'rgba(60,45,15,0.18)'
      g.fillRect(Math.round(i * 0.05 * px) - (strong ? 2 : 1), 0, strong ? 4 : 2, h)
    }
    const band = Math.round(0.018 * px)
    g.fillStyle = RAMP_EDGE
    g.fillRect(0, 0, w, band)
    g.fillRect(0, h - band, w, band)
  })
}

// A text label that keeps the same size on screen (``px`` CSS pixels tall) at any camera distance, so it
// stays readable in a small tile and on a 1080p recording. Its bottom centre sits at its position.
function textSprite(text, { color = '#ffffff', bg = 'rgba(20,22,28,0.86)', px = 19 } = {}) {
  const pad = 20
  const font = '650 64px system-ui, -apple-system, Segoe UI, sans-serif'
  const probe = document.createElement('canvas').getContext('2d')
  probe.font = font
  const w = Math.ceil(probe.measureText(text).width) + pad * 2
  const tex = canvasTexture(w, 96, (g, cw, ch) => {
    g.fillStyle = bg
    const r = 24
    g.beginPath()
    g.moveTo(r, 0); g.arcTo(cw, 0, cw, ch, r); g.arcTo(cw, ch, 0, ch, r); g.arcTo(0, ch, 0, 0, r); g.arcTo(0, 0, cw, 0, r)
    g.fill()
    g.font = font
    g.fillStyle = color
    g.textBaseline = 'middle'
    g.fillText(text, pad, ch / 2 + 3)
  })
  const sprite = new Sprite(new SpriteMaterial({ map: tex, depthTest: false, transparent: true, sizeAttenuation: false }))
  sprite.userData = { label: true, px, aspect: w / 96 }
  sprite.center.set(0.5, 0)
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

function finishOf(part, look) {
  if (look.material === 'aluminum') return FOIL
  const detail = (look.detail || {})[part.name] || {}
  return FINISH[detail.material] || FINISH.pla
}

function partGeometry(shape, size, finish) {
  if (shape === 'box') {
    const [x, y, z] = size
    const m = Math.min(x, y, z)
    const [share, cap] = finish.bevel
    return new RoundedBoxGeometry(x, y, z, 4, Math.min(m * share, cap, m * 0.49))
  }
  if (shape === 'cylinder') {
    const g = new CylinderGeometry(size[0], size[0], size[1], 56, 1)
    g.rotateX(Math.PI / 2) // MuJoCo cylinders run along their local z
    return g
  }
  if (shape === 'capsule') {
    const g = new CapsuleGeometry(size[0], size[1] || size[0], 10, 28)
    g.rotateX(Math.PI / 2)
    return g
  }
  return new SphereGeometry(size[0], 48, 28)
}

// Half-extent of a part along a unit direction given in the part's own frame.
function support(shape, size, d) {
  if (shape === 'box') return (Math.abs(d.x) * size[0] + Math.abs(d.y) * size[1] + Math.abs(d.z) * size[2]) / 2
  if (shape === 'cylinder') return (Math.abs(d.z) * size[1]) / 2 + size[0] * Math.sqrt(Math.max(0, 1 - d.z * d.z))
  if (shape === 'capsule') return (Math.abs(d.z) * (size[1] || size[0])) / 2 + size[0]
  return size[0]
}

function disposeTree(root) {
  root.traverse((o) => {
    if (o.geometry) o.geometry.dispose()
    if (o.material) {
      if (o.material.map) o.material.map.dispose()
      o.material.dispose()
    }
  })
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
    // Neutral tone mapping keeps part colours true (a product-shot look) instead of washing them out.
    this.renderer.toneMapping = NeutralToneMapping
    this.renderer.toneMappingExposure = this.dark ? 0.95 : 1.0
    this.renderer.setClearColor(0x000000, 0) // the app's own background shows through
    this.renderer.domElement.className = 'tb-canvas'
    container.appendChild(this.renderer.domElement)

    this.scene = new Scene()
    // Soft studio reflections so foil and clear-coated plastic read as materials, not flat colour.
    const pmrem = new PMREMGenerator(this.renderer)
    this.envMap = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    pmrem.dispose()
    this.scene.environment = this.envMap
    this.scene.environmentIntensity = this.dark ? 0.5 : 0.55

    this.camera = new PerspectiveCamera(32, 1, 0.01, 50)
    this.camera.position.set(0.6, 0.35, 0.6)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.enabled = interactive
    this.controls.maxPolarAngle = Math.PI * 0.495
    this.controls.minDistance = 0.08
    this.controls.maxDistance = 6
    this.controls.autoRotateSpeed = 0.9
    this.controls.addEventListener('start', () => { this.userMoved = true; this.controls.autoRotate = false })

    this._lights()
    // MuJoCo world (z up) inside a y-up three.js scene; the tilt group carries ramp angles.
    this.world = new Group()
    this.world.rotation.x = -Math.PI / 2
    this.scene.add(this.world)
    this.tilt = new Group()
    this.world.add(this.tilt)
    const floor = this._makeFloor()
    this.floor = floor.group
    this.grid = floor.grid
    this.tilt.add(this.floor)
    this.slick = new Group()
    this.slick.visible = false
    this.floor.add(this.slick)
    this._slick()
    this.terrain = new Group()
    this.tilt.add(this.terrain)
    this.robot = new Group()
    this.tilt.add(this.robot)

    this.meshes = []
    this.meta = {}
    this.look = {}
    this.follow = true
    this.userMoved = false
    this.tipPhase = 0
    this.tipPart = null
    this._qa = new Quaternion()
    this._qb = new Quaternion()
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
    const sky = this.dark ? 0xd3dcff : 0xffffff
    const ground = this.dark ? 0x20242c : 0xb9b4ab
    this.hemi = new HemisphereLight(sky, ground, this.dark ? 0.7 : 0.8)
    this.scene.add(this.hemi)
    const key = new DirectionalLight(0xfff6ea, this.dark ? 2.0 : 2.3)
    key.position.set(1.2, 2.4, 1.6)
    key.castShadow = true
    key.shadow.mapSize.set(2048, 2048)
    key.shadow.radius = 5
    key.shadow.blurSamples = 16
    key.shadow.bias = -0.0003
    key.shadow.normalBias = 0.012
    const s = key.shadow.camera
    s.left = s.bottom = -0.6
    s.right = s.top = 0.6
    s.near = 0.1
    s.far = 6
    this.key = key
    this.scene.add(key)
    this.scene.add(key.target)
    // A soft fill from the camera side opens the shadows; a cool rim from behind separates white and
    // silver robots from a light floor.
    const fill = new DirectionalLight(0xdfe8ff, this.dark ? 0.55 : 0.5)
    fill.position.set(1.4, 0.7, -1.6)
    this.scene.add(fill)
    const rim = new DirectionalLight(this.dark ? 0x8fb4ff : 0x9db6e8, this.dark ? 1.1 : 1.0)
    rim.position.set(-1.6, 1.2, -1.4)
    this.scene.add(rim)
  }

  // A shadow catcher plus a procedural grid: a soft disc with 5 cm / 20 cm lines, fading out radially. In
  // the light theme the disc is a mid grey, so white and silver robots keep their outline against it.
  _makeFloor() {
    const group = new Group()
    const shadow = new Mesh(new PlaneGeometry(8, 8), new ShadowMaterial({ opacity: this.dark ? 0.5 : 0.32 }))
    shadow.receiveShadow = true
    group.add(shadow)
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
    group.add(grid)
    return { group, grid }
  }

  // The slippery floor: a glossy, faintly blue sheet with a brighter rim.
  _slick() {
    const sheet = new Mesh(new CircleGeometry(0.62, 72),
      new MeshPhysicalMaterial({ color: 0x66bdff, transparent: true, opacity: this.dark ? 0.15 : 0.22, roughness: 0.03,
        metalness: 0, clearcoat: 1, clearcoatRoughness: 0.03, depthWrite: false }))
    sheet.position.z = 0.001
    const rim = new Mesh(new RingGeometry(0.612, 0.62, 72),
      new MeshBasicMaterial({ color: 0x9bd4ff, transparent: true, opacity: 0.75, depthWrite: false }))
    rim.position.z = 0.0012
    this.slick.add(sheet, rim)
  }

  _material(p, look, decalParts, finish) {
    let color = new Color(p.color || '#9aa4b2')
    if (look.accent && !decalParts.has(p.name)) color = color.lerp(new Color(look.accent), 0.78)
    const { bevel, ...pbr } = finish
    if (finish === FOIL) color.lerp(new Color(0xffffff), 0.28) // foil is a little brighter than the board under it
    return new MeshPhysicalMaterial({ color, ...pbr })
  }

  _decorate(mesh, part, kind, look) {
    if (kind !== 'oled' || part.shape !== 'box') return
    // A dark bezel on the front (+x) face with a glowing OLED screen, like the real robot's face.
    const [sx, sy, sz] = part.size_m
    const pw = sy * 0.34
    const ph = sz * 0.3
    const panel = new Mesh(new RoundedBoxGeometry(0.003, pw, ph, 3, 0.0012),
      new MeshStandardMaterial({ color: 0x101317, roughness: 0.4, metalness: 0.3 }))
    panel.position.set(sx / 2 + 0.0008, 0, sz * 0.06)
    panel.castShadow = true
    mesh.add(panel)
    const glow = look.oled || '#58b4ff'
    const screen = new Mesh(new PlaneGeometry(pw * 0.84, ph * 0.72), new MeshBasicMaterial({ map: oledTexture(glow),
      toneMapped: false }))
    // Face +x (the robot's front); text runs along +y, which is the viewer's right when facing the robot.
    screen.quaternion.setFromRotationMatrix(new Matrix4().makeBasis(
      new Vector3(0, 1, 0), new Vector3(0, 0, 1), new Vector3(1, 0, 0)))
    screen.position.set(0.0017, 0, 0)
    panel.add(screen)
  }

  // A servo horn with its screw at a joint: a short dark (or light, on dark parts) cylinder along the joint
  // axis, through the driven part. It is symmetric about the axis, so it sits right for both linked parts.
  _horn(mesh, part, d, color) {
    const axis = new Vector3(...d.axis)
    if (axis.lengthSq() < 0.5) return
    axis.normalize()
    const anchor = new Vector3(...d.anchor)
    const half = support(part.shape, part.size_m, axis)
    const centre = -anchor.dot(axis) // the part's centre along the axis, measured from the joint
    const eps = 0.0016
    // From the joint through the part; a joint far outside the part gets a stub, not a long rod.
    const s0 = Math.max(Math.min(0, centre - half), centre - half - 0.012) - eps
    const s1 = Math.min(Math.max(0, centre + half), centre + half + 0.012) + eps
    const least = AXES.reduce((a, b) => (Math.abs(a.dot(axis)) < Math.abs(b.dot(axis)) ? a : b))
    const u = new Vector3().crossVectors(axis, least).normalize()
    const v = new Vector3().crossVectors(axis, u)
    const across = Math.min(support(part.shape, part.size_m, u), support(part.shape, part.size_m, v))
    const big = /996|995|946|ds3|standard/i.test(d.servo || '')
    const radius = Math.min(big ? 0.0105 : 0.0072, across * 0.8)
    if (radius < 0.0025) return
    const lum = 0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b
    const horn = new Mesh(new CylinderGeometry(radius, radius, s1 - s0, 36),
      new MeshStandardMaterial({ color: lum < 0.12 ? 0xe6e2d8 : 0x23272e, roughness: 0.55, metalness: 0.05 }))
    horn.quaternion.setFromUnitVectors(Y_AXIS, axis)
    horn.position.copy(anchor).addScaledVector(axis, (s0 + s1) / 2)
    horn.castShadow = true
    const screw = new Mesh(new CylinderGeometry(radius * 0.36, radius * 0.36, s1 - s0 + 0.0012, 20),
      new MeshStandardMaterial({ color: 0xc9ced6, roughness: 0.28, metalness: 1 }))
    horn.add(screw)
    mesh.add(horn)
  }

  setRobot(parts, look = {}) {
    for (const m of this.meshes) {
      this.robot.remove(m)
      disposeTree(m)
    }
    this._clearTip()
    this.look = look || {}
    const detail = this.look.detail || {}
    const decals = new Map((this.look.decals || []).map((d) => [d.part, d.kind]))
    this.meshes = parts.map((p) => {
      const finish = finishOf(p, this.look)
      const mesh = new Mesh(partGeometry(p.shape, p.size_m, finish), this._material(p, this.look, decals, finish))
      mesh.castShadow = true
      mesh.receiveShadow = true
      mesh.name = p.name
      mesh.userData = { shape: p.shape, size: p.size_m, ground: (detail[p.name] || {}).ground }
      if (decals.has(p.name)) this._decorate(mesh, p, decals.get(p.name), this.look)
      const d = detail[p.name]
      if (d && d.anchor && d.axis) this._horn(mesh, p, d, mesh.material.color)
      this.robot.add(mesh)
      return mesh
    })
    this.root = this.meshes[0]
    this.known = Object.keys(detail).length > 0
  }

  setPose(frame) {
    if (!frame) return
    for (let i = 0; i < this.meshes.length && i < frame.length; i++) {
      const [x, y, z, qw, qx, qy, qz] = frame[i]
      this.meshes[i].position.set(x, y, z)
      this.meshes[i].quaternion.set(qx, qy, qz, qw)
    }
    this._afterPose()
  }

  // A pose between two recorded frames (k in 0..1), so replays stay smooth at any display rate and in
  // slow motion.
  setPoseBlend(a, b, k) {
    if (!a) return
    if (!b || k <= 0) { this.setPose(a); return }
    for (let i = 0; i < this.meshes.length && i < a.length && i < b.length; i++) {
      const p = a[i], q = b[i]
      this.meshes[i].position.set(p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k, p[2] + (q[2] - p[2]) * k)
      this._qa.set(p[4], p[5], p[6], p[3])
      this._qb.set(q[4], q[5], q[6], q[3])
      this.meshes[i].quaternion.slerpQuaternions(this._qa, this._qb, k)
    }
    this._afterPose()
  }

  _afterPose() {
    this._updatePayload()
    if (this.tipLabel && this.tipPart) this._placeAbove(this.tipLabel, this.tipPart, 0.014)
    if (this.follow && this.root) this._track()
  }

  // The lowest and highest point of every part along x, y, z of the (possibly tilted) floor frame.
  _bounds(meshes = this.meshes) {
    const lo = new Vector3(Infinity, Infinity, Infinity)
    const hi = new Vector3(-Infinity, -Infinity, -Infinity)
    const inv = new Quaternion()
    const d = new Vector3()
    for (const m of meshes) {
      inv.copy(m.quaternion).invert()
      AXES.forEach((axis, i) => {
        const h = support(m.userData.shape, m.userData.size, d.copy(axis).applyQuaternion(inv))
        lo.setComponent(i, Math.min(lo.getComponent(i), m.position.getComponent(i) - h))
        hi.setComponent(i, Math.max(hi.getComponent(i), m.position.getComponent(i) + h))
      })
    }
    return { lo, hi }
  }

  _placeAbove(sprite, mesh, gap) {
    const { hi } = this._bounds([mesh])
    sprite.position.set(mesh.position.x, mesh.position.y, hi.z + gap)
  }

  // 0: nothing. 1: the moment of the tip (strong red on the part that touches the floor, plus a label).
  // 2: afterwards (the part stays faintly marked until the replay loops).
  // ``why`` is the simulator's fall reason when the run has one ("part 'head' touched the floor", "root tilted
  // more than 60 deg"); without it the stage works the part out from the pose.
  setTip(phase, why = null) {
    if (phase === this.tipPhase) return
    const was = this.tipPhase
    this.tipPhase = phase
    if (!phase) { this._clearTip(); return }
    if (!was) this._markTip(why)
    const strength = phase === 1 ? 0.7 : 0.3
    for (const m of this.tipMarked || []) m.material.emissiveIntensity = strength
  }

  _markTip(why) {
    // Which part ended the run. First choice: the simulator's reason. Else the lowest part that must not
    // touch the floor, if it is at the floor; otherwise the body tilted past the limit. Runs recorded
    // without part hints mark the whole robot.
    let part = null
    let text = 'tipped over'
    const named = /'([^']+)' touched the floor/.exec(why || '')
    const touched = named ? this.meshes.find((m) => m.name === named[1]) : null
    if (touched) {
      part = touched
      text = `${part.name.replace(/_/g, ' ')} touches the floor`
    } else if (/tilted more than/.test(why || '')) {
      part = this.root
      text = 'tilted past 60°'
    } else if (this.known) {
      let lowest = Infinity
      for (const m of this.meshes) {
        if (m.userData.ground) continue
        const z = this._bounds([m]).lo.z
        if (z < lowest) { lowest = z; part = m }
      }
      if (part && lowest < 0.006) text = `${part.name.replace(/_/g, ' ')} touches the floor`
      else { part = this.root; text = 'tilted past 60°' }
    }
    this.tipMarked = part ? [part] : this.meshes
    for (const m of this.tipMarked) m.material.emissive = TIP_RED
    this.tipPart = part || this.root
    if (this.tipPart) {
      this.tipLabel = textSprite(text, { bg: 'rgba(214,40,28,0.94)' })
      this.robot.add(this.tipLabel)
      this._placeAbove(this.tipLabel, this.tipPart, 0.014)
      this._fitLabels()
    }
  }

  _clearTip() {
    for (const m of this.tipMarked || []) {
      m.material.emissive = BLACK
      m.material.emissiveIntensity = 0
    }
    this.tipMarked = null
    this.tipPart = null
    this.tipPhase = 0
    if (this.tipLabel) {
      this.robot.remove(this.tipLabel)
      this.tipLabel.material.map.dispose()
      this.tipLabel.material.dispose()
      this.tipLabel = null
    }
  }

  // Labels keep their pixel size: scale each one for the current canvas height.
  _fitLabels() {
    const unit = (2 * Math.tan((this.camera.fov * Math.PI) / 360)) / Math.max(this.container.clientHeight, 10)
    this.scene.traverse((o) => {
      if (o.userData && o.userData.label) o.scale.set(o.userData.px * o.userData.aspect * unit, o.userData.px * unit, 1)
    })
  }

  _label(text, at, opts = {}) {
    const sprite = textSprite(text, opts)
    sprite.position.copy(at)
    this.terrain.add(sprite)
    return sprite
  }

  _clearTerrain() {
    while (this.terrain.children.length) disposeTree(this.terrain.children.pop())
    if (this.level) {
      this.world.remove(this.level)
      disposeTree(this.level)
      this.level = null
    }
    this.arrow = null
    this.payload = null
    this.payloadLabel = null
  }

  // Dress the scene. Call after the robot has its first pose: sizes and positions follow the robot.
  setMeta(meta = {}) {
    this.meta = meta
    this._clearTerrain()
    const { lo, hi } = this.meshes.length ? this._bounds() : { lo: new Vector3(-0.1, -0.1, 0), hi: new Vector3(0.1, 0.1, 0.1) }
    this._size = hi.clone().sub(lo).length()
    const mid = lo.clone().add(hi).multiplyScalar(0.5)
    const tilt = ((meta.tilt_deg || 0) * Math.PI) / 180
    this.tilt.rotation.y = -tilt // the floor rises toward +x (the robot faces uphill)
    this.slick.visible = meta.floor === 'slippery'
    this.floor.visible = !tilt
    const ink = this.dark ? 0xffffff : 0x26303c
    const near = lo.y - Math.max(0.035, this._size * 0.1) // the camera's side of the robot

    if (tilt) this._ramp(tilt, meta.tilt_deg, lo, hi)
    else if (meta.mark === 'front') this._scaleMark(hi.x + Math.max(0.03, this._size * 0.1), mid.y + (hi.y - lo.y) * 0.3, ink, true)
    else if (meta.mark !== 'none') this._scaleMark(mid.x, near, ink)

    if (meta.floor === 'slippery') {
      this.slick.position.set(mid.x, mid.y, 0)
      const mu = typeof meta.friction === 'number' ? ` · friction ${meta.friction.toFixed(2)}` : ''
      this._label(`slippery floor${mu}`, new Vector3(hi.x + this._size * 0.16, mid.y + (hi.y - lo.y) * 0.25, 0.004),
        { color: '#bfe4ff' })
    }
    for (const b of meta.boxes || []) {
      const [hx, hy, hz] = b.half
      const width = Math.min(hy, Math.max(0.18, (hi.y - lo.y) * 0.9)) * 2
      // Hazard tape: alternating yellow and black 3 cm segments along the bar.
      const bar = new Group()
      const n = Math.max(2, Math.round(width / 0.03))
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
      this._label(`${Math.round(hz * 2 * 1000) / 10} cm bar`, new Vector3(b.center[0], -width / 2 - 0.02, hz * 2 + 0.008),
        { color: HAZARD_YELLOW })
    }
    if (meta.push) {
      // A solid arrow that appears for the push, with the force in body weights.
      const v = meta.push.vector || [1, 0]
      const dir = new Vector3(v[0], v[1], 0).normalize()
      const len = Math.max(0.07, this._size * 0.32)
      const mat = new MeshStandardMaterial({ color: 0xff5a4f, roughness: 0.4, emissive: 0xff5a4f, emissiveIntensity: 0.25 })
      const arrow = new Group()
      const shaft = new Mesh(new CylinderGeometry(len * 0.07, len * 0.07, len * 0.66, 20), mat)
      shaft.position.y = len * 0.33
      const head = new Mesh(new ConeGeometry(len * 0.17, len * 0.34, 28), mat)
      head.position.y = len * 0.83
      arrow.add(shaft, head)
      arrow.quaternion.setFromUnitVectors(Y_AXIS, dir)
      arrow.userData = { dir, len }
      arrow.visible = false
      shaft.castShadow = head.castShadow = true
      this.arrow = arrow
      this.terrain.add(arrow)
      const level = meta.push.level
      this.arrowLabel = this._label(level != null ? `push ${level}× weight` : 'push', new Vector3(), { color: '#ffd0cb' })
      this.arrowLabel.visible = false
    }
    if (meta.payload && meta.payload.part) {
      // The payload: a steel block hanging at the carrying part, with its mass.
      const side = 0.012 + Math.cbrt(Math.max(meta.payload.grams, 1)) * 0.0034
      this.payload = new Mesh(new RoundedBoxGeometry(side, side, side, 3, side * 0.12),
        new MeshStandardMaterial({ color: 0x8792a2, roughness: 0.32, metalness: 0.75 }))
      this.payload.castShadow = true
      this.payload.userData = { side }
      this.payloadIndex = this.meshes.findIndex((m) => m.name === meta.payload.part)
      this.terrain.add(this.payload)
      this.payloadLabel = this._label(`${meta.payload.grams} g payload`, new Vector3(), { color: '#e3e8ef' })
      this._updatePayload()
    }
    this._fitLabels()
  }

  // A 10 cm scale mark on the floor beside the robot (or, ``across``, in front of it).
  _scaleMark(x, y, ink, across = false) {
    const mat = new MeshBasicMaterial({ color: ink, transparent: true, opacity: this.dark ? 0.8 : 0.75, depthWrite: false })
    const mark = new Group()
    const bar = new Mesh(new PlaneGeometry(0.1, 0.0024), mat)
    const a = new Mesh(new PlaneGeometry(0.0024, 0.012), mat)
    const b = new Mesh(new PlaneGeometry(0.0024, 0.012), mat)
    a.position.x = -0.05
    b.position.x = 0.05
    mark.add(bar, a, b)
    mark.position.set(x, y, 0.0014)
    if (across) mark.rotation.z = Math.PI / 2
    this.terrain.add(mark)
    const label = textSprite('10 cm', { px: 15, color: this.dark ? '#ffffff' : '#1d2733',
      bg: this.dark ? 'rgba(20,22,28,0.62)' : 'rgba(255,255,255,0.78)' })
    label.position.set(x, y, 0.005)
    this.terrain.add(label)
  }

  // The ramp: a wedge on a level floor. Its top is the tilted floor the robot stands on; the side wall
  // facing the camera carries the angle (a level line, an arc and the number).
  _ramp(tilt, degrees, lo, hi) {
    const length = hi.x - lo.x
    const x0 = lo.x - Math.max(0.24, length * 0.9)
    const x1 = hi.x + Math.max(0.7, length * 2.2)
    const half = Math.max(0.2, (hi.y - lo.y) * 0.5 + 0.1)
    const cx = (lo.y + hi.y) / 2
    const top = new Mesh(new PlaneGeometry(x1 - x0, half * 2),
      new MeshStandardMaterial({ map: rampTexture(x1 - x0, half * 2), roughness: 0.86 }))
    top.position.set((x0 + x1) / 2, cx, -0.0002)
    top.receiveShadow = true
    this.terrain.add(top)
    this._scaleMark((lo.x + hi.x) / 2, lo.y - Math.min(0.05, (half - (hi.y - lo.y) / 2) * 0.5), 0x3a2f18)

    // Everything below the top lives in the level world frame (x forward, z up).
    const c = Math.cos(tilt), s = Math.sin(tilt)
    const level = new Group()
    const [ax, az] = [x0 * c, x0 * s] // the low edge, on the floor
    const [bx, bz] = [x1 * c, x1 * s] // the high edge
    const y0 = cx - half, y1 = cx + half
    const wedge = new BufferGeometry()
    wedge.setAttribute('position', new Float32BufferAttribute([
      ax, y0, az, bx, y0, az, bx, y0, bz, // side facing the camera (-y)
      ax, y1, az, bx, y1, bz, bx, y1, az, // far side
      bx, y0, az, bx, y1, az, bx, y1, bz, bx, y0, az, bx, y1, bz, bx, y0, bz, // the tall end
    ], 3))
    wedge.computeVertexNormals()
    level.add(new Mesh(wedge, new MeshStandardMaterial({ color: RAMP_SIDE, roughness: 0.9, side: DoubleSide })))
    const floor = this._makeFloor()
    floor.group.position.set((lo.x + hi.x) / 2 * c, cx, az - 0.0004)
    level.add(floor.group)

    // The angle, drawn on the camera-side wall just behind the robot: level line, arc, number.
    const px = Math.max(x0 + 0.02, lo.x - Math.max(0.05, length * 0.3))
    const r = Math.min(0.2, Math.max(0.1, length * 0.7))
    const wall = y0 - 0.0008
    const dark = new MeshBasicMaterial({ color: 0x2b2416, side: DoubleSide })
    const sector = new Mesh(new CircleGeometry(r, 40, 0, tilt), new MeshBasicMaterial({ color: 0x2b2416,
      transparent: true, opacity: 0.2, side: DoubleSide }))
    sector.rotation.x = Math.PI / 2
    sector.position.set(px * c, wall, px * s)
    const arc = new Mesh(new RingGeometry(r - 0.003, r, 40, 1, 0, tilt), dark)
    arc.rotation.x = Math.PI / 2
    arc.position.copy(sector.position)
    const line = new Mesh(new PlaneGeometry(r * 1.25, 0.003), dark)
    line.rotation.x = Math.PI / 2
    line.position.set(px * c + r * 0.625, wall, px * s)
    level.add(sector, arc, line)
    const label = textSprite(`${Math.round(degrees)}° ramp`, { color: '#ffd27a', px: 22 })
    label.position.set(px * c + r * 1.45 * Math.cos(tilt / 2), wall - 0.01, px * s + r * 1.45 * Math.sin(tilt / 2) - 0.02)
    level.add(label)
    this.level = level
    this.world.add(level)
  }

  setTime(t) {
    if (!this.arrow || !this.meta.push || !this.root) return
    const p = this.meta.push
    const on = t >= p.at_s - 0.05 && t <= p.at_s + Math.max(p.duration_s, 0.6)
    this.arrow.visible = on
    this.arrowLabel.visible = on
    if (on) {
      const { dir, len } = this.arrow.userData
      const { lo, hi } = this._bounds()
      const reach = Math.abs(dir.x) * (hi.x - lo.x) / 2 + Math.abs(dir.y) * (hi.y - lo.y) / 2
      const height = (lo.z + hi.z) / 2
      const tail = new Vector3((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, height).addScaledVector(dir, -(reach + len + 0.012))
      this.arrow.position.copy(tail)
      this.arrowLabel.position.copy(tail).add(new Vector3(0, 0, len * 0.25))
    }
  }

  _updatePayload() {
    if (!this.payload || this.payloadIndex < 0) return
    const m = this.meshes[this.payloadIndex]
    const { lo } = this._bounds([m])
    const side = this.payload.userData.side
    this.payload.position.set(m.position.x, m.position.y, Math.max(lo.z - side / 2 + 0.002, side / 2))
    this.payloadLabel.position.set(m.position.x, m.position.y, this._bounds([m]).hi.z + 0.012)
  }

  setTurntable(on) {
    this.controls.autoRotate = !!on && !this.userMoved
  }

  // Aim the camera at the robot. ``fit`` also chooses the distance and the side (first frame, "reset view").
  frame(fit = true, { distance = null, azimuth = null } = {}) {
    if (!this.meshes.length) return
    this.scene.updateMatrixWorld(true)
    const { lo, hi } = this._bounds()
    const size = hi.clone().sub(lo).length()
    this._size = size
    const center = this.tilt.localToWorld(lo.clone().add(hi).multiplyScalar(0.5))
    const ramp = !!this.meta.tilt_deg
    center.y *= 0.85 // aim a little low so the floor and the shadow are in frame
    if (ramp) center.y -= size * 0.16 // and lower still for a ramp: its side wall carries the angle
    this.controls.target.copy(center)
    if (fit) {
      // Fit the robot's bounding sphere in the narrower of the two view angles (tall phone panels too).
      const v = (this.camera.fov * Math.PI) / 360
      const h = Math.atan(Math.tan(v) * this.camera.aspect)
      const k = Math.sin(v) / Math.sin(Math.min(v, h))
      const dist = Math.max(size * (distance || (ramp ? 2.75 : 2.15)) * k, 0.3)
      const dir = new Vector3(...(azimuth || (ramp ? VIEW_SIDE : VIEW_FRONT))).normalize()
      this.camera.position.copy(center).addScaledVector(dir, dist)
      this.userMoved = false
    }
    this._aimLight(center, size)
    this.controls.update()
  }

  _track() {
    // Follow the whole robot (its bounding-box centre), not one part, so nothing leaves the frame.
    const { lo, hi } = this._bounds()
    const p = this.tilt.localToWorld(lo.clone().add(hi).multiplyScalar(0.5))
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
    this._fitLabels()
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
    this._clearTip()
    this._clearTerrain()
    disposeTree(this.scene)
    if (this.envMap) this.envMap.dispose()
    this.renderer.dispose()
    this.renderer.forceContextLoss()
    this.renderer.domElement.remove()
  }
}
