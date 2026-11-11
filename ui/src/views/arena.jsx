// Arena: one robot (and at most one variant of it) on one scene, quick run (10 worlds), replayed side by side in the
// same world with the terrain drawn, and a results table underneath. Same jobs, traces and viewer as the report
// card and the compare page; nothing here touches the physics or the gate.
import { useEffect, useMemo, useState } from 'react'
import { Viewer3D, Timeline, usePlayer, tipMarks, tipTime, traceDuration } from '../viewer.jsx'
import { Button, Chip, ErrorBox, Loading, Progress, STATUS, human, pct, useApi, useJob, useTrace } from '../ui.jsx'

const ICON = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }
const Svg = ({ children }) => <svg viewBox="0 0 40 28" width="40" height="28" aria-hidden="true" {...ICON}>{children}</svg>

const SCENES = [
  { id: 'flat', title: 'Flat floor', blurb: 'Walk straight on level ground.',
    icon: <Svg><path d="M3 21 H37" /><circle cx="14" cy="15" r="3" /><path d="M22 15 H32 M29 12 L32 15 L29 18" /></Svg> },
  { id: 'ramp_5', title: 'Ramp 5°', blurb: 'A gentle slope uphill.',
    icon: <Svg><path d="M3 22 H37 L37 17 Z" /><path d="M10 22 A8 8 0 0 0 7 20" /></Svg> },
  { id: 'ramp_10', title: 'Ramp 10°', blurb: 'A real hill for a small robot.',
    icon: <Svg><path d="M3 22 H37 L37 11 Z" /><path d="M13 22 A10 10 0 0 0 11 18" /></Svg> },
  { id: 'ramp_15', title: 'Ramp 15°', blurb: 'Steep: most hobby robots slide.',
    icon: <Svg><path d="M3 22 H37 L37 5 Z" /><path d="M16 22 A13 13 0 0 0 14 17" /></Svg> },
  { id: 'obstacle_1cm', title: 'Bar 1 cm', blurb: 'Step over a 1 cm bar.',
    icon: <Svg><path d="M3 22 H37" /><rect x="19" y="18" width="5" height="4" /></Svg> },
  { id: 'obstacle_2cm', title: 'Bar 2 cm', blurb: 'Step over a 2 cm bar.',
    icon: <Svg><path d="M3 22 H37" /><rect x="19" y="14" width="5" height="8" /></Svg> },
  { id: 'push', title: 'Push', blurb: 'A shove from the side: does it stay up?',
    icon: <Svg><path d="M3 22 H37" /><rect x="22" y="10" width="9" height="12" rx="2" /><path d="M5 16 H17 M13 12 L17 16 L13 20" /></Svg> },
  { id: 'slippery', title: 'Slippery', blurb: 'Low friction, like a polished table.',
    icon: <Svg><path d="M3 22 H37" /><path d="M7 16 Q10 12 13 16 T19 16 T25 16 T31 16" /></Svg> },
  { id: 'payload', title: 'Payload', blurb: 'How much can the arm lift?',
    icon: <Svg><path d="M5 22 H20 M12 22 V14 L26 8" /><rect x="25" y="9" width="9" height="8" rx="1.5" /></Svg> },
]
const SCENE_BY_ID = Object.fromEntries(SCENES.map((s) => [s.id, s]))

function variantSet({ scale, mass, servo }) {
  const set = {}
  if (Math.abs(scale - 1) > 1e-6) set['@scale'] = scale
  if (mass !== '' && Number(mass) > 0) set['@mass_total'] = Number(mass)
  if (servo) set['parts.*.joint.servo'] = servo
  return set
}

function variantName({ scale, mass, servo }) {
  const bits = []
  if (Math.abs(scale - 1) > 1e-6) bits.push(`×${scale.toFixed(2).replace(/0$/, '')} size`)
  if (mass !== '' && Number(mass) > 0) bits.push(`${Math.round(Number(mass))} g`)
  if (servo) bits.push(servo)
  return bits.join(' · ')
}

// The world to replay: the median world, the worst world of the first robot, or a world where the two disagree.
function worldChoices(result, names, scene) {
  const base = result.cards.base
  const median = base && base.metric && base.metric.median_seed != null ? [base.metric.median_seed] : [0]
  const worst = base && base.metric && base.metric.worst && base.metric.worst.seed != null ? [base.metric.worst.seed] : []
  const out = result.outcomes || {}
  const passed = (n, seed) => {
    const hit = (out[n] || []).find(([s]) => s === seed)
    return hit ? hit[1] : null
  }
  const differ = []
  for (const [seed] of out.base || []) {
    const vals = names.map((n) => passed(n, seed))
    if (vals.length > 1 && vals.some((v) => v) && vals.some((v) => !v)) differ.push(seed)
  }
  return { median, worst, differ }
}

const MODES = [['median', 'Median world'], ['worst', 'Worst world'], ['differ', 'Where they differ']]

function Replay({ robot, jobId, scene, names, labels, result }) {
  const choices = useMemo(() => worldChoices(result, names, scene), [result, names, scene])
  const [mode, setMode] = useState('median')
  const [idx, setIdx] = useState(0)
  const list = choices[mode].length ? choices[mode] : choices.median
  const seed = list[Math.min(idx, list.length - 1)]
  const traces = names.map((n) => useTrace({ robot, scene, seed, ...(n === 'base' ? {} : { job_id: jobId, variant: n }) }))
  const ok = traces.map(([d]) => (d && d.ok ? d : null))
  const player = usePlayer(traceDuration(...ok.map((d) => d && d.trace)))
  return (
    <div className="tb-card tb-arena-replay">
      <div className="tb-card-head">
        <h3>{SCENE_BY_ID[scene] ? SCENE_BY_ID[scene].title : scene}: world {seed}{names.length > 1 ? ', side by side' : ''}</h3>
        <div className="tb-row tb-gap-sm tb-wrap">
          <div className="tb-seg" role="tablist">
            {MODES.filter(([m]) => m !== 'differ' || names.length > 1).map(([m, label]) => (
              <button key={m} type="button" className={'tb-seg-btn' + (mode === m ? ' tb-active' : '')}
                disabled={!choices[m].length} onClick={() => { setMode(m); setIdx(0) }}>
                {label} <span className="tb-seg-count">{choices[m].length}</span>
              </button>
            ))}
          </div>
          {list.length > 1 ? (
            <Button onClick={() => setIdx((idx + 1) % list.length)}>Next world ({Math.min(idx, list.length - 1) + 1}/{list.length})</Button>
          ) : null}
        </div>
      </div>
      <div className={'tb-grid-views tb-views-' + names.length}>
        {names.map((n, i) => {
          const d = ok[i]
          if (!d) return <div key={n} className="tb-viewer tb-viewer-wait" style={{ height: 380 }}><span className="tb-spinner" /> {labels[n]}…</div>
          const r = d.result || {}
          return (
            <Viewer3D key={n} parts={d.trace.parts} frames={d.trace.frames} fps={d.trace.fps} meta={d.meta} look={d.look}
              tipAt={tipTime(d.trace, r)} tipWhy={r.reason} time={player.t} height={380}
              label={labels[n]} sublabel={r.passed ? `passed · ${human(scene, r.metric)}` : `${r.reason || 'failed'} · ${human(scene, r.metric)}`}
              tone={r.passed ? 'green' : 'red'} />
          )
        })}
      </div>
      <Timeline player={player} marks={tipMarks(...ok.map((d, i) => [d && d.trace, d && d.result, `${labels[names[i]]} tips`]))} />
    </div>
  )
}

function ResultsTable({ scene, names, labels, cards }) {
  const rows = names.map((n) => ({ n, c: cards[n] }))
  if (rows.some(({ c }) => !c || c.applicable === false)) {
    const bad = rows.find(({ c }) => !c || c.applicable === false)
    return <div className="tb-callout tb-tone-amber">This scene does not apply to {labels[bad.n]}{bad.c && bad.c.note ? `: ${bad.c.note}` : '.'}</div>
  }
  return (
    <div className="tb-card">
      <div className="tb-card-head"><h3>Results</h3><Chip>{rows[0].c.runs} worlds · same seeds for both</Chip></div>
      <div className="tb-table-wrap">
        <table className="tb-table tb-table-arena">
          <thead><tr><th>Robot</th><th>Pass rate</th><th>Distance (median)</th><th>Tipped</th><th>Worst world</th></tr></thead>
          <tbody>
            {rows.map(({ n, c }) => {
              const st = STATUS[c.status] || STATUS['n/a']
              const reasons = Object.entries(c.failure_reasons || {})
              return (
                <tr key={n}>
                  <th scope="row">{labels[n]}</th>
                  <td><span className={'tb-dot tb-fill-' + st.tone} /> <b>{pct(c.pass_rate)}</b> <span className="tb-muted">{c.passed}/{c.runs}</span></td>
                  <td>{c.metric ? human(scene, c.metric.median, c.metric.unit) : '–'}</td>
                  <td>{c.falls ? <Chip tone="red">{c.falls} of {c.runs}</Chip> : <Chip tone="green">none</Chip>}
                    {reasons.length ? <span className="tb-muted tb-small"> {reasons.map(([why, k]) => `${why} ×${k}`).join(', ')}</span> : null}</td>
                  <td>{c.metric && c.metric.worst ? human(scene, c.metric.worst.value, c.metric.unit) : '–'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ArenaPage({ robot }) {
  const [detail] = useApi(robot ? `/robots/${robot}` : null)
  const [tpl] = useApi('/templates')
  const [withVariant, setWithVariant] = useState(true)
  const [scale, setScale] = useState(1.3)
  const [mass, setMass] = useState('')
  const [servo, setServo] = useState('')
  const [scene, setScene] = useState('ramp_10')
  const [run, setRun] = useState(null)
  const [job, start] = useJob()
  useEffect(() => { setRun(null) }, [robot])
  if (!robot) return null
  if (!detail || !detail.ok) return detail ? <ErrorBox data={detail} /> : <Loading what="Loading robot" />
  const baseMass = Math.round(detail.summary.total_mass_g)
  const knobs = { scale, mass, servo }
  const set = variantSet(knobs)
  const hasVariant = withVariant && Object.keys(set).length > 0
  const name = variantName(knobs)
  const running = job && (job.status === 'running' || job.status === 'starting')
  const simulate = () => {
    // One robot alone is a compare with an unchanged copy (shown once): a /bench run would be saved as the robot's
    // newest report and replace its full report card with this one scene.
    setRun({ robot, scene, hasVariant, name })
    start('/compare', { robot, scenes: [scene], quick: true, variants: [hasVariant ? { name, set } : { name: 'same', set: { '@scale': 1 } }] })
  }
  const done = job && job.status === 'done' && run && run.robot === robot && job.result
  let view = null
  if (done) {
    const res = job.result
    const names = run.hasVariant ? ['base', run.name] : ['base']
    const labels = { base: detail.title, [run.name || 'x']: run.name ? `${detail.title} · ${run.name}` : '' }
    const cards = {}
    const outcomes = {}
    for (const n of names) {
      cards[n] = ((res.reports && res.reports[n] && res.reports[n].scenes) || []).find((c) => c.id === run.scene)
    }
    const row = (res.rows || []).find((r) => r.scene === run.scene)
    Object.assign(outcomes, row ? row.outcomes : {})
    view = { names, labels, cards, result: { cards, outcomes } }
  }
  return (
    <div className="tb-page">
      <div className="tb-hero">
        <div>
          <h2>Arena</h2>
          <p>Put a robot, and one changed version of it, on the same scene. Both run on exactly the same randomized
            worlds, then replay side by side. Every number is a simulation result.</p>
        </div>
      </div>

      <div className="tb-card tb-arena-setup">
        <div className="tb-card-head"><h3>1 · The robots</h3><span className="tb-muted">pick the robot in the header</span></div>
        <div className="tb-arena-robots">
          <div className="tb-arena-robot">
            <Chip tone="muted">A</Chip>
            <div><b>{detail.title}</b><div className="tb-muted tb-small">{detail.summary.joints.length} servos · {baseMass} g · as designed</div></div>
          </div>
          <label className="tb-toggle"><input type="checkbox" checked={withVariant} onChange={(e) => setWithVariant(e.target.checked)} /> add a changed version</label>
          {withVariant ? (
            <div className="tb-arena-robot tb-arena-variant">
              <Chip tone="accent">B</Chip>
              <div className="tb-row tb-gap tb-wrap">
                <label className="tb-field">Size ×{scale.toFixed(2)}
                  <input type="range" min="0.6" max="1.8" step="0.05" value={scale} onChange={(e) => setScale(Number(e.target.value))} />
                </label>
                <label className="tb-field">Total mass (g)
                  <input className="tb-input tb-input-xs" type="number" min="5" value={mass} placeholder={`${baseMass}`}
                    onChange={(e) => setMass(e.target.value)} />
                </label>
                <label className="tb-field">Servo
                  <select className="tb-select" value={servo} onChange={(e) => setServo(e.target.value)}>
                    <option value="">same servos</option>
                    {tpl && tpl.ok ? tpl.servos.map((s) => <option key={s} value={s}>{s}</option>) : null}
                  </select>
                </label>
              </div>
            </div>
          ) : null}
          {withVariant && !hasVariant ? <p className="tb-muted tb-small">Change the size, mass or servo to get a second robot.</p> : null}
        </div>
      </div>

      <div className="tb-card">
        <div className="tb-card-head"><h3>2 · The scene</h3><span className="tb-muted">{(SCENE_BY_ID[scene] || {}).blurb}</span></div>
        <div className="tb-scene-grid" role="radiogroup" aria-label="Scene">
          {SCENES.map((s) => (
            <button key={s.id} type="button" role="radio" aria-checked={scene === s.id}
              className={'tb-scene' + (scene === s.id ? ' tb-active' : '')} onClick={() => setScene(s.id)}>
              <span className="tb-scene-icon">{s.icon}</span>
              <span className="tb-scene-title">{s.title}</span>
              <span className="tb-scene-blurb">{s.blurb}</span>
            </button>
          ))}
        </div>
        <div className="tb-row tb-gap">
          <Button kind="primary" busy={running} onClick={simulate}>Simulate · 10 worlds</Button>
          <span className="tb-muted tb-small">{hasVariant ? 'Both robots, same worlds.' : 'One robot.'} Takes well under a minute.</span>
        </div>
      </div>

      <Progress job={job} label="Simulating" />
      {view ? (
        <>
          <Replay key={`${run.robot}-${run.scene}-${job.id}`} robot={run.robot} jobId={job.id} scene={run.scene} names={view.names}
            labels={view.labels} result={view.result} />
          <ResultsTable scene={run.scene} names={view.names} labels={view.labels} cards={view.cards} />
        </>
      ) : null}
    </div>
  )
}
