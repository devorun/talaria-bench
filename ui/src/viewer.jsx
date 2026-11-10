// React wrapper around the three.js stage, plus one shared player so several views replay in lockstep.
import { useEffect, useRef, useState, useCallback } from 'react'
import { Stage } from './stage.js'

const TIP_FLASH_S = 0.8

// When a recorded run tips: the simulator's fall time if it gave one, else the first frame whose body
// (the first part) is tilted more than 50 degrees from upright.
// "tipped at 1.20 s", or for a robot whose servos cannot hold it up (it goes down while settling, at 0.00 s).
export function tipLabel(result, verb = 'tipped') {
  if (result && result.fell_at_s === 0) return 'cannot stand: collapses before it moves'
  return `${verb} at ${result && result.fell_at_s != null ? result.fell_at_s.toFixed(2) : '?'} s`
}

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

// Timeline marks for the runs on screen: where each one tips.
export function tipMarks(...runs) {
  const marks = []
  for (const [trace, result, label] of runs) {
    const t = tipTime(trace, result)
    if (t != null && !marks.some((m) => Math.abs(m.t - t) < 0.02)) marks.push({ t, label: label || 'tips', tone: 'red' })
  }
  return marks
}

export function Viewer3D({ parts, frames, pose, meta, look, time = 0, fps = 30, label, sublabel, tone, height = 340,
  interactive = true, onStage, tipAt = null, tipWhy = null, turntable = false }) {
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
    s.setPose(frames ? frames[0] : pose)
    s.setMeta(meta || {}) // after the first pose: the course is laid out around the robot
    s.frame(true)
  }, [parts, meta, frames, pose, look])

  useEffect(() => {
    const s = stage.current
    if (!s || !frames || !frames.length) return
    // Blend between recorded frames so the replay is smooth at any display rate and in slow motion.
    const f = Math.max(0, Math.min(frames.length - 1, time * fps))
    const i = Math.floor(f)
    s.setPoseBlend(frames[i], frames[Math.min(i + 1, frames.length - 1)], f - i)
    s.setTime(time)
    s.setTip(tipAt != null && time >= tipAt ? (time < tipAt + TIP_FLASH_S ? 1 : 2) : 0, tipWhy)
  }, [time, frames, tipAt, tipWhy, fps])

  useEffect(() => {
    if (stage.current) stage.current.setTurntable(turntable && !frames)
  }, [turntable, frames, parts])

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
      <button type="button" className="tb-viewer-reset" title="Reset view" aria-label="Reset view"
        onClick={() => stage.current && stage.current.frame(true)}>
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3 8a5 5 0 1 0 1.6-3.7M3 2.5v2.3h2.3"
          fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
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

const RATES = [0.25, 0.5, 1, 2]

export function Timeline({ player, marks = [] }) {
  const { t, playing, setPlaying, rate, setRate, seek, duration } = player
  if (!duration) return null
  const at = (v) => `${(Math.min(Math.max(v, 0), duration) / duration) * 100}%`
  return (
    <div className="tb-timeline">
      <button type="button" className="tb-icon-btn" onClick={() => setPlaying(!playing)}
        aria-label={playing ? 'Pause' : 'Play'}>
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          {playing ? <path d="M2.5 1.5h2.4v9H2.5zM7.1 1.5h2.4v9H7.1z" fill="currentColor" />
            : <path d="M3 1.3v9.4L10.4 6z" fill="currentColor" />}
        </svg>
      </button>
      <div className="tb-scrub">
        <div className="tb-scrub-track"><div className="tb-scrub-fill" style={{ width: at(t) }} /></div>
        {marks.map((m) => (
          <span key={m.label + m.t} className={'tb-mark tb-mark-' + (m.tone || 'accent')} style={{ left: at(m.t) }}>
            <i>{m.label}</i>
          </span>
        ))}
        <input type="range" min={0} max={duration} step={1 / 120} value={t} aria-label="Replay position"
          onChange={(e) => { setPlaying(false); seek(parseFloat(e.target.value)) }} />
      </div>
      <span className="tb-time">{t.toFixed(2)} <small>/ {duration.toFixed(2)} s</small></span>
      <div className="tb-seg tb-rates" role="group" aria-label="Playback speed">
        {RATES.map((r) => (
          <button key={r} type="button" className={'tb-seg-btn' + (rate === r ? ' tb-active' : '')} aria-pressed={rate === r}
            title={r < 1 ? 'Slow motion' : r > 1 ? 'Fast' : 'Real time'} onClick={() => setRate(r)}>{r}×</button>
        ))}
      </div>
    </div>
  )
}

export function traceDuration(...traces) {
  return Math.max(0, ...traces.filter(Boolean).map((tr) => (tr.frames.length - 1) / tr.fps))
}
