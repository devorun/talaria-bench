import { useEffect, useMemo, useRef, useState } from 'react'
import { api, notify } from '../platform.js'
import { Viewer3D, Timeline, usePlayer, tipLabel, tipMarks, tipTime, traceDuration } from '../viewer.jsx'
import { Button, Chip, ErrorBox, Loading, MODEL_NOTE, useApi, useTrace } from '../ui.jsx'

function Photo({ robot, version }) {
  const [src, setSrc] = useState(null)
  useEffect(() => {
    let live = true
    setSrc(null)
    api(`/robots/${robot}/photo.json`).then((r) => { if (live && r.ok) setSrc(r.data_url) })
    return () => { live = false }
  }, [robot, version])
  if (!src) return <div className="tb-photo tb-photo-empty"><span className="tb-spinner" /></div>
  return (
    <figure className="tb-photo">
      <img src={src} alt={`${robot}, photo`} />
      <figcaption><Chip tone="green">REAL</Chip> photo of the robot</figcaption>
    </figure>
  )
}

// "Add photo": JPEG/PNG/WebP up to 10 MB, checked again by the backend; only for the user's own robots.
function AddPhoto({ robot, onDone, compact }) {
  const input = useRef(null)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const pick = (e) => {
    const file = e.target.files && e.target.files[0]
    if (!file) return
    if (file.size > 10 * 1024 * 1024) { setRes({ ok: false, error: 'The photo is larger than 10 MB.' }); return }
    const reader = new FileReader()
    reader.onload = async () => {
      setBusy(true)
      const r = await api(`/robots/${robot}/photo`, { method: 'POST', body: { data: String(reader.result) } })
      setBusy(false)
      setRes(r)
      if (r.ok) { notify('Photo added'); onDone() }
    }
    reader.readAsDataURL(file)
    e.target.value = ''
  }
  return (
    <div className={compact ? '' : 'tb-photo tb-photo-add'}>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={pick} />
      <Button busy={busy} onClick={() => input.current && input.current.click()}>{compact ? 'Replace photo' : '＋ Add a photo'}</Button>
      {!compact ? <p className="tb-muted tb-small">Shown next to the 3D model. JPEG, PNG or WebP, up to 10 MB.</p> : null}
      <ErrorBox data={res} />
    </div>
  )
}

function PartsEditor({ detail, onSaved }) {
  const [edits, setEdits] = useState({})
  const [name, setName] = useState(`${detail.robot}_custom`.replace(/_custom_custom$/, '_custom'))
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null)
  useEffect(() => { setEdits({}); setResult(null); setName(`${detail.robot}_custom`) }, [detail.robot])
  const change = (part, key, value) => setEdits((e) => ({ ...e, [part]: { ...(e[part] || {}), [key]: value } }))
  const count = Object.keys(edits).length
  const save = async () => {
    const parts = {}
    for (const [p, ch] of Object.entries(edits)) {
      parts[p] = {}
      if (ch.size != null) parts[p].size = ch.size.split(/[ ,x×]+/).filter(Boolean).map(Number)
      if (ch.mass != null) parts[p].mass = Number(ch.mass)
      if (ch.servo != null) parts[p].servo = ch.servo
    }
    setSaving(true)
    const r = await api(`/robots/${detail.robot}/edit`, { method: 'POST', body: { new_name: name, parts } })
    setSaving(false)
    setResult(r)
    if (r.ok) { notify(`Saved ${r.robot}`); onSaved(r.robot) }
  }
  return (
    <div className="tb-card">
      <div className="tb-card-head">
        <h3>Parts</h3>
        <span className="tb-muted">sizes in cm · masses in g · edits are saved as your own copy</span>
      </div>
      <div className="tb-table-wrap">
        <table className="tb-table">
          <thead><tr><th>Part</th><th>Shape</th><th>Size (cm)</th><th>Mass (g)</th><th>Servo</th></tr></thead>
          <tbody>
            {detail.parts.map((p) => {
              const e = edits[p.name] || {}
              return (
                <tr key={p.name}>
                  <td><span className="tb-swatch" style={{ background: p.color }} />{p.name}</td>
                  <td className="tb-muted">{p.shape}</td>
                  <td><input className="tb-input tb-input-sm" value={e.size ?? p.size.join(' × ')}
                    disabled={!detail.editable} onChange={(ev) => change(p.name, 'size', ev.target.value)} /></td>
                  <td><input className="tb-input tb-input-xs" type="number" value={e.mass ?? p.mass}
                    disabled={!detail.editable} onChange={(ev) => change(p.name, 'mass', ev.target.value)} /></td>
                  <td>{p.servo ? (
                    <select className="tb-select tb-select-sm" value={e.servo ?? p.servo} disabled={!detail.editable}
                      onChange={(ev) => change(p.name, 'servo', ev.target.value)}>
                      {detail.servos.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>) : <span className="tb-muted">–</span>}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="tb-row tb-gap">
        <input className="tb-input" value={name} onChange={(e) => setName(e.target.value)} aria-label="Name of the copy" />
        <Button kind="primary" busy={saving} disabled={!count || !detail.editable} onClick={save}>
          Save as my copy{count ? ` (${count} part${count > 1 ? 's' : ''})` : ''}
        </Button>
      </div>
      <ErrorBox data={result} />
    </div>
  )
}

export function RobotPage({ robot, go, refresh }) {
  const [detail, loading, reload] = useApi(robot ? `/robots/${robot}` : null)
  const [playing, setPlaying] = useState(null)
  const [photoVersion, setPhotoVersion] = useState(0)
  useEffect(() => setPlaying(null), [robot])
  const [trace, traceLoading] = useTrace(playing ? { robot, move: playing } : null)
  const tr = trace && trace.ok ? trace.trace : null
  const player = usePlayer(traceDuration(tr))
  const rest = useMemo(() => detail && detail.ok ? (detail.showcase || detail.render) : null, [detail])
  const restPose = useMemo(() => rest ? rest.parts.map((p) => p.pose) : null, [rest])
  if (!robot) return null
  if (loading && !detail) return <Loading what="Loading robot" />
  if (!detail || !detail.ok) return <ErrorBox data={detail} />
  const s = detail.summary
  return (
    <div className="tb-page">
      <div className="tb-hero">
        <div>
          <h2 title={`spec hash ${detail.spec_hash} (physics only)`}>{detail.title}
            {detail.look && detail.look.badge ? <span className="tb-badge" style={{ '--tb-badge': detail.look.accent }}>{detail.look.badge}</span> : null}
          </h2>
          <p>{detail.role || detail.description}</p>
          <div className="tb-meta-row">
            {detail.family ? <Chip>{detail.family}</Chip> : null}
            <Chip>{s.joints.length} servos</Chip>
            <Chip>{Math.round(s.total_mass_g)} g</Chip>
            <Chip>{s.parts} parts</Chip>
            {detail.base === 'fixed' ? <Chip>fixed base</Chip> : null}
          </div>
        </div>
        <div className="tb-hero-actions">
          <Button onClick={() => go('arena', robot)}>Open in Arena</Button>
          <Button onClick={() => go('bench', robot)}>Report card</Button>
          <Button onClick={() => go('compare', robot)}>Compare designs</Button>
          <Button kind="primary" onClick={() => go('check', robot)}>Check a move</Button>
        </div>
      </div>

      <div className={'tb-split' + (detail.has_photo || detail.source === 'user' ? '' : ' tb-split-single')}>
        <div className="tb-card tb-card-flush">
          <Viewer3D parts={tr ? tr.parts : rest.parts} frames={tr ? tr.frames : null} pose={tr ? null : restPose}
            fps={tr ? tr.fps : 30} meta={trace && trace.ok ? trace.meta : null} look={detail.look}
            tipAt={tr ? tipTime(tr, trace.result) : null} tipWhy={tr ? trace.result.fall_reason : null}
            time={player.t} turntable={!detail.has_photo}
            label={playing ? `move: ${playing}` : 'showcase pose'}
            sublabel={tr ? (trace.result.fell ? tipLabel(trace.result) : 'nominal world, stays up') : 'standing on the floor'}
            tone={tr ? (trace.result.fell ? 'red' : 'green') : null} height={440} />
          {tr ? <Timeline player={player} marks={tipMarks([tr, trace.result])} /> : null}
          {traceLoading ? <div className="tb-overlay-note"><span className="tb-spinner" /> simulating {playing}…</div> : null}
        </div>
        {detail.has_photo ? (
          <div className="tb-photo-col">
            <Photo robot={robot} version={photoVersion} />
            {detail.source === 'user' ? <p className="tb-muted tb-small tb-model-note">{MODEL_NOTE}</p> : null}
            {detail.source === 'user' ? <AddPhoto robot={robot} compact onDone={() => { setPhotoVersion((v) => v + 1); reload(); if (refresh) refresh() }} /> : null}
          </div>
        ) : detail.source === 'user' ? <AddPhoto robot={robot} onDone={() => { setPhotoVersion((v) => v + 1); reload(); if (refresh) refresh() }} /> : null}
      </div>

      <div className="tb-two">
        <div className="tb-card">
          <div className="tb-card-head"><h3>Moves</h3><span className="tb-muted">replay in the nominal simulated world</span></div>
          <div className="tb-list">
            {detail.moves.map((m) => (
              <div key={m.name} className={'tb-list-row' + (playing === m.name ? ' tb-active' : '')}>
                <div>
                  <div className="tb-list-title">{m.name}
                    {m.official ? (
                      <Chip tone={m.official.high <= 0.1 ? 'green' : m.official.falls ? 'red' : 'grey'}
                        title={`95% interval ${(m.official.low * 100).toFixed(0)}–${(m.official.high * 100).toFixed(0)}% · ${m.official.origin || ''}`}>
                        tips {(m.official.rate * 100).toFixed(0)}% · {m.official.worlds} worlds{m.official.quick ? ' · quick' : ''}
                      </Chip>) : null}
                    {m.preflight && m.preflight.startsWith('pass') ? <Chip tone="accent">approved</Chip> : null}
                  </div>
                  <div className="tb-muted">{m.description || ''}{m.duration_s ? ` · ${m.duration_s.toFixed(1)} s` : ''}</div>
                </div>
                <div className="tb-row tb-gap-sm">
                  <Button onClick={() => setPlaying(m.name)}>Simulate</Button>
                  <Button onClick={() => go('check', robot, m.name)}>Check</Button>
                </div>
              </div>
            ))}
          </div>
          {detail.limitations && detail.limitations.length ? (
            <div className="tb-callout tb-tone-grey">
              <strong>Outside the model's scope</strong>
              {detail.limitations.map((l) => <p key={l.scope}>{l.scope}: {l.note}</p>)}
            </div>
          ) : null}
        </div>
        <PartsEditor detail={detail} onSaved={(name) => { reload(); go('robot', name) }} />
      </div>
    </div>
  )
}
