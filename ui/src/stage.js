// The 3D stage: one three.js scene per viewer. Robots arrive as MuJoCo geometry (metres, z up, x forward)
// and per-frame poses [x, y, z, qw, qx, qy, qz]; the stage turns that into soft, rounded parts on a
// shadowed floor, draws the scene's terrain (ramp tilt, bars, slippery tint, push arrow, payload) and
// keeps the camera on the robot. No app markup is touched; everything lives in the container it is given.
// Named imports (not `import * as THREE`) so the bundler can drop the parts of three.js the stage does not use.
import {
  ACESFilmicToneMapping, ArrowHelper, Box3, BufferGeometry, CapsuleGeometry, CircleGeometry, Color, CylinderGeometry,
  DirectionalLight, EdgesGeometry, Group, HemisphereLight, Line, LineBasicMaterial, LineDashedMaterial, LineSegments,
  Mesh, MeshPhysicalMaterial, MeshStandardMaterial, PCFSoftShadowMap, PerspectiveCamera, PlaneGeometry, Scene,
  ShaderMaterial, ShadowMaterial, SphereGeometry, SRGBColorSpace, Vector3, WebGLRenderer,
} from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'

const THREE = {
  ACESFilmicToneMapping, ArrowHelper, Box3, BufferGeometry, CapsuleGeometry, CircleGeometry, Color, CylinderGeometry,
  DirectionalLight, EdgesGeometry, Group, HemisphereLight, Line, LineBasicMaterial, LineDashedMaterial, LineSegments,
  Mesh, MeshPhysicalMaterial, MeshStandardMaterial, PCFSoftShadowMap, PerspectiveCamera, PlaneGeometry, Scene,
  ShaderMaterial, ShadowMaterial, SphereGeometry, SRGBColorSpace, Vector3, WebGLRenderer,
}
const UP = new THREE.Vector3(0, 1, 0)

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

function partGeometry(shape, size) {
  if (shape === 'box') {
    const [x, y, z] = size
    const r = Math.min(x, y, z) * 0.22
    return new RoundedBoxGeometry(x, y, z, 4, r)
  }
  if (shape === 'cylinder') {
    const g = new THREE.CylinderGeometry(size[0], size[0], size[1], 40, 1)
    g.rotateX(Math.PI / 2) // MuJoCo cylinders run along their local z
    return g
  }
  if (shape === 'capsule') {
    const g = new THREE.CapsuleGeometry(size[0], size[1] || size[0], 8, 24)
    g.rotateX(Math.PI / 2)
    return g
  }
  return new THREE.SphereGeometry(size[0], 32, 20)
}

export class Stage {
  constructor(container, { interactive = true } = {}) {
    this.container = container
    this.dark = isDarkTheme(container)
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.05
    this.renderer.setClearColor(0x000000, 0) // the app's own background shows through
    this.renderer.domElement.className = 'tb-canvas'
    container.appendChild(this.renderer.domElement)

    this.scene = new THREE.Scene()
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.01, 50)
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
    this.world = new THREE.Group()
    this.world.rotation.x = -Math.PI / 2
    this.scene.add(this.world)
    this.tilt = new THREE.Group()
    this.world.add(this.tilt)
    this.floor = new THREE.Group()
    this.tilt.add(this.floor)
    this.terrain = new THREE.Group()
    this.tilt.add(this.terrain)
    this.robot = new THREE.Group()
    this.tilt.add(this.robot)
    this._floor()

    this.meshes = []
    this.meta = {}
    this.follow = true
    this.userMoved = false
    this.target = new THREE.Vector3()
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
    const sky = this.dark ? 0xb9c6ff : 0xffffff
    const ground = this.dark ? 0x1a1d24 : 0xd9d4cc
    this.hemi = new THREE.HemisphereLight(sky, ground, this.dark ? 1.1 : 1.35)
    this.scene.add(this.hemi)
    const key = new THREE.DirectionalLight(0xffffff, this.dark ? 2.2 : 2.6)
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
    const rim = new THREE.DirectionalLight(this.dark ? 0x8fb4ff : 0xfff1dc, this.dark ? 0.9 : 0.6)
    rim.position.set(-1.6, 1.1, -1.4)
    this.scene.add(rim)
  }

  _floor() {
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(8, 8),
      new THREE.ShadowMaterial({ opacity: this.dark ? 0.45 : 0.22 }))
    shadow.receiveShadow = true
    this.floor.add(shadow)
    // A procedural floor: a soft disc plus 5 cm / 20 cm grid lines, all fading out radially.
    const SPAN = 1.6 // metres
    const grid = new THREE.Mesh(new THREE.PlaneGeometry(SPAN, SPAN), new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: {
        uColor: { value: new THREE.Color(this.dark ? 0xffffff : 0x26303c) },
        uDisc: { value: this.dark ? 0.06 : 0.07 },
        uMinor: { value: this.dark ? 0.12 : 0.13 },
        uMajor: { value: this.dark ? 0.26 : 0.26 },
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
          float a = uDisc * (1.0 - smoothstep(0.0, 0.75, r));
          a += uMinor * lines(vPos, 0.05) * fade;
          a = max(a, uMajor * lines(vPos, 0.2) * fade);
          if (a < 0.002) discard;
          gl_FragColor = vec4(uColor, a);
        }`,
    }))
    grid.position.z = 0.0006
    this.grid = grid
    this.floor.add(grid)
    this.slick = new THREE.Mesh(new THREE.CircleGeometry(1.1, 64),
      new THREE.MeshPhysicalMaterial({ color: 0x5fb7ff, transparent: true, opacity: 0.16, roughness: 0.05,
        metalness: 0, clearcoat: 1, clearcoatRoughness: 0.05, depthWrite: false }))
    this.slick.position.z = 0.001
    this.slick.visible = false
    this.floor.add(this.slick)
  }

  setRobot(parts) {
    for (const m of this.meshes) {
      this.robot.remove(m)
      m.geometry.dispose()
      m.material.dispose()
    }
    this.meshes = parts.map((p) => {
      const color = new THREE.Color(p.color || '#9aa4b2')
      const mat = new THREE.MeshPhysicalMaterial({ color, roughness: 0.48, metalness: 0.04, clearcoat: 0.35,
        clearcoatRoughness: 0.4, sheen: 0.2 })
      const mesh = new THREE.Mesh(partGeometry(p.shape, p.size_m), mat)
      mesh.castShadow = true
      mesh.receiveShadow = true
      mesh.name = p.name
      this.robot.add(mesh)
      return mesh
    })
    this.root = this.meshes[0]
  }

  setPose(frame) {
    if (!frame) return
    for (let i = 0; i < this.meshes.length && i < frame.length; i++) {
      const [x, y, z, qw, qx, qy, qz] = frame[i]
      this.meshes[i].position.set(x, y, z)
      this.meshes[i].quaternion.set(qx, qy, qz, qw)
    }
    this._updatePayload(frame)
    if (this.follow && this.root) this._track(false)
  }

  setMeta(meta = {}) {
    this.meta = meta
    while (this.terrain.children.length) {
      const c = this.terrain.children.pop()
      c.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose() })
    }
    const tilt = (meta.tilt_deg || 0) * Math.PI / 180
    this.tilt.rotation.y = -tilt // the floor rises toward +x (the robot faces uphill)
    this.slick.visible = meta.floor === 'slippery'
    if (this.levelLine) {
      this.world.remove(this.levelLine)
      this.levelLine.geometry.dispose()
      this.levelLine.material.dispose()
      this.levelLine = null
    }
    if (tilt) {
      // Make the slope legible: a tinted ramp surface, its level reference, and an uphill arrow.
      const ramp = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 0.5), new THREE.MeshStandardMaterial({
        color: 0xd9a441, transparent: true, opacity: this.dark ? 0.16 : 0.2, roughness: 0.9, depthWrite: false }))
      ramp.position.set(0.3, 0, 0.0004)
      this.terrain.add(ramp)
      const edge = new THREE.LineSegments(new THREE.EdgesGeometry(ramp.geometry),
        new THREE.LineBasicMaterial({ color: 0xd9a441, transparent: true, opacity: 0.7 }))
      edge.position.copy(ramp.position)
      this.terrain.add(edge)
      const up = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(-0.05, -0.2, 0.002), 0.4,
        0xd9a441, 0.05, 0.03)
      this.terrain.add(up)
      // A level line from the ramp's low end, outside the tilted group, shows the angle against horizontal.
      const level = new THREE.Line(new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-0.3, -0.25, 0), new THREE.Vector3(0.9, -0.25, 0)]),
      new THREE.LineDashedMaterial({ color: this.dark ? 0xffffff : 0x26303c, dashSize: 0.02, gapSize: 0.015,
        transparent: true, opacity: 0.45 }))
      level.computeLineDistances()
      this.levelLine = level
      this.world.add(level)
    }
    for (const b of meta.boxes || []) {
      const [hx, hy, hz] = b.half
      const bar = new THREE.Mesh(new RoundedBoxGeometry(hx * 2, Math.min(hy, 0.18) * 2, hz * 2, 3, Math.min(hx, hz) * 0.3),
        new THREE.MeshStandardMaterial({ color: this.dark ? 0xc9a46a : 0xb88a4a, roughness: 0.7 }))
      bar.position.set(...b.center)
      bar.castShadow = bar.receiveShadow = true
      this.terrain.add(bar)
    }
    this.arrow = null
    if (meta.push) {
      const v = meta.push.vector || [1, 0]
      const dir = new THREE.Vector3(v[0], v[1], 0).normalize()
      this.arrow = new THREE.ArrowHelper(dir, new THREE.Vector3(), 0.12, 0xff5a4f, 0.04, 0.025)
      this.arrow.visible = false
      this.terrain.add(this.arrow)
    }
    this.payload = null
    if (meta.payload && meta.payload.part) {
      const r = 0.008 + Math.cbrt(Math.max(meta.payload.grams, 1)) * 0.0022
      this.payload = new THREE.Mesh(new THREE.SphereGeometry(r, 24, 16),
        new THREE.MeshStandardMaterial({ color: 0x7c8796, roughness: 0.3, metalness: 0.6 }))
      this.payload.castShadow = true
      this.payloadIndex = this.meshes.findIndex((m) => m.name === meta.payload.part)
      this.terrain.add(this.payload)
    }
  }

  setTime(t) {
    if (!this.arrow || !this.meta.push || !this.root) return
    const p = this.meta.push
    const on = t >= p.at_s - 0.05 && t <= p.at_s + Math.max(p.duration_s, 0.5)
    this.arrow.visible = on
    if (on) {
      const dir = new THREE.Vector3(p.vector[0], p.vector[1], 0).normalize()
      const at = this.root.position.clone().addScaledVector(dir, -0.16)
      this.arrow.position.copy(at)
    }
  }

  _updatePayload(frame) {
    if (!this.payload || this.payloadIndex < 0) return
    const [x, y, z] = frame[this.payloadIndex]
    this.payload.position.set(x, y, z - 0.025)
  }

  _robotBox() {
    const box = new THREE.Box3()
    for (const m of this.meshes) box.expandByObject(m)
    return box
  }

  // Aim the camera at the robot. ``fit`` also chooses the distance (first frame or "reset view").
  frame(fit = true) {
    this.scene.updateMatrixWorld(true)
    const box = this._robotBox()
    if (box.isEmpty()) return
    const center = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3()).length()
    this._size = size
    center.y *= 0.85 // aim a little low so the floor and the shadow are in frame
    this.target.copy(center)
    this.controls.target.copy(center)
    if (fit) {
      const dist = Math.max(size * 2.35, 0.3)
      // 3/4 view from the front right, slightly above (robot faces MuJoCo +x = three +x).
      const dir = new THREE.Vector3(0.78, 0.5, 0.72).normalize()
      this.camera.position.copy(center).addScaledVector(dir, dist)
      this.userMoved = false
    }
    this._aimLight(center, size)
    this.controls.update()
  }

  _track() {
    // Follow the whole robot (its bounding-box centre), not one part, so nothing leaves the frame.
    this.scene.updateMatrixWorld(true)
    const box = this._robotBox()
    if (box.isEmpty()) return
    const p = box.getCenter(new THREE.Vector3())
    p.y = this.controls.target.y + (p.y - this.controls.target.y) * 0.3
    const delta = p.sub(this.controls.target)
    delta.y *= 0.3
    const step = delta.multiplyScalar(0.12)
    this.controls.target.add(step)
    this.camera.position.add(step)
    // Keep the faded grid under a walking robot, snapped to whole 20 cm cells so it never slides.
    this.grid.position.x = Math.round(this.root.position.x / 0.2) * 0.2
    this.grid.position.y = Math.round(this.root.position.y / 0.2) * 0.2
    this._aimLight(this.controls.target, this._size || 0.4)
  }

  _aimLight(center, size) {
    this.key.target.position.copy(center)
    this.key.position.copy(center).add(new THREE.Vector3(1.2, 2.4, 1.6).normalize().multiplyScalar(2.2))
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

  snapshot() {
    return this.renderer.domElement.toDataURL('image/png')
  }

  dispose() {
    this._running = false
    cancelAnimationFrame(this._raf)
    this._resize.disconnect()
    this.controls.dispose()
    this.scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose()
      if (o.material) {
        if (o.material.alphaMap) o.material.alphaMap.dispose()
        o.material.dispose()
      }
    })
    this.renderer.dispose()
    this.renderer.forceContextLoss()
    this.renderer.domElement.remove()
  }
}

export { UP }
