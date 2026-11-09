// Small shared pieces: data hooks, status chips, bars, buttons. Theme-aware through CSS variables only.
import { useEffect, useRef, useState, useCallback } from 'react'
import { api } from './platform.js'

export function useApi(path, deps = []) {
  const [state, setState] = useState({ loading: !!path, data: null })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    if (!path) { setState({ loading: false, data: null }); return undefined }
    let live = true
    setState((s) => ({ loading: true, data: s.data }))
    api(path).then((data) => { if (live) setState({ loading: false, data }) })
    return () => { live = false }
  }, [path, nonce, ...deps])
  return [state.data, state.loading, useCallback(() => setNonce((n) => n + 1), [])]
}

// Start a background job and follow it until it settles.
export function useJob(onDone) {
  const [job, setJob] = useState(null)
  const done = useRef(onDone)
  done.current = onDone
  useEffect(() => {
    if (!job || job.status !== 'running') return undefined
    let live = true
    const timer = setTimeout(async () => {
      const next = await api(`/jobs/${job.id}`)
      if (!live) return
      if (!next.ok) { setJob({ ...job, status: 'failed', log_tail: next.error }); return }
      setJob(next)
      if (next.status === 'done' && done.current) done.current(next)
    }, 1200)
    return () => { live = false; clearTimeout(timer) }
  }, [job])
  const start = useCallback(async (path, body) => {
    setJob({ id: null, status: 'starting', progress: {} })
    const r = await api(path, { method: 'POST', body })
    if (!r.ok) { setJob({ status: 'failed', log_tail: r.error }); return }
    setJob({ id: r.job_id, status: 'running', progress: {} })
  }, [])
  return [job, start]
}

export function useTrace(body) {
  const key = body ? JSON.stringify(body) : null
  const [state, setState] = useState({ loading: false, data: null })
  useEffect(() => {
    if (!key) { setState({ loading: false, data: null }); return undefined }
    let live = true
    setState({ loading: true, data: null })
    api('/trace', { method: 'POST', body: JSON.parse(key) }).then((data) => { if (live) setState({ loading: false, data }) })
    return () => { live = false }
  }, [key])
  return [state.data, state.loading]
}

export const STATUS = {
  green: { label: 'PASS', tone: 'green' },
  amber: { label: 'MIXED', tone: 'amber' },
  red: { label: 'FAIL', tone: 'red' },
  'n/a': { label: 'N/A', tone: 'muted' },
  out_of_scope: { label: 'OUT OF MODEL SCOPE', tone: 'grey' },
}

export function Chip({ tone = 'muted', children, title }) {
  return <span className={'tb-chip tb-tone-' + tone} title={title}>{children}</span>
}

export function Button({ kind = 'default', busy, children, ...rest }) {
  return (
    <button type="button" className={'tb-btn tb-btn-' + kind} disabled={busy || rest.disabled} {...rest}>
      {busy ? <span className="tb-spinner" /> : null}
      {children}
    </button>
  )
}

export function Bar({ value, max = 100, mark, tone, label, right, note }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  const t = tone || (value >= 90 ? 'red' : value >= 70 ? 'amber' : 'green')
  return (
    <div className="tb-barrow">
      <div className="tb-barrow-label">{label}</div>
      <div className="tb-bar">
        <div className={'tb-bar-fill tb-fill-' + t} style={{ width: pct + '%' }} />
        {mark != null ? <div className="tb-bar-mark" style={{ left: (mark / max) * 100 + '%' }} title={`limit ${mark}%`} /> : null}
      </div>
      <div className="tb-barrow-right">{right}</div>
      {note ? <div className="tb-barrow-note">{note}</div> : null}
    </div>
  )
}

export function Progress({ job, label }) {
  if (!job) return null
  const p = job.progress || {}
  const total = p.total || 0
  const pct = total ? Math.round(((p.done || 0) / total) * 100) : 0
  if (job.status === 'failed') {
    return <div className="tb-callout tb-tone-red">The run failed. {job.log_tail ? <pre>{job.log_tail}</pre> : null}</div>
  }
  if (job.status === 'done') return null
  return (
    <div className="tb-progress">
      <div className="tb-progress-head">
        <span><span className="tb-spinner" /> {label || 'Running'}{p.variant ? ` · ${p.variant}` : ''}{p.scene ? ` · ${p.scene}` : ''}</span>
        <span>{total ? `${p.done}/${total} runs · ${pct}%` : 'starting…'}</span>
      </div>
      <div className="tb-bar"><div className="tb-bar-fill tb-fill-accent" style={{ width: pct + '%' }} /></div>
    </div>
  )
}

export function Empty({ children }) {
  return <div className="tb-empty">{children}</div>
}

export function Loading({ what = 'Loading' }) {
  return <div className="tb-empty"><span className="tb-spinner" /> {what}…</div>
}

export function ErrorBox({ data }) {
  if (!data || data.ok !== false) return null
  return (
    <div className="tb-callout tb-tone-red">
      <strong>{data.error}</strong>
      {data.problems && data.problems.length ? <ul>{data.problems.map((p) => <li key={p}>{p}</li>)}</ul> : null}
    </div>
  )
}

export function pct(x, digits = 0) {
  return x == null ? '–' : `${(x * 100).toFixed(digits)}%`
}

export function fmt(v, unit) {
  if (v == null) return '–'
  if (unit === 'x weight' && v > PUSH_MAX) return '>1'
  const s = Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2)
  return s.replace(/\.?0+$/, '') || '0'
}

// One format per unit, everywhere: distances with one decimal, angles and grams as short numbers.
const PUSH_MAX = 1 // the largest push the bench applies, in body weights; a larger value means "never tipped"
const cm = (v) => Math.abs(v).toFixed(1)
const short = (v) => (Math.round(v * 10) / 10).toFixed(1).replace(/\.0$/, '')

// A scene's main metric in plain words; negative distances say what actually happened.
export function human(sceneId, v, unit) {
  if (v == null) return '–'
  const id = sceneId || ''
  if (id.startsWith('obstacle')) return v >= 0 ? `${cm(v)} cm past the bar` : `stopped ${cm(v)} cm before the bar`
  if (id.startsWith('ramp')) return v >= 0 ? `climbed ${cm(v)} cm` : `slid ${cm(v)} cm back down`
  if (id === 'flat' || id === 'slippery') return v >= 0 ? `${cm(v)} cm forward` : `${cm(v)} cm backwards`
  if (id === 'push') return v > PUSH_MAX ? 'no tip up to 1× weight' : `tips at ${fmt(v)}× weight`
  if (id === 'payload') return v < 0 ? 'no safe payload' : `${short(v)} g safe payload`
  if (id.startsWith('move:')) return `${short(v)}° body tilt`
  return `${fmt(v, unit)} ${unit || ''}`.trim()
}

export function RobotPicker({ robots, value, onChange }) {
  return (
    <select className="tb-select" value={value || ''} onChange={(e) => onChange(e.target.value)}>
      {(robots || []).map((r) => <option key={r.name} value={r.name}>{r.title || r.name}</option>)}
    </select>
  )
}
