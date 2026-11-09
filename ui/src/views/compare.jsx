import { useEffect, useMemo, useState } from 'react'
import { Viewer3D, Timeline, usePlayer, tipMarks, tipTime, traceDuration } from '../viewer.jsx'
import { Button, Chip, ErrorBox, Progress, STATUS, human, pct, useApi, useJob, useTrace } from '../ui.jsx'

function parseCustom(text) {
  // "name: path=value, path=value" per line
  const out = []
  for (const line of text.split('\n')) {
    const [name, rest] = line.split(':')
    if (!name || !rest || !name.trim()) continue
    const set = {}
    for (const kv of rest.split(',')) {
      const [k, v] = kv.split('=')
      if (k && v != null && k.trim()) set[k.trim()] = /^[-+*]/.test(v.trim()) || isNaN(Number(v)) ? v.trim() : Number(v)
    }
    if (Object.keys(set).length) out.push({ name: name.trim(), set })
  }
  return out
}

function Delta({ d }) {
  if (d == null) return null
  const pts = Math.round(d * 100)
  if (!pts) return <span className="tb-delta" title="same pass rate as the base design">= same</span>
  return (
    <span className={'tb-delta ' + (pts > 0 ? 'tb-up' : 'tb-down')} title="pass rate against the base design, in percentage points">
      {pts > 0 ? '▲ +' : '▼ −'}{Math.abs(pts)} pts
    </span>
  )
}

// Worlds where the designs disagree (base failing first), worlds where every design fails, and the median.
function worldChoices(row, names, result) {
  const out = row.outcomes || {}
  const passed = (n, seed) => {
    const hit = (out[n] || []).find(([s]) => s === seed)
    return hit ? hit[1] : null
  }
  const differ = []
  const allFail = []
  for (const [seed] of out.base || []) {
    const vals = names.map((n) => passed(n, seed))
    if (vals.some((v) => v) && vals.some((v) => !v)) differ.push(seed)
    else if (vals.every((v) => v === false)) allFail.push(seed)
  }
  differ.sort((a, b) => Number(passed('base', a)) - Number(passed('base', b)) || a - b)
  const card = result.reports.base.scenes.find((c) => c.id === row.scene)
  const median = card && card.metric ? [card.metric.median_seed] : [0]
  return { differ, fail: allFail, median }
}

const MODES = [['differ', 'Different outcome'], ['fail', 'All fail'], ['median', 'Median world']]

function Synced({ robot, jobId, row, names, result }) {
  const choices = useMemo(() => worldChoices(row, names, result), [row, names, result])
  const [mode, setMode] = useState(choices.differ.length ? 'differ' : 'median')
  const [idx, setIdx] = useState(0)
  const list = choices[mode].length ? choices[mode] : choices.median
  const seed = list[Math.min(idx, list.length - 1)]
  const traces = names.map((n) => useTrace({ robot, scene: row.scene, seed, job_id: jobId, variant: n }))
  const ok = traces.map(([d]) => (d && d.ok ? d : null))
  const player = usePlayer(traceDuration(...ok.map((d) => d && d.trace)))
  return (
    <div className="tb-card">
      <div className="tb-card-head">
        <h3>{row.title}: world {seed}, every design</h3>
        <div className="tb-row tb-gap-sm tb-wrap">
          <div className="tb-seg" role="tablist">
            {MODES.map(([m, label]) => (
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
      <div className={'tb-grid-views tb-views-' + Math.min(names.length, 3)}>
        {names.map((n, i) => {
          const d = ok[i]
          if (!d) return <div key={n} className="tb-viewer tb-viewer-wait" style={{ height: 320 }}><span className="tb-spinner" /> {n}…</div>
          const r = d.result || {}
          return (
            <Viewer3D key={n} parts={d.trace.parts} frames={d.trace.frames} fps={d.trace.fps} meta={d.meta} look={d.look}
              tipAt={tipTime(d.trace, r)} tipWhy={r.reason} time={player.t} height={320}
              label={n} sublabel={r.passed ? `passed · ${human(row.scene, r.metric)}` : `${r.reason || 'failed'} · ${human(row.scene, r.metric)}`}
              tone={r.passed ? 'green' : 'red'} />
          )
        })}
      </div>
      <Timeline player={player} marks={tipMarks(...ok.map((d, i) => [d && d.trace, d && d.result, `${names[i]} tips`]))} />
    </div>
  )
}

export function ComparePage({ robot }) {
  const [presets] = useApi(robot ? `/robots/${robot}/variants` : null)
  const [picked, setPicked] = useState({})
  const [custom, setCustom] = useState('')
  const [quick, setQuick] = useState(true)
  const [row, setRow] = useState(null)
  const [job, start] = useJob()
  useEffect(() => { setPicked({}); setRow(null); setCustom('') }, [robot])
  useEffect(() => {
    const list = presets && presets.ok ? presets.variants : []
    if (list.length && !Object.keys(picked).length) setPicked({ [list[list.length - 1].name]: true })
  }, [presets])
  const list = presets && presets.ok ? presets.variants : []
  const variants = [...list.filter((v) => picked[v.name]), ...parseCustom(custom)]
  const result = job && job.status === 'done' ? job.result : null
  const names = result ? result.variants.map((v) => v.name) : []
  const running = job && (job.status === 'running' || job.status === 'starting')
  return (
    <div className="tb-page">
      <div className="tb-hero">
        <div>
          <h2>Compare designs</h2>
          <p>The robot and its variants on exactly the same randomized worlds, side by side. Deltas are in
            percentage points of pass rate against the base design.</p>
        </div>
      </div>
      <div className="tb-card">
        <div className="tb-card-head"><h3>Variants</h3><span className="tb-muted">presets from examples/variants, or your own overrides</span></div>
        <div className="tb-checks">
          {list.map((v) => (
            <label key={v.name} className={'tb-check' + (picked[v.name] ? ' tb-active' : '')}>
              <input type="checkbox" checked={!!picked[v.name]} onChange={(e) => setPicked({ ...picked, [v.name]: e.target.checked })} />
              <span>{v.name}</span>
              <small>{v.set ? Object.entries(v.set).map(([k, x]) => `${k} = ${x}`).join(', ') : `robot ${v.robot}`}</small>
            </label>
          ))}
        </div>
        <textarea className="tb-input tb-textarea" rows={2} value={custom} onChange={(e) => setCustom(e.target.value)}
          placeholder={'legs +1.5 cm: parts.left_leg.size.2=+1.5, parts.right_leg.size.2=+1.5'} />
        <div className="tb-row tb-gap">
          <label className="tb-toggle"><input type="checkbox" checked={quick} onChange={(e) => setQuick(e.target.checked)} /> quick (10 worlds)</label>
          <Button kind="primary" busy={running} disabled={!variants.length}
            onClick={() => { setRow(null); start('/compare', { robot, variants, quick }) }}>
            Compare {variants.length} variant{variants.length === 1 ? '' : 's'}
          </Button>
        </div>
      </div>
      <Progress job={job} label="Comparing" />
      {result ? (
        <div className="tb-card">
          <div className="tb-card-head"><h3>Results</h3><Chip>{result.settings.worlds} worlds per scene · same seeds</Chip></div>
          <div className="tb-table-wrap">
            <table className="tb-table tb-table-compare">
              <thead><tr><th>Scene</th>{names.map((n) => <th key={n}>{n}</th>)}</tr></thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.scene} className={(row && row.scene === r.scene ? 'tb-active ' : '') + 'tb-clickable'}
                    tabIndex={0} aria-selected={!!row && row.scene === r.scene} onClick={() => setRow(r)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setRow(r) } }}>
                    <th scope="row">{r.title}</th>
                    {names.map((n) => {
                      const c = r.cells[n]
                      const st = STATUS[c.status] || STATUS['n/a']
                      if (c.pass_rate == null || c.status === 'out_of_scope') return <td key={n}><Chip tone={st.tone}>{st.label}</Chip></td>
                      return (
                        <td key={n}>
                          <span className={'tb-dot tb-fill-' + st.tone} /> <b>{pct(c.pass_rate)}</b>
                          <span className="tb-muted"> · {human(r.scene, c.median, c.unit)}</span> <Delta d={c.delta_pass} />
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tb-hint">Click a row to replay that scene for every design in the same world.</p>
        </div>
      ) : null}
      {result && row ? <Synced key={row.scene} robot={robot} jobId={job.id} row={row} names={names} result={result} /> : null}
      <ErrorBox data={presets} />
    </div>
  )
}
