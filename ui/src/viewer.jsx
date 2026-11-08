// React wrapper around the three.js stage, plus one shared player so several views replay in lockstep.
import { useEffect, useRef, useState, useCallback } from 'react'
import { Stage } from './stage.js'

// When a recorded run tips: the simulator's fall time if it gave one, else the first frame whose body
// (the first part) is tilted more than 50 degrees from upright.
export function tipTime(trace, result) {
  if (!trace || !result || !result.fell) return null
  if (result.fell_at_s != null) return result.fell_at_s
  for (let i = 0; i < trace.frames.length; i++) {
    const [, , , , qx, qy] = trace.frames[i][0]
    const upZ = 1 - 2 * (qx * qx + qy * qy) // z of the body's up axis
    if (upZ < Math.cos((50 * Math.PI) / 180)) return i / trace.fps
  }
  return (trace.frames.length - 1) / trace.fps
}

export function Viewer3D({ parts, frames, pose, meta, look, frameIndex = 0, time = 0, label, sublabel, tone, height = 340,
  interactive = true, onStage, tipAt = null }) {
  const box = useRef(null)
  const stage = useRef(null)
  const [error, setError] = useState(null)
  const tipped = tipAt != null && time >= tipAt

  useEffect(() => {
    try {
      stage.current = new Stage(box.current, { interactive })
      if (onStage) onStage(stage.current)
    } catch (err) {
      setError('3D view unavailable: ' + ((err && err.message) || err))
    }
    return () => {
      if (stage.current) stage.current.dispose()
      stage.current = null
    }
  }, [])

  useEffect(() => {
    const s = stage.current
    if (!s || !parts) return
    s.setRobot(parts, look || {})
    s.setMeta(meta || {})
    s.setPose(frames ? frames[0] : pose)
    s.frame(true)
  }, [parts, meta, frames, pose, look])

  useEffect(() => {
    const s = stage.current
    if (!s || !frames || !frames.length) return
    s.setPose(frames[Math.min(frameIndex, frames.length - 1)])
    s.setTime(time)
    s.setTip(tipAt != null && time >= tipAt && time < tipAt + 0.8)
  }, [frameIndex, time, frames, tipAt])

  return (
    <div className="tb-viewer" style={{ height }}>
      <div className="tb-viewer-canvas" ref={box} />
      <div className="tb-viewer-tag">SIMULATION</div>
      {tipped ? <div className="tb-viewer-tipped">TIPPED · {tipAt.toFixed(2)} s</div> : null}
      {label ? (
        <div className={'tb-viewer-label' + (tone ? ' tb-tone-' + tone : '')}>
          <span>{label}</span>
          {sublabel ? <small>{sublabel}</small> : null}
        </div>
      ) : null}
      <button type="button" className="tb-viewer-reset" title="Reset view"
        onClick={() => stage.current && stage.current.frame(true)}>⟲</button>
      {error ? <div className="tb-viewer-error">{error}</div> : null}
    </div>
  )
}

// One clock for any number of views: t in seconds, looping, scrubbable.
export function usePlayer(duration, { autoplay = true } = {}) {
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(autoplay)
  const [rate, setRate] = useState(1)
  const last = useRef(null)
  useEffect(() => { setT(0); setPlaying(autoplay) }, [duration])
  useEffect(() => {
    if (!playing || !duration) return undefined
    let raf
    const tick = (now) => {
      if (last.current != null) {
        const dt = Math.min((now - last.current) / 1000, 0.1) * rate
        setT((prev) => {
          const next = prev + dt
          return next > duration + 0.6 ? 0 : next
        })
      }
      last.current = now
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); last.current = null }
  }, [playing, duration, rate])
  const seek = useCallback((v) => { setT(v); }, [])
  return { t: Math.min(t, duration || 0), playing, setPlaying, rate, setRate, seek, duration }
}

export function frameAt(trace, t) {
  if (!trace) return 0
  return Math.max(0, Math.min(trace.frames.length - 1, Math.floor(t * trace.fps)))
}

export function Timeline({ player, marks = [] }) {
  const { t, playing, setPlaying, rate, setRate, seek, duration } = player
  if (!duration) return null
  return (
    <div className="tb-timeline">
      <button type="button" className="tb-icon-btn" onClick={() => setPlaying(!playing)}
        aria-label={playing ? 'Pause' : 'Play'}>{playing ? '❚❚' : '▶'}</button>
      <div className="tb-scrub">
        <input type="range" min={0} max={duration} step={1 / 60} value={t}
          onChange={(e) => { setPlaying(false); seek(parseFloat(e.target.value)) }} />
        {marks.map((m) => (
          <span key={m.label} className="tb-mark" title={m.label}
            style={{ left: `${(Math.min(m.t, duration) / duration) * 100}%` }} />
        ))}
      </div>
      <span className="tb-time">{t.toFixed(2)} / {duration.toFixed(2)} s</span>
      <select className="tb-select tb-select-sm" value={rate} onChange={(e) => setRate(parseFloat(e.target.value))}>
        <option value={0.25}>0.25×</option>
        <option value={0.5}>0.5×</option>
        <option value={1}>1×</option>
        <option value={2}>2×</option>
      </select>
    </div>
  )
}

export function traceDuration(...traces) {
  return Math.max(0, ...traces.filter(Boolean).map((tr) => (tr.frames.length - 1) / tr.fps))
}
